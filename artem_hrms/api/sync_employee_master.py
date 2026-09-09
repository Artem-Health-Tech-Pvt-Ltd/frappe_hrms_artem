import frappe

FIELD_MAP = {
    "employment_type": "employment_type",
    "designation": "designation",
    "department": "department",
    "branch": "branch",
}

MASTER_LINK_FIELDS = {"designation", "department", "branch"}

EMPLOYMENT_TYPE_ALIASES = {
    "permanent": "Full-time",
    "full-time": "Full-time",
    "fulltime": "Full-time",
    "contract": "Contract",
    "contractual": "Contract"
}


def _log_to_error_log(title, message, payload=None, reference_doctype=None, reference_name=None):
    """Safely log messages and payloads into the Frappe Error Log Doctype (Desk UI)."""
    try:
        full_message = message
        if payload is not None:
            full_message += f"\n\n=== Payload ===\n{frappe.as_json(payload)}"

        frappe.log_error(
            title=title,
            message=full_message,
            reference_doctype=reference_doctype,
            reference_name=reference_name
        )
    except Exception:
        pass


def generate_normalized_username(user_id_input):
    username = str(user_id_input or "").replace("@bmcinternal.com", "")
    if "@" in username:
        username = username + "bmcinternal.com"
    else:
        username = username + "@bmcinternal.com"
    return "-".join(username.split())


def _extract_updates(payload):
    if not isinstance(payload, dict):
        return []

    raw = payload.get("updates")
    if not isinstance(raw, list):
        return []

    updates = []
    for item in raw:
        if isinstance(item, dict):
            updates.append(item)
    return updates


def _resolve_employee_id(identifier):
    raw_id = (identifier or "").strip()
    if not raw_id:
        raise ValueError("username / employee ID is required")

    if frappe.db.exists("Employee", raw_id):
        return raw_id

    normalized_user = generate_normalized_username(raw_id)

    user_record = frappe.db.get_value(
        "User",
        {"name": normalized_user},
        ["name", "email"],
        as_dict=True
    ) or frappe.db.get_value(
        "User",
        {"email": normalized_user},
        ["name", "email"],
        as_dict=True
    )

    if user_record:
        employee = frappe.db.get_value(
            "Employee",
            {"user_id": user_record.email or user_record.name},
            "name"
        )
        if employee:
            return employee

    employee = frappe.db.get_value("Employee", {"user_id": normalized_user}, "name")
    if employee:
        return employee

    raise ValueError(f"User is not found. Please create this user with username: '{raw_id}'")


def _resolve_master(doctype, value):
    if value is None:
        return None
    candidate = str(value).strip()
    if not candidate:
        return None

    name_field = "name"
    label_field = {
        "Department": "department_name",
        "Designation": "designation_name",
        "Branch": "branch",
    }.get(doctype, "name")

    rows = frappe.get_all(doctype, fields=[name_field, label_field])
    for row in rows:
        if candidate.lower() == (row.get(name_field) or "").lower():
            return row.get(name_field)
        if candidate.lower() == (row.get(label_field) or "").lower():
            return row.get(label_field)
    return None


