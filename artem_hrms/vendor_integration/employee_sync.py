import datetime as dt
import uuid

import frappe
from frappe import _
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


def is_uuid(val):
    """Return True if val is a valid UUID string (36-char hex format)."""
    if not val:
        return False
    val_str = str(val).strip()
    try:
        uuid_obj = uuid.UUID(val_str)
        return str(uuid_obj) == val_str.lower()
    except (ValueError, AttributeError, TypeError):
        return False


def ensure_attendance_device_id(doc, method=None):
    """Generate a device UUID for Contract employees when one is missing, and freeze UUID values."""
    if frappe.flags.in_migrate or frappe.flags.in_install or frappe.flags.in_patch:
        return

    doc.flags.attendance_device_id_generated = False
    if doc.employment_type == "Contract" and not doc.attendance_device_id:
        doc.attendance_device_id = str(uuid.uuid4())
        doc.flags.attendance_device_id_generated = True

    # Freeze protection: Once a UUID is set, it cannot be modified afterward.
    # Existing 10- or 12-digit numeric values are NOT frozen.
    if not doc.is_new() and not getattr(doc.flags, "attendance_device_id_generated", False):
        old_val = None
        if hasattr(doc, "get_value_before_save"):
            old_val = doc.get_value_before_save("attendance_device_id")
        if not old_val and getattr(doc, "_doc_before_save", None):
            old_val = doc._doc_before_save.get("attendance_device_id")
        if not old_val and doc.name and frappe.db.exists("Employee", doc.name):
            old_val = frappe.db.get_value("Employee", doc.name, "attendance_device_id")

        if old_val and is_uuid(old_val):
            if str(doc.attendance_device_id or "").strip() != str(old_val).strip():
                frappe.throw(
                    _("Attendance Device ID cannot be modified once a UUID is assigned.")
                )


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

    is_create = (method == "on_insert")
    modified_fields = None

    if not is_create:
        generated_contract_id = (
            doc.employment_type == "Contract"
            and getattr(doc.flags, "attendance_device_id_generated", False)
            and doc.get("vendor_last_sync_status") != SYNCED
        )
        if not generated_contract_id:
            old = doc.get_doc_before_save() if hasattr(doc, "get_doc_before_save") else getattr(doc, "_doc_before_save", None)
            if old:
                try:
                    vendor_config = frappe.get_doc("Biometric Vendor Configuration", vendor_name)
                    changed = get_changed_mapped_fields(doc, old, vendor_config)
                    if changed is not None and not changed:
                        return
                    if changed:
                        modified_fields = list(changed)
                except frappe.DoesNotExistError:
                    return

    frappe.enqueue(
        "artem_hrms.vendor_integration.employee_sync.run_sync",
        queue="short",
        employee_name=doc.name,
        timeout=300,
        enqueue_after_commit=True,
        modified_fields=modified_fields,
    )


def _get_vendor_for_branch(branch_name):
    """Fetch assigned Biometric Vendor Configuration name for a given Branch."""
    if not branch_name or not frappe.db.has_column("Branch", "custom_biometric_vendor"):
        return None
    return frappe.db.get_value("Branch", branch_name, "custom_biometric_vendor")


def get_changed_mapped_fields(doc, old, vendor_config):
    """Return set of frappe_fields in vendor_config that changed between old and doc."""
    if not old:
        return None

    changed = set()
    mapped_fields = {row.frappe_field for row in vendor_config.payload_mappings if row.frappe_field}
    mapped_fields.add("branch")

    for field in mapped_fields:
        old_val = old.get(field)
        new_val = doc.get(field)
        old_str = "" if old_val is None else str(old_val).strip()
        new_str = "" if new_val is None else str(new_val).strip()
        if old_str != new_str:
            changed.add(field)

    # If employee_name changed, check if split name parts changed
    if str(doc.get("employee_name") or "").strip() != str(old.get("employee_name") or "").strip():
        old_first, old_mid, old_last = _split_name(old.get("employee_name"), old.get("first_name"), old.get("last_name"))
        new_first, new_mid, new_last = _split_name(doc.get("employee_name"), doc.get("first_name"), doc.get("last_name"))
        if old_first != new_first:
            changed.add("first_name")
        if old_mid != new_mid:
            changed.add("middle_name")
        if old_last != new_last:
            changed.add("last_name")
        changed.add("employee_name")

    return changed


def _api_fields_changed(doc, old, vendor_name):
    """Return True if any mapped field differs between old and new doc."""
    try:
        vendor_config = frappe.get_doc("Biometric Vendor Configuration", vendor_name)
    except frappe.DoesNotExistError:
        return False

    changed = get_changed_mapped_fields(doc, old, vendor_config)
    return bool(changed) if changed is not None else True


