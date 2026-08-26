import frappe
from frappe.utils import get_datetime


def _log_payload(title, payload):
    """Persist full payload to Error Log doctype for audit/debug."""
    try:
        frappe.log_error(message=frappe.as_json(payload, indent=2), title=title)
    except Exception:
        frappe.log_error(title=title)


@frappe.whitelist(allow_guest=False)
def checkin_ingest():
    """
    Ingest biometric punches from Machine.
    Matching priority:
      1. uuid (if present) -> attendance_device_id
      2. user_id           -> custom_aadhar_number
    If either matches, the check-in is recorded.
    """

    data = frappe.request.get_json()

    # Log the incoming request payload for audit/debug
    _log_payload(
        title=f"Biometric API Request (device_id={data.get('device_id') if data else 'N/A'})",
        payload=data or {}
    )

    if not data:
        frappe.throw("Invalid JSON payload")

    device_id = data.get("device_id")
    punches = data.get("punches")

    if not device_id or not punches:
        frappe.throw("device_id and punches are required")

    inserted = 0
    skipped = 0

    results = []

    for p in punches:
        try:
            user_id = str(p.get("user_id") or "").strip()
            uuid = str(p.get("uuid") or "").strip()
            timestamp = p.get("timestamp")
            punch_type = p.get("punch_type") or "IN"

            # Need at least one identifying field
            if not uuid and not user_id:
                skipped += 1
                results.append({
                    "user_id": user_id,
                    "uuid": uuid,
                    "timestamp": timestamp,
                    "status": "skipped",
                    "message": "Both uuid and user_id are missing"
                })
                continue

            # Missing Timestamp
            if not timestamp:
                skipped += 1
                results.append({
                    "user_id": user_id,
                    "uuid": uuid,
                    "timestamp": None,
                    "status": "skipped",
                    "message": "timestamp is missing"
                })
                continue

            punch_time = get_datetime(timestamp)

            employee = None
            match_method = None

            # 1) Try uuid against attendance_device_id first
            if uuid:
                employee = frappe.db.get_value(
                    "Employee",
                    {"attendance_device_id": uuid},
                    "name"
                )
                if employee:
                    match_method = "uuid -> attendance_device_id"

            # 2) Fall back to user_id against custom_aadhar_number
            if not employee and user_id:
                employee = frappe.db.get_value(
                    "Employee",
                    {"custom_aadhar_number": user_id},
                    "name"
                )
                if employee:
                    match_method = "user_id -> custom_aadhar_number"

            # Employee Not Found
            if not employee:
                skipped += 1
                results.append({
                    "user_id": user_id,
                    "uuid": uuid,
                    "timestamp": timestamp,
                    "status": "skipped",
                    "message": f"No employee found (uuid='{uuid}' or user_id='{user_id}')"
                })
                continue

            # Duplicate Check
            if frappe.db.exists(
                "Employee Checkin",
                {
                    "employee": employee,
                    "time": punch_time,
                    "device_id": device_id
                }
            ):
                skipped += 1
                results.append({
                    "employee": employee,
                    "user_id": user_id,
                    "uuid": uuid,
                    "timestamp": timestamp,
                    "status": "skipped",
                    "message": "Duplicate punch already exists"
                })
                continue

            doc = frappe.new_doc("Employee Checkin")
            doc.employee = employee
            doc.time = punch_time
            doc.log_type = punch_type
            doc.device_id = device_id
            doc.custom_source = "Biometric"
            doc.skip_auto_attendance = 0

            doc.flags.ignore_permissions = True

            doc.insert()

            inserted += 1

            results.append({
                "employee": employee,
                "user_id": user_id,
                "uuid": uuid,
                "timestamp": timestamp,
                "status": "inserted",
                "checkin_id": doc.name,
                "match_method": match_method,
                "message": "Checkin inserted successfully"
            })

        except Exception as e:
            skipped += 1

            err_payload = {
                "punch": p,
                "error": str(e),
                "traceback": frappe.get_traceback()
            }
            _log_payload(
                title=f"Biometric API Error (device_id={device_id})",
                payload=err_payload
            )

            results.append({
                "user_id": p.get("user_id"),
                "uuid": p.get("uuid"),
                "timestamp": p.get("timestamp"),
                "status": "error",
                "message": str(e)
            })

    frappe.db.commit()

    return {
        "status": "ok",
        "device_id": device_id,
        "total_received": len(punches),
        "inserted": inserted,
        "skipped": skipped,
        "results": results
    }