@frappe.whitelist(allow_guest=True)
def sync_employee_master(**kwargs):
    """Bulk-sync employee fields from the HMIS master website."""
    frappe.set_user("Administrator")

    payload = frappe.request.get_json(silent=True) or kwargs or {}
    updates = _extract_updates(payload)

    # LOG TO DESK UI AT START: Log entire incoming payload immediately
    _log_to_error_log(
        title="Sync Employee Master: Payload Received",
        message=f"Received payload containing {len(updates)} record(s) to process.",
        payload=payload
    )

    if not updates:
        frappe.throw("Payload must include a non-empty 'updates' array")

    total = len(updates)
    success = 0
    failed = 0

    logs = []
    error_log = []

    logs.append({
        "step": "payload_received",
        "message": f"Payload received successfully with {total} record(s) to process",
        "payload": payload
    })

    doctype_map = {
        "department": "Department",
        "designation": "Designation",
        "branch": "Branch",
    }

    for record in updates:
        username = (record.get("username") or record.get("employee_id") or "").strip()
        record_errors = []
        try:
            employee_id = _resolve_employee_id(username)

            logs.append({
                "step": "user_found",
                "username": username,
                "message": f"User/Employee found successfully: '{employee_id}'",
                "employee_id": employee_id
            })

            updates_to_apply = {}
            for source_field, target_field in FIELD_MAP.items():
                if source_field not in record or record[source_field] is None:
                    continue

                raw_value = record[source_field]
                value = str(raw_value).strip() if raw_value is not None else ""

                if value == "":
                    updates_to_apply[target_field] = ""
                    continue

                if target_field == "employment_type":
                    canonical = EMPLOYMENT_TYPE_ALIASES.get(value.lower(), value)
                    master_name = _resolve_master("Employment Type", canonical)
                    if not master_name:
                        record_errors.append(
                            f"{source_field} '{value}' not found in Employment Type master; skipped"
                        )
                        continue
                    updates_to_apply[target_field] = master_name
                elif target_field in MASTER_LINK_FIELDS:
                    target_doctype = doctype_map.get(target_field, target_field.capitalize())
                    master_name = _resolve_master(target_doctype, value)
                    if not master_name:
                        record_errors.append(
                            f"{source_field} '{value}' not found in {target_doctype} master; skipped"
                        )
                        continue
                    updates_to_apply[target_field] = master_name
                else:
                    updates_to_apply[target_field] = value

            if not updates_to_apply:
                raise ValueError("No supported fields supplied for update")

            doc = frappe.get_doc("Employee", employee_id)
            doc.update(updates_to_apply)
            doc.save(ignore_permissions=True)

            logs.append({
                "step": "db_change_successful",
                "username": username,
                "employee_id": employee_id,
                "message": f"Database update successful for Employee '{employee_id}'",
                "updated_fields": updates_to_apply
            })

            # SUCCESS LOG (Desk UI): payload + confirmation that DB was updated
            # and what values changed.
            _log_to_error_log(
                title=f"Sync Employee Master: DB update successful for '{username}'",
                message=(
                    f"Payload:\n{frappe.as_json(record, indent=2)}\n\n"
                    f"DB update successful. Value changed to "
                    f"{frappe.as_json(updates_to_apply, indent=2)}"
                ),
                payload=record,
                reference_doctype="Employee",
                reference_name=employee_id,
            )

            if record_errors:
                _log_to_error_log(
                    title=f"Sync Employee Master: partial update for '{username}'",
                    message="\n".join(record_errors),
                    payload=record,
                    reference_doctype="Employee",
                    reference_name=employee_id,
                )
                error_log.append({
                    "username": username,
                    "status": "partial",
                    "reason": "; ".join(record_errors),
                    "payload": record
                })
            success += 1

        except Exception as e:
            failed += 1
            error_reason = str(e)

            # Detect the user-not-found cases from _resolve_employee_id so the
            # caller (and the Desk UI Error Log) gets an explicit, actionable
            # message: create the user in HRMS first.
            user_not_found = (
                "User is not found" in error_reason
                or "username / employee ID is required" in error_reason
            )

            if user_not_found:
                error_reason_full = (
                    f"{error_reason}\n\n"
                    f"Action required: HRMS does not have a user for "
                    f"'{username}'. Please create this user in HRMS before "
                    f"retrying the sync."
                )
            else:
                error_reason_full = error_reason

            _log_to_error_log(
                title=(
                    f"Sync Employee Master: user not found - '{username}'"
                    if user_not_found
                    else f"Sync Employee Master: error for '{username}'"
                ),
                message=error_reason_full,
                payload=record,
                reference_doctype="User",
                reference_name=username,
            )

            error_log.append({
                "username": username,
                "status": "error",
                "reason": error_reason_full,
                "payload": record,
                "user_not_found": user_not_found,
            })

    frappe.db.commit()

    return {
        "status": "ok",
        "caller": frappe.session.user,
        "total": total,
        "success": success,
        "failed": failed,
        "logs": logs,
        "error_log": error_log,
    }