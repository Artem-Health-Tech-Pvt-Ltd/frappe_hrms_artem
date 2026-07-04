import frappe
from frappe.utils import get_datetime

@frappe.whitelist(allow_guest=False)
def checkin_ingest():
    """
    Ingest biometric punches from Machine
    """

    data = frappe.request.get_json()

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
            timestamp = p.get("timestamp")
            punch_type = p.get("punch_type") or "IN"

            # Missing User ID
            if not user_id:
                skipped += 1
                results.append({
                    "user_id": None,
                    "timestamp": timestamp,
                    "status": "skipped",
                    "message": "user_id is missing"
                })
                continue

            # Missing Timestamp
            if not timestamp:
                skipped += 1
                results.append({
                    "user_id": user_id,
                    "timestamp": None,
                    "status": "skipped",
                    "message": "timestamp is missing"
                })
                continue

            punch_time = get_datetime(timestamp)

            employee = frappe.db.get_value(
                "Employee",
                {"attendance_device_id": user_id},
                "name"
            )

            # Employee Not Found
            if not employee:
                skipped += 1
                results.append({
                    "user_id": user_id,
                    "timestamp": timestamp,
                    "status": "skipped",
                    "message": f"No employee mapped with attendance_device_id={user_id}"
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
            doc.checkin_source = "Biometric"
            doc.skip_auto_attendance = 0

            doc.flags.ignore_permissions = True

            doc.insert()

            inserted += 1

            results.append({
                "employee": employee,
                "user_id": user_id,
                "timestamp": timestamp,
                "status": "inserted",
                "checkin_id": doc.name,
                "message": "Checkin inserted successfully"
            })

        except Exception as e:
            skipped += 1

            results.append({
                "user_id": p.get("user_id"),
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
