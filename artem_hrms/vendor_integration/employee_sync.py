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
from .constants import BRANCH_MAP

MAX_429_RETRIES = 3
RETRY_DELAY_SECONDS = 60

PENDING = "Pending"
SYNCED = "Synced"
FAILED = "Failed"

API_FIELDS = (
    "attendance_device_id",
    "employee_name",
    "first_name",
    "last_name",
    "gender",
    "date_of_birth",
    "date_of_joining",
    "branch",
    "department",
    "designation",
    "cell_number",
    "personal_email",
)


def ensure_attendance_device_id(doc, method):
    """Validate hook: auto-generate UUID v4 for attendance_device_id on create.
    Also flags whether this save is a fresh create so the sync hook knows to
    skip the field-change check on the first sync."""
    if frappe.flags.in_migrate or frappe.flags.in_install or frappe.flags.in_patch:
        return
    frappe.flags.vendor_was_create = bool(doc.is_new())
    if doc.is_new() and not doc.attendance_device_id:
        doc.attendance_device_id = str(uuid.uuid4())


def enqueue_employee_sync(doc, method):
    """on_insert / on_update hook: enqueue background sync job.
    - Always syncs on create.
    - On update, syncs only if an API-relevant field changed since the last save.
    - Skips silently if no relevant change (saves an API call)."""
    if frappe.flags.in_migrate or frappe.flags.in_install or frappe.flags.in_patch:
        return
    if not _is_branch_allowed(doc.branch):
        return
    if doc.get("vendor_last_sync_status") == PENDING:
        return

    is_create = getattr(frappe.flags, "vendor_was_create", False)
    if not is_create:
        old = getattr(doc, "_doc_before_save", None)
        if old and not _api_fields_changed(doc, old):
            return

    frappe.enqueue(
        "artem_hrms.vendor_integration.employee_sync.run_sync",
        queue="short",
        employee_name=doc.name,
        timeout=300,
    )


def _api_fields_changed(doc, old):
    """Return True if any field sent to the vendor differs between old and new doc."""
    for field in API_FIELDS:
        if doc.get(field) != old.get(field):
            return True
    return False


def run_sync(employee_name, retry_count=0):
    """Background worker: call Add (new) or Update (existing), write result back."""
    try:
        employee = frappe.get_doc("Employee", employee_name)
    except frappe.DoesNotExistError:
        return

    _set_status(employee_name, PENDING)

    vendor_branch = _resolve_branch(employee.branch)
    if not vendor_branch:
        _mark_failed(
            employee_name,
            f"Branch '{employee.branch}' is not in BRANCH_MAP. Sync skipped.",
        )
        return

    payload = build_payload(employee, vendor_branch)

    try:
        if employee.get("vendor_employee_id"):
            status, body = api.update_employees([payload])
        else:
            status, body = api.add_employees([payload])
    except Exception as e:
        _mark_failed(employee_name, f"Network/timeout error: {type(e).__name__}: {e}")
        frappe.log_error(
            title=f"Vendor network error for {employee_name}",
            message=frappe.get_traceback(),
        )
        return

    _handle_response(employee_name, status, body, retry_count)


def build_payload(doc, vendor_branch):
    first, middle, last = _split_name(
        doc.employee_name, doc.first_name, doc.last_name
    )
    payload = {
        "attendance_device_id": doc.attendance_device_id,
        "full_name": doc.employee_name,
        "first_name": first,
        "middle_name": middle,
        "last_name": last,
        "gender": doc.gender or "",
        "branch": vendor_branch,
        "department": doc.department or "Other",
        "designation": doc.designation or "Other",
    }
    if doc.date_of_birth:
        payload["date_of_birth"] = str(doc.date_of_birth)
    if doc.date_of_joining:
        payload["date_of_joining"] = str(doc.date_of_joining)
    if doc.cell_number:
        payload["phone"] = doc.cell_number
    if doc.personal_email:
        payload["email"] = doc.personal_email
    return {k: v for k, v in payload.items() if v}


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


def _is_branch_allowed(frappe_branch):
    if not frappe_branch:
        return False
    target = frappe_branch.strip().lower()
    return any(k.strip().lower() == target for k in BRANCH_MAP)


def _resolve_branch(frappe_branch):
    if not frappe_branch:
        return None
    target = frappe_branch.strip().lower()
    for k, v in BRANCH_MAP.items():
        if k.strip().lower() == target:
            return v
    return None


def _handle_response(employee_name, status, body, retry_count):
    if status in (200, 201):
        data = (body.get("data") or [{}])[0]
        frappe.db.set_value(
            "Employee",
            employee_name,
            {
                "vendor_employee_id": data.get("employee_id", ""),
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

    if status == 401:
        _mark_failed(
            employee_name,
            "Vendor returned 401 Unauthorized. Check VENDOR_USERNAME and VENDOR_PASSWORD in constants.py.",
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

    _mark_failed(
        employee_name,
        f"Vendor returned HTTP {status}. {body.get('message', '')}".strip(),
    )


def _format_422(body):
    errors = body.get("errors") or []
    lines = [f"422: {body.get('message', 'Validation error')}"]
    for err in errors:
        idx = err.get("index", "?")
        uuid_ = err.get("attendance_device_id", "?")
        name = err.get("full_name", "?")
        field_errors = err.get("errors", {}) or {}
        for field, messages in field_errors.items():
            for m in messages:
                lines.append(f"Row {idx} ({name}, uuid={uuid_}): {field}: {m}")
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