import frappe
from frappe.utils import get_datetime
from artem_hrms.doc_events.employee_checkin import get_next_log_type_for_employee


def _log_failure(title, payload):
    """Persist failure payloads to Error Log doctype and commit immediately."""
    try:
        title_str = str(title)[:140]
        message_str = frappe.as_json(payload, indent=2) if not isinstance(payload, str) else str(payload)
        frappe.log_error(message=message_str, title=title_str)
        frappe.db.commit()
    except Exception:
        try:
            frappe.log_error(title=str(title)[:140])
            frappe.db.commit()
        except Exception:
            pass


def _to_emp_dict(emp):
    if not emp:
        return None
    name = emp.get("name") if isinstance(emp, dict) else getattr(emp, "name", str(emp))
    emp_name = emp.get("employee_name") if isinstance(emp, dict) else getattr(emp, "employee_name", name)
    status = emp.get("status") if isinstance(emp, dict) else getattr(emp, "status", None)
    relieving = emp.get("relieving_date") if isinstance(emp, dict) else getattr(emp, "relieving_date", None)
    return {
        "name": name,
        "employee_name": emp_name,
        "status": status,
        "relieving_date": relieving,
    }


def find_employee(uuid_val=None, user_id_val=None):
    """
    Find employee by uuid or user_id in priority order:
      1. uuid -> attendance_device_id
      2. uuid -> vendor_uuid
      3. user_id -> attendance_device_id (10/12-digit numbers)
      4. user_id -> custom_aadhar_number
      5. user_id -> vendor_employee_id
      6. user_id -> employee_number
      7. user_id -> name (Employee DocName / ID)

    Returns:
      tuple: (employee_dict, match_method, searched_fields_list)
    """
    searched = []

    # 1) Try uuid against attendance_device_id
    if uuid_val:
        searched.append(f"attendance_device_id='{uuid_val}'")
        emp = frappe.db.get_value(
            "Employee",
            {"attendance_device_id": uuid_val},
            ["name", "employee_name", "status", "relieving_date"],
            as_dict=True,
        )
        if emp:
            return _to_emp_dict(emp), "uuid -> attendance_device_id", searched

        # 2) Try uuid against vendor_uuid
        if frappe.db.has_column("Employee", "vendor_uuid"):
            searched.append(f"vendor_uuid='{uuid_val}'")
            emp = frappe.db.get_value(
                "Employee",
                {"vendor_uuid": uuid_val},
                ["name", "employee_name", "status", "relieving_date"],
                as_dict=True,
            )
            if emp:
                return _to_emp_dict(emp), "uuid -> vendor_uuid", searched

    # 3) Try user_id against attendance_device_id
    if user_id_val:
        searched.append(f"attendance_device_id='{user_id_val}'")
        emp = frappe.db.get_value(
            "Employee",
            {"attendance_device_id": user_id_val},
            ["name", "employee_name", "status", "relieving_date"],
            as_dict=True,
        )
        if emp:
            return _to_emp_dict(emp), "user_id -> attendance_device_id", searched

        # 4) Try user_id against custom_aadhar_number
        if frappe.db.has_column("Employee", "custom_aadhar_number"):
            searched.append(f"custom_aadhar_number='{user_id_val}'")
            emp = frappe.db.get_value(
                "Employee",
                {"custom_aadhar_number": user_id_val},
                ["name", "employee_name", "status", "relieving_date"],
                as_dict=True,
            )
            if emp:
                return _to_emp_dict(emp), "user_id -> custom_aadhar_number", searched

        # 5) Try user_id against vendor_employee_id
        if frappe.db.has_column("Employee", "vendor_employee_id"):
            searched.append(f"vendor_employee_id='{user_id_val}'")
            emp = frappe.db.get_value(
                "Employee",
                {"vendor_employee_id": user_id_val},
                ["name", "employee_name", "status", "relieving_date"],
                as_dict=True,
            )
            if emp:
                return _to_emp_dict(emp), "user_id -> vendor_employee_id", searched

        # 6) Try user_id against employee_number
        if frappe.db.has_column("Employee", "employee_number"):
            searched.append(f"employee_number='{user_id_val}'")
            emp = frappe.db.get_value(
                "Employee",
                {"employee_number": user_id_val},
                ["name", "employee_name", "status", "relieving_date"],
                as_dict=True,
            )
            if emp:
                return _to_emp_dict(emp), "user_id -> employee_number", searched

        # 7) Try user_id against name
        searched.append(f"name='{user_id_val}'")
        emp = frappe.db.get_value(
            "Employee",
            {"name": user_id_val},
            ["name", "employee_name", "status", "relieving_date"],
            as_dict=True,
        )
        if emp:
            return _to_emp_dict(emp), "user_id -> name", searched

    return None, None, searched


