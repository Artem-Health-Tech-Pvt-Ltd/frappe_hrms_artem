import datetime as dt
import re

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

VALID_GENDERS = {"Male", "Female", "M", "F"}
EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")
PHONE_REGEX = re.compile(r"^[6-9]\d{9}$")

DEFAULT_DEPT = "Other"
DEFAULT_DESIG = "Other"

def validate_employee_for_facebio(doc, method):
    if frappe.flags.in_migrate or frappe.flags.in_install or frappe.flags.in_patch:
        return
    if not _is_branch_allowed(doc.branch):
        return

    errors = []

    if not doc.attendance_device_id:
        errors.append(("attendance_device_id", "UUID is required. Set it before saving."))
    else:
        try:
            u = __import__("uuid").UUID(doc.attendance_device_id)
            if u.version != 4:
                errors.append(
                    ("attendance_device_id", f"Must be a UUID v4, got v{u.version}.")
                )
        except (ValueError, AttributeError):
            errors.append(
                ("attendance_device_id", f"'{doc.attendance_device_id}' is not a valid UUID.")
            )

    if not doc.employee_name:
        errors.append(("employee_name", "Full name is required."))
    elif len(doc.employee_name) > 255:
        errors.append(
            ("employee_name", f"Must be max 255 characters, got {len(doc.employee_name)}.")
        )

    if not doc.gender:
        errors.append(("gender", "Gender is required."))
    elif doc.gender not in VALID_GENDERS:
        errors.append(("gender", f"Must be Male, Female, M, or F. Got '{doc.gender}'."))

    if doc.cell_number:
        phone_clean = "".join(c for c in str(doc.cell_number) if c.isdigit())
        if not PHONE_REGEX.match(phone_clean):
            errors.append(
                ("cell_number", f"Phone must be 10 digits starting with 6-9, got '{doc.cell_number}'.")
            )

    if doc.personal_email and not EMAIL_REGEX.match(doc.personal_email):
        errors.append(
            ("personal_email", f"'{doc.personal_email}' is not a valid email address.")
        )

    if not doc.department:
        _ensure_department_exists(DEFAULT_DEPT)
        doc.department = DEFAULT_DEPT
    elif len(doc.department) > 70:
        errors.append(
            ("department", f"Must be max 70 characters, got {len(doc.department)}.")
        )

    if not doc.designation:
        _ensure_designation_exists(DEFAULT_DESIG)
        doc.designation = DEFAULT_DESIG
    elif len(doc.designation) > 70:
        errors.append(
            ("designation", f"Must be max 70 characters, got {len(doc.designation)}.")
        )

    if errors:
        lines = ["<b>FaceBio validation failed. Fix the following before saving:</b>"]
        for field, msg in errors:
            lines.append(f"&nbsp;&nbsp;• <b>{field}</b>: {msg}")
        frappe.throw("<br>".join(lines), title="FaceBio Validation Error")

def _ensure_department_exists(name):
    if frappe.db.exists("Department", name):
        return
    try:
        d = frappe.new_doc("Department")
        d.department_name = name
        companies = frappe.get_all("Company", limit=1)
        if companies:
            d.company = companies[0].name
        d.insert(ignore_permissions=True)
    except Exception:
        frappe.log_error(
            title=f"FaceBio: failed to create Department '{name}'",
            message=frappe.get_traceback(),
        )

def _ensure_designation_exists(name):
    if frappe.db.exists("Designation", name):
        return
    try:
        d = frappe.new_doc("Designation")
        d.designation_name = name
        d.insert(ignore_permissions=True)
    except Exception:
        frappe.log_error(
            title=f"FaceBio: failed to create Designation '{name}'",
            message=frappe.get_traceback(),
        )

def enqueue_employee_sync(doc, method):
    if frappe.flags.in_migrate or frappe.flags.in_install or frappe.flags.in_patch:
        return
    if not _is_branch_allowed(doc.branch):
        return
    if doc.get("facebio_last_sync_status") == PENDING:
        return
    frappe.enqueue(
        "artem_hrms.facebio_integration.employee_sync.run_sync",
        queue="short",
        employee_name=doc.name,
        timeout=300,
    )

