import datetime as dt
import uuid

import frappe
from frappe.utils import now_datetime

try:
    from frappe.utils.background_jobs import enqueue_at
except ImportError:
    try:
        from frappe.utils.scheduler import enqueue_at
    except ImportError:
        enqueue_at = None

from . import api
from .constants import FAILED, MAX_429_RETRIES, PENDING, RETRY_DELAY_SECONDS, SYNCED


def ensure_attendance_device_id(doc, method):
    """Generate a device UUID for Contract employees when one is missing."""
    if frappe.flags.in_migrate or frappe.flags.in_install or frappe.flags.in_patch:
        return

    frappe.flags.vendor_was_create = bool(doc.is_new())
    doc.flags.attendance_device_id_generated = False
    if doc.employment_type == "Contract" and not doc.attendance_device_id:
        doc.attendance_device_id = str(uuid.uuid4())
        doc.flags.attendance_device_id_generated = True


def enqueue_employee_sync(doc, method):
    """on_insert / on_update hook: enqueue background sync job.
    - Always syncs on create.
    - On update, syncs only if an API-relevant field changed since the last save.
    - Skips silently if no vendor is mapped or no relevant change."""
    if frappe.flags.in_migrate or frappe.flags.in_install or frappe.flags.in_patch:
        return

    vendor_name = _get_vendor_for_branch(doc.branch)
    if not vendor_name:
        return

    if doc.get("vendor_last_sync_status") == PENDING:
        return

    is_create = getattr(frappe.flags, "vendor_was_create", False)
    if not is_create:
        generated_contract_id = (
            doc.employment_type == "Contract"
            and getattr(doc.flags, "attendance_device_id_generated", False)
            and doc.get("vendor_last_sync_status") != SYNCED
        )
        if not generated_contract_id:
            old = getattr(doc, "_doc_before_save", None)
            if old and not _api_fields_changed(doc, old, vendor_name):
                return

    frappe.enqueue(
        "artem_hrms.vendor_integration.employee_sync.run_sync",
        queue="short",
        employee_name=doc.name,
        timeout=300,
        enqueue_after_commit=True,
    )


def _get_vendor_for_branch(branch_name):
    """Fetch assigned Biometric Vendor Configuration name for a given Branch."""
    if not branch_name or not frappe.db.has_column("Branch", "custom_biometric_vendor"):
        return None
    return frappe.db.get_value("Branch", branch_name, "custom_biometric_vendor")


def _api_fields_changed(doc, old, vendor_name):
    """Return True if any mapped field differs between old and new doc."""
    try:
        vendor_config = frappe.get_doc("Biometric Vendor Configuration", vendor_name)
    except frappe.DoesNotExistError:
        return False

    mapped_fields = {row.frappe_field for row in vendor_config.payload_mappings if row.frappe_field}
    mapped_fields.add("branch")

    for field in mapped_fields:
        if doc.get(field) != old.get(field):
            return True
    return False


def run_sync(employee_name, retry_count=0):
    """Background worker: call Vendor API using dynamic payload and write result back."""
    try:
        employee = frappe.get_doc("Employee", employee_name)
    except frappe.DoesNotExistError:
        return

    _set_status(employee_name, PENDING)

    vendor_name = _get_vendor_for_branch(employee.branch)
    if not vendor_name:
        _mark_failed(
            employee_name,
            f"Branch '{employee.branch}' has no Biometric Vendor assigned. Sync skipped.",
        )
        return

    try:
        vendor_config = frappe.get_doc("Biometric Vendor Configuration", vendor_name)
    except frappe.DoesNotExistError:
        _mark_failed(
            employee_name,
            f"Configured vendor '{vendor_name}' does not exist. Sync skipped.",
        )
        return

    # Build dynamic payload from vendor mapping child table
    try:
        payload = build_payload(employee, vendor_config)
    except ValueError as val_err:
        _mark_failed(employee_name, str(val_err))
        return

    # Execute request via dynamic HTTP client
    try:
        is_update = bool(employee.get("vendor_employee_id"))
        status, body = api.send_vendor_request(vendor_config, payload, is_update=is_update)
    except Exception as e:
        _mark_failed(employee_name, f"Network/timeout error: {type(e).__name__}: {e}")
        frappe.log_error(
            title=f"Vendor network error for {employee_name}",
            message=frappe.get_traceback(),
        )
        return

    _handle_response(employee_name, status, body, retry_count)