@frappe.whitelist(allow_guest=False)
def checkin_ingest():
    """
    Ingest biometric punches from Machine.
    Matching priority:
      1. uuid (if present) -> attendance_device_id, vendor_uuid
      2. user_id           -> attendance_device_id, custom_aadhar_number,
                              vendor_employee_id, employee_number, name
    If matched, the check-in is recorded.

    Logging policy:
      - Whenever any punch is skipped or produces an error, a detailed Error Log
        entry is created with the exact reason and full punch payload.
      - The exact reason is also returned in each item of the API response and in
        `skipped_reasons` at the top level for clear observability.
    """

    data = None
    try:
        data = frappe.request.get_json()
    except Exception:
        pass

    if not data and hasattr(frappe, "form_dict") and frappe.form_dict:
        data = dict(frappe.form_dict)

    if not data:
        _log_failure(
            title="Biometric Checkin Skipped: Empty Payload",
            payload={"error": "Request body or form_dict is empty"},
        )
        frappe.throw("Invalid JSON payload: Request body or form_dict is empty")

    device_id = data.get("device_id")
    punches = data.get("punches")

    if isinstance(punches, str):
        try:
            import json
            punches = json.loads(punches)
        except Exception as e:
            _log_failure(
                title=f"Biometric Checkin Error: Invalid Punches JSON (device_id={device_id})",
                payload={"raw_punches": punches, "error": str(e)},
            )
            frappe.throw(f"Invalid JSON in punches: {e}")

    if not device_id or not punches:
        _log_failure(
            title="Biometric Checkin Skipped: Missing device_id or punches",
            payload={"data": data},
        )
        frappe.throw("device_id and punches are required")

    if not isinstance(punches, list):
        punches = [punches]

    # Sort punches chronologically to ensure accurate odd/even (IN/OUT) sequence
    try:
        punches = sorted(
            punches,
            key=lambda p: get_datetime(p.get("timestamp")) if p.get("timestamp") else get_datetime("1970-01-01"),
        )
    except Exception:
        pass

    inserted = 0
    skipped = 0

    results = []
    skipped_results = []

    for p in punches:
        try:
            user_id = str(p.get("user_id") or "").strip()
            uuid = str(p.get("uuid") or "").strip()
            timestamp = p.get("timestamp")
            punch_type = p.get("punch_type") or "IN"

            # 1. Need at least one identifying field
            if not uuid and not user_id:
                skipped += 1
                reason = "Both 'uuid' and 'user_id' are missing or empty in punch payload. At least one identifier is required."
                r = {
                    "user_id": user_id,
                    "uuid": uuid,
                    "timestamp": timestamp,
                    "status": "skipped",
                    "reason": reason,
                    "message": reason,
                }
                results.append(r)
                skipped_results.append(r)
                _log_failure(
                    title=f"Biometric Checkin Skipped: Missing Identifiers (device_id={device_id})",
                    payload={"device_id": device_id, "punch": p, "reason": reason},
                )
                continue

            # 2. Missing Timestamp
            if not timestamp:
                skipped += 1
                reason = "Missing 'timestamp' field in punch payload."
                r = {
                    "user_id": user_id,
                    "uuid": uuid,
                    "timestamp": None,
                    "status": "skipped",
                    "reason": reason,
                    "message": reason,
                }
                results.append(r)
                skipped_results.append(r)
                _log_failure(
                    title=f"Biometric Checkin Skipped: Missing Timestamp (device_id={device_id})",
                    payload={"device_id": device_id, "punch": p, "reason": reason},
                )
                continue

            # 3. Parse Timestamp
            try:
                punch_time = get_datetime(timestamp)
            except Exception as dt_err:
                skipped += 1
                reason = f"Invalid timestamp format '{timestamp}': {str(dt_err)}"
                r = {
                    "user_id": user_id,
                    "uuid": uuid,
                    "timestamp": timestamp,
                    "status": "skipped",
                    "reason": reason,
                    "message": reason,
                }
                results.append(r)
                skipped_results.append(r)
                _log_failure(
                    title=f"Biometric Checkin Skipped: Invalid Timestamp '{timestamp}' (device_id={device_id})",
                    payload={"device_id": device_id, "punch": p, "reason": reason},
                )
                continue

            # 4. Lookup Employee
            emp_record, match_method, searched_fields = find_employee(uuid_val=uuid, user_id_val=user_id)

            if not emp_record:
                skipped += 1
                searched_str = ", ".join(searched_fields)
                reason = (
                    f"No employee found matching uuid='{uuid}' or user_id='{user_id}'. "
                    f"Evaluated [{searched_str}], but no matching Employee record exists in the system."
                )
                r = {
                    "user_id": user_id,
                    "uuid": uuid,
                    "timestamp": timestamp,
                    "status": "skipped",
                    "reason": reason,
                    "message": reason,
                    "searched_fields": searched_fields,
                }
                results.append(r)
                skipped_results.append(r)
                _log_failure(
                    title=f"Biometric Checkin Skipped: Employee Not Found (uuid={uuid or 'None'}, user_id={user_id or 'None'})",
                    payload={
                        "device_id": device_id,
                        "punch": p,
                        "reason": reason,
                        "searched_criteria": searched_fields,
                    },
                )
                continue

            employee = emp_record["name"]
            employee_name = emp_record.get("employee_name") or employee
            employee_status = emp_record.get("status")

            # 5. Check Active Status
            if employee_status != "Active":
                skipped += 1
                reason = (
                    f"Employee '{employee}' ({employee_name}) has status '{employee_status}'. "
                    f"Check-in is permitted only for Active employees."
                )
                r = {
                    "employee": employee,
                    "employee_name": employee_name,
                    "user_id": user_id,
                    "uuid": uuid,
                    "timestamp": timestamp,
                    "status": "skipped",
                    "reason": reason,
                    "message": reason,
                }
                results.append(r)
                skipped_results.append(r)
                _log_failure(
                    title=f"Biometric Checkin Skipped: Inactive Employee '{employee}' ({employee_status})",
                    payload={
                        "device_id": device_id,
                        "punch": p,
                        "reason": reason,
                        "employee": employee,
                        "employee_status": employee_status,
                    },
                )
                continue

            # 6. Check Relieving Date
            if emp_record.get("relieving_date"):
                checkin_date = frappe.utils.getdate(punch_time)
                relieving_date = frappe.utils.getdate(emp_record["relieving_date"])
                if checkin_date > relieving_date:
                    skipped += 1
                    reason = (
                        f"Check-in not allowed: Employee '{employee}' ({employee_name}) was relieved on {relieving_date} "
                        f"(punch date is {checkin_date})."
                    )
                    r = {
                        "employee": employee,
                        "employee_name": employee_name,
                        "user_id": user_id,
                        "uuid": uuid,
                        "timestamp": timestamp,
                        "status": "skipped",
                        "reason": reason,
                        "message": reason,
                    }
                    results.append(r)
                    skipped_results.append(r)
                    _log_failure(
                        title=f"Biometric Checkin Skipped: Relieved Employee '{employee}'",
                        payload={
                            "device_id": device_id,
                            "punch": p,
                            "reason": reason,
                            "employee": employee,
                            "relieving_date": str(relieving_date),
                            "punch_date": str(checkin_date),
                        },
                    )
                    continue

            # 7. Duplicate Check
            existing = frappe.db.get_value(
                "Employee Checkin",
                {
                    "employee": employee,
                    "time": punch_time,
                    "device_id": device_id,
                },
                ["name", "log_type", "device_id", "time"],
                as_dict=True,
            )
            if not existing:
                existing = frappe.db.get_value(
                    "Employee Checkin",
                    {
                        "employee": employee,
                        "time": punch_time,
                    },
                    ["name", "log_type", "device_id", "time"],
                    as_dict=True,
                )

            if existing:
                skipped += 1
                existing_id = existing.get("name") if isinstance(existing, dict) else getattr(existing, "name", str(existing))
                existing_dev = existing.get("device_id") if isinstance(existing, dict) else getattr(existing, "device_id", device_id)
                existing_log_type = existing.get("log_type") if isinstance(existing, dict) else getattr(existing, "log_type", "")
                reason = (
                    f"Duplicate punch: Employee '{employee}' ({employee_name}) already has a check-in record "
                    f"'{existing_id}' at timestamp '{punch_time}' on device '{existing_dev}'. "
                    f"Existing log_type: {existing_log_type}."
                )
                r = {
                    "employee": employee,
                    "employee_name": employee_name,
                    "user_id": user_id,
                    "uuid": uuid,
                    "timestamp": timestamp,
                    "status": "skipped",
                    "reason": reason,
                    "message": reason,
                    "existing_checkin_id": existing_id,
                }
                results.append(r)
                skipped_results.append(r)
                _log_failure(
                    title=f"Biometric Checkin Skipped: Duplicate Punch ({employee} at {punch_time})",
                    payload={
                        "device_id": device_id,
                        "punch": p,
                        "reason": reason,
                        "employee": employee,
                        "existing_checkin": existing,
                    },
                )
                continue

            # 8. Insert Employee Checkin
            try:
                doc = frappe.new_doc("Employee Checkin")
                doc.employee = employee
                doc.time = punch_time
                doc.log_type = get_next_log_type_for_employee(employee, punch_time)
                doc.device_id = device_id
                doc.custom_source = "Biometric"
                doc.skip_auto_attendance = 0
                doc.flags.ignore_permissions = True

                doc.insert()

                inserted += 1

                results.append({
                    "employee": employee,
                    "employee_name": employee_name,
                    "user_id": user_id,
                    "uuid": uuid,
                    "timestamp": timestamp,
                    "log_type": doc.log_type,
                    "status": "inserted",
                    "checkin_id": doc.name,
                    "match_method": match_method,
                    "reason": "Checkin inserted successfully",
                    "message": "Checkin inserted successfully",
                })

            except Exception as insert_err:
                skipped += 1
                reason = f"Checkin insert failed for Employee '{employee}' ({employee_name}): {str(insert_err)}"
                r = {
                    "employee": employee,
                    "employee_name": employee_name,
                    "user_id": user_id,
                    "uuid": uuid,
                    "timestamp": timestamp,
                    "status": "error",
                    "reason": reason,
                    "message": str(insert_err),
                }
                results.append(r)
                skipped_results.append(r)
                _log_failure(
                    title=f"Biometric Checkin Error: Insert Failed ({employee})",
                    payload={
                        "device_id": device_id,
                        "punch": p,
                        "reason": reason,
                        "employee": employee,
                        "error": str(insert_err),
                        "traceback": frappe.get_traceback(),
                    },
                )

        except Exception as e:
            skipped += 1
            reason = f"Unexpected processing error: {str(e)}"
            r = {
                "user_id": p.get("user_id"),
                "uuid": p.get("uuid"),
                "timestamp": p.get("timestamp"),
                "status": "error",
                "reason": reason,
                "message": str(e),
            }
            results.append(r)
            skipped_results.append(r)
            _log_failure(
                title=f"Biometric Checkin Error: Unexpected Error (device_id={device_id})",
                payload={
                    "device_id": device_id,
                    "punch": p,
                    "reason": reason,
                    "error": str(e),
                    "traceback": frappe.get_traceback(),
                },
            )

    frappe.db.commit()

    # Log summary entry if any punches were skipped
    if skipped_results:
        _log_failure(
            title=f"Biometric Ingest Summary (device_id={device_id}, total={len(punches)}, inserted={inserted}, skipped={skipped})",
            payload={
                "device_id": device_id,
                "total_received": len(punches),
                "inserted": inserted,
                "skipped": skipped,
                "skipped_details": skipped_results,
            },
        )

    return {
        "status": "ok",
        "device_id": device_id,
        "total_received": len(punches),
        "inserted": inserted,
        "skipped": skipped,
        "skipped_reasons": [r.get("reason") for r in skipped_results if r.get("reason")],
        "results": results,
    }