import frappe


def _audit_log(title, message):
    """Write a structured entry to the Error Log doctype."""
    try:
        frappe.log_error(title=title, message=message)
    except Exception:
        pass


# Field mapping: HMIS master field name -> Employee doctype field name
FIELD_MAP = {
    "employment_type": "employment_type",
    "designation": "designation",
    "department": "department",
    "branch": "branch",
}

# Fields whose values must match an existing master record
MASTER_LINK_FIELDS = {
    "designation": "Designation",
    "department": "Department",
    "branch": "Branch",
}

# HMIS-side labels -> Frappe Employment Type names
EMPLOYMENT_TYPE_ALIASES = {
    "permanent": "Full-time",
    "full-time": "Full-time",
    "fulltime": "Full-time",
    "contract": "Contract",
    "contractual": "Contract",
}


def _extract_updates(payload):
    if not isinstance(payload, dict):
        return []
    raw = payload.get("updates")
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, dict)]


def _resolve_employee_id(username):
    """
    1. Search User by username -> get User email.
    2. Search Employee by user_id == email -> return Employee name.
    """
    username = (username or "").strip()
    if not username:
        raise ValueError("username is required")

    # STEP 1: Find User in User DocType & fetch Email / User ID
    user = frappe.db.get_value(
        "User", {"name": username}, ["name", "email", "username"], as_dict=True
    ) or frappe.db.get_value(
        "User", {"username": username}, ["name", "email", "username"], as_dict=True
    ) or frappe.db.get_value(
        "User", {"email": username}, ["name", "email", "username"], as_dict=True
    )

    if not user:
        raise ValueError(f"No User found in system for username '{username}'")

    user_email = user.get("email") or user.get("name")

    # STEP 2: Find mapped Employee using user_email (or user.name fallback)
    employee = None
    if user_email:
        employee = frappe.db.get_value("Employee", {"user_id": user_email}, "name")

    if not employee and user.get("name"):
        employee = frappe.db.get_value("Employee", {"user_id": user.get("name")}, "name")

    if not employee:
        raise ValueError(f"No Employee record mapped to User '{username}' (email: {user_email})")

    return employee


def _resolve_master(doctype, value):
    """Case-insensitive master lookup for Link fields."""
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

    # Fast direct DB match
    matched_name = frappe.db.get_value(
        doctype, {name_field: candidate}, name_field
    ) or frappe.db.get_value(
        doctype, {label_field: candidate}, name_field
    )

    if matched_name:
        return matched_name

    # Fallback scan
    rows = frappe.get_all(doctype, fields=[name_field, label_field])
    for row in rows:
        if candidate.lower() == (row.get(name_field) or "").lower():
            return row.get(name_field)
        if candidate.lower() == (row.get(label_field) or "").lower():
            return row.get(name_field)
    return None


@frappe.whitelist()
def sync_employee_master(**kwargs):
    """Bulk-sync employee fields from HMIS master."""
    try:
        payload = frappe.request.get_json(silent=True) or kwargs or {}
        updates = _extract_updates(payload)
    except Exception as e:
        _audit_log(
            "sync_employee_master: fatal payload parse error",
            f"Caller: {frappe.session.user if frappe.session else 'guest'}\nError: {str(e)}",
        )
        raise

    caller = frappe.session.user if frappe.session else "guest"
    remote_addr = getattr(frappe.request, "remote_addr", None) or "unknown"
    _audit_log(
        "sync_employee_master: payload received",
        f"Caller: {caller}\n"
        f"Remote: {remote_addr}\n"
        f"Method: {frappe.request.method if frappe.request else 'unknown'}\n"
        f"Update count: {len(updates)}\n"
        f"Payload: {frappe.as_json(payload, indent=2)}",
    )

    if not updates:
        _audit_log(
            "sync_employee_master: empty payload",
            f"Caller: {caller}\nRemote: {remote_addr}\nPayload was non-JSON or contained no 'updates' array.",
        )
        frappe.throw("Payload must include a non-empty 'updates' array")

    total = len(updates)
    success = 0
    failed = 0
    error_log = []

    try:
        for record in updates:
            username = (record.get("username") or "").strip()
            record_errors = []
            try:
                # STEP 1, 2 & 3: Resolves Employee ID via User -> Email -> Employee
                employee_id = _resolve_employee_id(username)

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
                        actual_doctype = MASTER_LINK_FIELDS[target_field]
                        master_name = _resolve_master(actual_doctype, value)
                        if not master_name:
                            record_errors.append(
                                f"{source_field} '{value}' not found in {actual_doctype} master; skipped"
                            )
                            continue
                        updates_to_apply[target_field] = master_name

                    else:
                        updates_to_apply[target_field] = value

                if not updates_to_apply:
                    raise ValueError("No supported fields supplied for update")

                # STEP 4: Change values in the mapped Employee record
                frappe.db.set_value("Employee", employee_id, updates_to_apply)

                if record_errors:
                    error_log.append({
                        "username": username or record.get("username"),
                        "status": "partial",
                        "message": "; ".join(record_errors),
                    })
                success += 1

            except Exception as e:
                failed += 1
                error_log.append({
                    "username": username or record.get("username"),
                    "status": "error",
                    "message": str(e),
                })

    except Exception as e:
        _audit_log(
            "sync_employee_master: fatal processing error",
            f"Caller: {caller}\nRemote: {remote_addr}\n"
            f"Total: {total} | Success so far: {success} | Failed so far: {failed}\nError: {str(e)}",
        )
        raise

    frappe.db.commit()

    _audit_log(
        "sync_employee_master: completed",
        f"Caller: {caller}\nRemote: {remote_addr}\n"
        f"Total: {total} | Success: {success} | Failed: {failed} | "
        f"Partial: {sum(1 for e in error_log if e['status'] == 'partial')}\n"
        f"Errors: {frappe.as_json(error_log, indent=2)}",
    )

    return {
        "status": "ok",
        "total": total,
        "success": success,
        "failed": failed,
        "errors": error_log,
    }