def build_payload(doc, vendor_config):
    """Constructs the outgoing payload dictionary based on child table field mappings."""
    payload = {}

    for row in vendor_config.payload_mappings:
        if not row.frappe_field or not row.vendor_key:
            continue

        field_val = doc.get(row.frappe_field)

        if row.frappe_field == "custom_administrative_officer" and field_val:
            field_val = frappe.db.get_value("Employee", field_val, "attendance_device_id")

        # Handle Name Split logic if dynamically mapped
        if row.frappe_field in ("first_name", "middle_name", "last_name"):
            first, middle, last = _split_name(doc.employee_name, doc.first_name, doc.last_name)
            if row.frappe_field == "first_name":
                field_val = first
            elif row.frappe_field == "middle_name":
                field_val = middle
            elif row.frappe_field == "last_name":
                field_val = last

        # Check mandatory requirement
        if not field_val and row.is_mandatory:
            raise ValueError(
                f"Missing required field '{row.frappe_field}' mapped to vendor key '{row.vendor_key}'."
            )

        if field_val is not None and field_val != "":
            payload[row.vendor_key] = str(field_val) if isinstance(field_val, (dt.date, dt.datetime)) else field_val

    return payload


def _split_name(employee_name, first_name, last_name):
    if first_name and last_name:
        parts = (employee_name or "").split()
        middle_parts = [p for p in parts if p != first_name and p != last_name]
        return first_name, " ".join(middle_parts), last_name
    if first_name:
        return first_name, "", ""
    if last_name:
        return "", "", last_name
    parts = (employee_name or "").split()
    if not parts:
        return "", "", ""
    if len(parts) == 1:
        return parts[0], "", ""
    if len(parts) == 2:
        return parts[0], "", parts[1]
    return parts[0], " ".join(parts[1:-1]), parts[-1]


def _handle_response(employee_name, status, body, retry_count):
    if status in (200, 201):
        data = body.get("data") if isinstance(body, dict) else {}
        if isinstance(data, list) and len(data) > 0:
            data = data[0]
        elif not isinstance(data, dict):
            data = {}

        frappe.db.set_value(
            "Employee",
            employee_name,
            {
                "vendor_employee_id": data.get("employee_id", data.get("id", "")),
                "vendor_uuid": data.get("uuid", ""),
                "vendor_last_sync_status": SYNCED,
                "vendor_last_sync_at": now_datetime(),
                "vendor_last_error": "",
            },
            update_modified=False,
        )
        return

    if status == 422:
        _mark_failed(employee_name, _format_422(body))
        return

    if status in (401, 403):
        _mark_failed(
            employee_name,
            f"Vendor Authentication Failed (HTTP {status}). Check credentials in Biometric Vendor Configuration.",
        )
        return

    if status == 429:
        if retry_count >= MAX_429_RETRIES:
            _mark_failed(
                employee_name,
                f"Rate limited (429) after {retry_count} retries. Manual intervention needed.",
            )
            return
        _retry_with_delay(employee_name, retry_count)
        return

    err_msg = body.get("message", body.get("raw", "")) if isinstance(body, dict) else str(body)
    _mark_failed(
        employee_name,
        f"Vendor returned HTTP {status}. {err_msg}".strip(),
    )


def _format_422(body):
    if not isinstance(body, dict):
        return f"422: Validation Error - {body}"

    errors = body.get("errors") or []
    lines = [f"422: {body.get('message', 'Validation error')}"]
    
    if isinstance(errors, list):
        for err in errors:
            if isinstance(err, dict):
                idx = err.get("index", "?")
                name = err.get("full_name", "?")
                field_errors = err.get("errors", {}) or {}
                for field, messages in field_errors.items():
                    msg_str = ", ".join(messages) if isinstance(messages, list) else str(messages)
                    lines.append(f"Row {idx} ({name}): {field}: {msg_str}")
    elif isinstance(errors, dict):
        for field, messages in errors.items():
            msg_str = ", ".join(messages) if isinstance(messages, list) else str(messages)
            lines.append(f"{field}: {msg_str}")

    return "\n".join(lines) if len(lines) > 1 else lines[0]


def _retry_with_delay(employee_name, retry_count):
    if enqueue_at:
        eta = dt.datetime.now() + dt.timedelta(seconds=RETRY_DELAY_SECONDS)
        enqueue_at(
            eta,
            "artem_hrms.vendor_integration.employee_sync.run_sync",
            queue="long",
            job_id=f"vendor-429-{employee_name}-{retry_count}",
            employee_name=employee_name,
            retry_count=retry_count + 1,
        )
    else:
        frappe.enqueue(
            "artem_hrms.vendor_integration.employee_sync.run_sync",
            queue="long",
            job_id=f"vendor-429-{employee_name}-{retry_count}",
            employee_name=employee_name,
            enqueue_after_commit=True,
            retry_count=retry_count + 1,
            timeout=300,
        )


def _set_status(employee_name, status):
    frappe.db.set_value(
        "Employee",
        employee_name,
        {
            "vendor_last_sync_status": status,
            "vendor_last_sync_at": now_datetime(),
        },
        update_modified=False,
    )


def _mark_failed(employee_name, error_message):
    frappe.db.set_value(
        "Employee",
        employee_name,
        {
            "vendor_last_sync_status": FAILED,
            "vendor_last_sync_at": now_datetime(),
            "vendor_last_error": error_message,
        },
        update_modified=False,
    )