def run_sync(employee_name, retry_count=0):
    try:
        employee = frappe.get_doc("Employee", employee_name)
    except frappe.DoesNotExistError:
        return

    _set_status(employee_name, PENDING)

    missing = _missing_required_fields(employee)
    if missing:
        _mark_failed(
            employee_name,
            f"Missing required field(s): {', '.join(missing)}. Sync skipped.",
        )
        return

    facebio_branch = _resolve_branch(employee.branch)
    if not facebio_branch:
        _mark_failed(
            employee_name,
            f"Branch '{employee.branch}' is not in the FaceBio allow-list. Sync skipped.",
        )
        return

    payload = build_payload(employee, facebio_branch)

    if employee.get("facebio_employee_id"):
        status, body = api.update_employees([payload])
    else:
        status, body = api.add_employees([payload])

    _handle_response(employee_name, status, body, retry_count)

def build_payload(doc, facebio_branch):
    first, middle, last = _split_name(
        doc.employee_name, doc.first_name, doc.last_name
    )
    payload = {
        "attendance_device_id": doc.attendance_device_id,
        "full_name": doc.employee_name,
        "first_name": first,
        "middle_name": middle,
        "last_name": last,
        "gender": doc.gender,
        "date_of_birth": str(doc.date_of_birth) if doc.date_of_birth else None,
        "date_of_joining": str(doc.date_of_joining) if doc.date_of_joining else None,
        "branch": facebio_branch,
        "department": doc.department,
        "designation": doc.designation,
    }
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

def _missing_required_fields(doc):
    missing = []
    if not doc.gender:
        missing.append("gender")
    return missing

def _handle_response(employee_name, status, body, retry_count):
    if status in (200, 201):
        data = (body.get("data") or [{}])[0]
        frappe.db.set_value(
            "Employee",
            employee_name,
            {
                "facebio_employee_id": data.get("employee_id", ""),
                "facebio_uuid": data.get("uuid", ""),
                "facebio_last_sync_status": SYNCED,
                "facebio_last_sync_at": now_datetime(),
                "facebio_last_error": "",
            },
            update_modified=False,
        )
        return

    if status == 422:
        msg = _format_422(body)
        _mark_failed(employee_name, msg)
        _add_comment(employee_name, "FaceBio 422", msg)
        return

    if status == 401:
        msg = (
            "FaceBio returned 401 Unauthorized. "
            "Check FACEBIO_USERNAME and FACEBIO_PASSWORD in constants.py."
        )
        _mark_failed(employee_name, msg)
        frappe.log_error(title="FaceBio 401", message=msg)
        _add_comment(employee_name, "FaceBio 401", msg)
        return

    if status == 429:
        if retry_count >= MAX_429_RETRIES:
            _mark_failed(
                employee_name,
                f"Rate limited (429) after {retry_count} retries. Manual intervention needed.",
            )
            return
        if enqueue_at:
            eta = dt.datetime.now() + dt.timedelta(seconds=RETRY_DELAY_SECONDS)
            enqueue_at(
                eta,
                "artem_hrms.facebio_integration.employee_sync.run_sync",
                queue="long",
                job_id=f"facebio-429-{employee_name}-{retry_count}",
                employee_name=employee_name,
                retry_count=retry_count + 1,
            )
        else:
            frappe.enqueue(
                "artem_hrms.facebio_integration.employee_sync.run_sync",
                queue="long",
                job_id=f"facebio-429-{employee_name}-{retry_count}",
                employee_name=employee_name,
                retry_count=retry_count + 1,
                timeout=300,
            )
        return

    msg = f"FaceBio returned {status}. {body.get('message', '')}"
    _mark_failed(employee_name, msg)

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
                lines.append(f"  Row {idx} ({name}, uuid={uuid_}): {field}: {m}")
    return "\n".join(lines) if len(lines) > 1 else lines[0]

def _set_status(employee_name, status):
    frappe.db.set_value(
        "Employee",
        employee_name,
        {
            "facebio_last_sync_status": status,
            "facebio_last_sync_at": now_datetime(),
        },
        update_modified=False,
    )

def _mark_failed(employee_name, error_message):
    frappe.db.set_value(
        "Employee",
        employee_name,
        {
            "facebio_last_sync_status": FAILED,
            "facebio_last_sync_at": now_datetime(),
            "facebio_last_error": error_message,
        },
        update_modified=False,
    )

def _add_comment(employee_name, title, message):
    try:
        frappe.get_doc(
            {
                "doctype": "Comment",
                "comment_type": "Info",
                "reference_doctype": "Employee",
                "reference_name": employee_name,
                "subject": title,
                "content": message,
            }
        ).insert(ignore_permissions=True)
    except Exception:
        frappe.log_error(
            title=f"FaceBio comment failed for {employee_name}",
            message=frappe.get_traceback(),
        )