def run_sync(employee_name, retry_count=0, modified_fields=None):
    """Background worker: call Vendor API using dynamic payload and write result back."""
    try:
        employee = frappe.get_doc("Employee", employee_name)
    except frappe.DoesNotExistError:
        return

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

    if not vendor_config.is_active:
        return

    _set_status(employee_name, PENDING)

    # Initial sync check:
    # If the employee was already synced, or already has a vendor ID / vendor UUID assigned,
    # then subsequent calls must call the update API. Creation API is never called a 2nd time.
    is_initial_synced = (
        employee.get("vendor_last_sync_status") == SYNCED
        or bool(employee.get("vendor_employee_id"))
        or bool(employee.get("vendor_uuid"))
    )
    is_update = bool(is_initial_synced)

    # Build dynamic payload from vendor mapping child table
    try:
        payload = build_payload(
            employee,
            vendor_config,
            is_update=is_update,
            modified_fields=modified_fields if is_update else None,
        )
    except ValueError as val_err:
        _mark_failed(employee_name, str(val_err))
        return

    # Execute request via dynamic HTTP client
    try:
        status, body = api.send_vendor_request(vendor_config, payload, is_update=is_update)
    except Exception as e:
        _mark_failed(employee_name, f"Network/timeout error: {type(e).__name__}: {e}")
        frappe.log_error(
            title=f"Vendor network error for {employee_name}",
            message=frappe.get_traceback(),
        )
        return

    _handle_response(employee_name, status, body, retry_count, modified_fields=modified_fields)


def build_payload(doc, vendor_config, is_update=False, modified_fields=None):
    """Constructs the outgoing payload dictionary based on child table field mappings.
    - If is_update=True:
        Only includes modified fields along with the mandatory UUID (attendance_device_id).
    - If is_update=False:
        Includes all mapped fields and validates mandatory constraints.
    """
    payload = {}
    modified_set = set(modified_fields) if modified_fields is not None else None

    # Identify vendor key mapped to attendance_device_id
    uuid_vendor_key = "uuid"
    for row in vendor_config.payload_mappings:
        if row.frappe_field == "attendance_device_id" and row.vendor_key:
            uuid_vendor_key = row.vendor_key
            break

    # Mandatory UUID value from attendance_device_id or vendor_uuid
    uuid_val = doc.get("attendance_device_id") or doc.get("vendor_uuid")

    for row in vendor_config.payload_mappings:
        if not row.frappe_field or not row.vendor_key:
            continue

        # In update mode, skip fields that were not modified,
        # but ALWAYS keep attendance_device_id
        if is_update and modified_set is not None:
            if row.frappe_field != "attendance_device_id" and row.frappe_field not in modified_set:
                continue

        field_val = doc.get(row.frappe_field)

        # Handle Branch normalization (vendor without comma -> DB with comma)
        if hasattr(row, "transform_value"):
            field_val = row.transform_value(field_val)
        elif row.frappe_field == "branch" and field_val:
            if str(field_val).strip() == "Lokmanya Tilak Municipal Medical College and General Hospital Sion":
                field_val = "Lokmanya Tilak Municipal Medical College and General Hospital, Sion"

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

        # Check mandatory requirement (only enforce on initial creation)
        if not is_update:
            if (field_val is None or field_val == "") and row.is_mandatory:
                raise ValueError(
                    f"Missing required field '{row.frappe_field}' mapped to vendor key '{row.vendor_key}'."
                )

        if field_val is not None and field_val != "":
            payload[row.vendor_key] = str(field_val) if isinstance(field_val, (dt.date, dt.datetime)) else field_val

    # Ensure mandatory UUID is present on update
    if is_update:
        if not uuid_val:
            raise ValueError(
                _("Attendance Device ID (UUID) is required for vendor update request.")
            )
        payload[uuid_vendor_key] = str(uuid_val)

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


def _handle_response(employee_name, status, body, retry_count, modified_fields=None):
    if status in (200, 201):
        data = body.get("data") if (isinstance(body, dict) and "data" in body) else body
        if isinstance(data, list) and len(data) > 0:
            data = data[0]
        elif not isinstance(data, dict):
            data = {}

        update_values = {
            "vendor_last_sync_status": SYNCED,
            "vendor_last_sync_at": now_datetime(),
            "vendor_last_error": "",
        }
        # Only overwrite identifiers if returned in the response
        resp_emp_id = data.get("employee_id", data.get("id"))
        if resp_emp_id:
            update_values["vendor_employee_id"] = str(resp_emp_id)

        resp_uuid = data.get("uuid")
        if resp_uuid:
            update_values["vendor_uuid"] = str(resp_uuid)

        frappe.db.set_value(
            "Employee",
            employee_name,
            update_values,
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
        _retry_with_delay(employee_name, retry_count, modified_fields=modified_fields)
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


def _retry_with_delay(employee_name, retry_count, modified_fields=None):
    if enqueue_at:
        eta = dt.datetime.now() + dt.timedelta(seconds=RETRY_DELAY_SECONDS)
        enqueue_at(
            eta,
            "artem_hrms.vendor_integration.employee_sync.run_sync",
            queue="long",
            job_id=f"vendor-429-{employee_name}-{retry_count}",
            employee_name=employee_name,
            retry_count=retry_count + 1,
            modified_fields=modified_fields,
        )
    else:
        frappe.enqueue(
            "artem_hrms.vendor_integration.employee_sync.run_sync",
            queue="long",
            job_id=f"vendor-429-{employee_name}-{retry_count}",
            employee_name=employee_name,
            enqueue_after_commit=True,
            retry_count=retry_count + 1,
            modified_fields=modified_fields,
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