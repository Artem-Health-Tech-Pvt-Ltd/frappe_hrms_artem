import frappe


def _audit_log(title, message):
    """Write a structured entry to the Error Log doctype.

    Used for HMIS API lifecycle tracing (entry + completion). Goes to the
    same Error Log UI as exceptions, so it shows up alongside any real
    errors in the desk. Pure logging — never raises.
    """
    try:
        frappe.log_error(title=title, message=message)
    except Exception:import frappe


def _audit_log(title, message):
    """Write a structured entry to the Error Log doctype.

    Used for HMIS API lifecycle tracing (entry + completion). Goes to the
    same Error Log UI as exceptions, so it shows up alongside any real
    errors in the desk. Pure logging — never raises.
    """
    try:
        frappe.log_error(title=title, message=message)
    except Exception:
        # If the log itself fails (DB down, etc.) don't take down the request.
        pass


# Extensible field map: HMIS master field name -> Employee doctype field name.
# Add new entries here to sync additional fields without changing the API contract.
FIELD_MAP = {
    "employment_type": "employment_type",
    "designation": "designation",
    "department": "department",
    "branch": "branch",
}

# Fields whose values must match an existing master record. If the supplied value
# does not resolve, the field is silently skipped and logged.
MASTER_LINK_FIELDS = {"designation", "department", "branch"}

# HMIS-side labels -> Frappe Employment Type names.
# Lookup is case-insensitive after stripping. Unmapped values pass through and
# are validated against the Employment Type doctype like other link fields.
EMPLOYMENT_TYPE_ALIASES = {
    "permanent": "Full-time",
    "full-time": "Full-time",
    "fulltime": "Full-time",
    "contract": "Contract",
}


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


def _resolve_employee_id(username):
    """Resolve a username (User.name) -> Employee.name via User.email -> Employee.user_id."""
    username = (username or "").strip()
    if not username:
        raise ValueError("username is required")

    user_email = frappe.db.get_value("User", {"name": username}, "email")
    if not user_email:
        raise ValueError(f"No User found with username '{username}'")

    employee = frappe.db.get_value(
        "Employee",
        {"user_id": user_email},
        "name",
    )
    if not employee:
        raise ValueError(
            f"No Employee linked to User '{username}' (email={user_email})"
        )

    return employee
def _resolve_master(doctype, value):
    """Return the existing master name for `value` in `doctype`, or None if missing.

    Lookup is case-insensitive and trimmed. Empty/None values return None.
    """
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

    # Match on either the doc's primary name or its label field (case-insensitive).
    rows = frappe.get_all(doctype, fields=[name_field, label_field])
    for row in rows:
        if candidate.lower() == (row.get(name_field) or "").lower():
            return row.get(name_field)
        if candidate.lower() == (row.get(label_field) or "").lower():
            return row.get(name_field)
    return None


@frappe.whitelist()
def sync_employee_master(**kwargs):
    """Bulk-sync employee fields from the HMIS master website.

    Accepts:
        {
          "updates": [
            {"username": "Drneelamk", "employment_type": "Contract"},
            {"username": "manojk", "employment_type": "Permanent"}
          ]
        }

    Lookup chain: username (User.name) -> User.email -> Employee.user_id -> Employee.name.

    Returns:
        Summary with totals + per-record success/error log. One bad record never
        aborts the batch.
    """
    try:
        payload = frappe.request.get_json(silent=True) or kwargs or {}
        updates = _extract_updates(payload)

    except Exception as e:
        _audit_log(
            "sync_employee_master: fatal payload parse error",
            f"Caller: {frappe.session.user if frappe.session else 'guest'}\n"
            f"Error: {str(e)}",
        )
        raise

    # ------------------------------------------------------------------
    # Audit log #1: API entered. Captures the raw payload, caller, and
    # remote address so support can trace every HMIS call.
    # ------------------------------------------------------------------
    caller = frappe.session.user if frappe.session else "guest"
    remote_addr = getattr(frappe.request, "remote_addr", None) or "unknown"
    _audit_log(
        "sync_employee_master: payload received",
        f"Caller: {caller}\n"
        f"Remote: {remote_addr}\n"
        f"Method: {frappe.request.method if frappe.request else 'unknown'}\n"
        f"Update count: {len(updates)}\n"
        f"Method: {frappe.request.method if frappe.request else 'unknown'}\n"
        f"Payload: {frappe.as_json(payload, indent=2)}",
    )

    if not updates:
        _audit_log(
            "sync_employee_master: empty payload",
            f"Caller: {caller}\nRemote: {remote_addr}\n"
            f"Payload was non-JSON or contained no 'updates' array.",
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
                        master_name = _resolve_master(target_field, value)
                        if not master_name:
                            record_errors.append(
                                f"{source_field} '{value}' not found in {target_field} master; skipped"
                            )
                            continue
                        updates_to_apply[target_field] = master_name
                    else:
                        updates_to_apply[target_field] = value

                if not updates_to_apply:
                    raise ValueError("No supported fields supplied for update")

                (
                    frappe.qb.update("Employee")
                    .set(updates_to_apply)
                    .where(frappe.qb.Field("name") == employee_id)
                    .run()
                )

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
            f"Caller: {caller}\n"
            f"Remote: {remote_addr}\n"
            f"Total: {total} | Success so far: {success} | Failed so far: {failed}\n"
            f"Error: {str(e)}",
        )
        raise

    frappe.db.commit()

    # ------------------------------------------------------------------
    # Audit log #2: API completed. Records outcome so success and failure
    # rates are visible without parsing each record's error_log.
    # ------------------------------------------------------------------
    _audit_log(
        "sync_employee_master: completed",
        f"Caller: {caller}\n"
        f"Remote: {remote_addr}\n"
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
        # If the log itself fails (DB down, etc.) don't take down the request.
        pass


# Extensible field map: HMIS master field name -> Employee doctype field name.
# Add new entries here to sync additional fields without changing the API contract.
FIELD_MAP = {
    "employment_type": "employment_type",
    "designation": "designation",
    "department": "department",
    "branch": "branch",
}

# Fields whose values must match an existing master record. If the supplied value
# does not resolve, the field is silently skipped and logged.
MASTER_LINK_FIELDS = {"designation", "department", "branch"}

# HMIS-side labels -> Frappe Employment Type names.
# Lookup is case-insensitive after stripping. Unmapped values pass through and
# are validated against the Employment Type doctype like other link fields.
EMPLOYMENT_TYPE_ALIASES = {
    "permanent": "Full-time",
    "full-time": "Full-time",
    "fulltime": "Full-time",
    "contract": "Contract",
}


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


def _resolve_employee_id(username):
    """Resolve a username (User.name) -> Employee.name via User.email -> Employee.user_id."""
    username = (username or "").strip()
    if not username:
        raise ValueError("username is required")

    user_email = frappe.db.get_value("User", {"name": username}, "email")
    if not user_email:
        raise ValueError(f"No User found with username '{username}'")

    employee = frappe.db.get_value(
        "Employee",
        {"user_id": user_email},
        "name",
    )
    if not employee:
        raise ValueError(
            f"No Employee linked to User '{username}' (email={user_email})"
        )

    return employee
def _resolve_master(doctype, value):
    """Return the existing master name for `value` in `doctype`, or None if missing.

    Lookup is case-insensitive and trimmed. Empty/None values return None.
    """
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

    # Match on either the doc's primary name or its label field (case-insensitive).
    rows = frappe.get_all(doctype, fields=[name_field, label_field])
    for row in rows:
        if candidate.lower() == (row.get(name_field) or "").lower():
            return row.get(name_field)
        if candidate.lower() == (row.get(label_field) or "").lower():
            return row.get(name_field)
    return None


@frappe.whitelist()
def sync_employee_master(**kwargs):
    """Bulk-sync employee fields from the HMIS master website.

    Accepts:
        {
          "updates": [
            {"username": "Drneelamk", "employment_type": "Contract"},
            {"username": "manojk", "employment_type": "Permanent"}
          ]
        }

    Lookup chain: username (User.name) -> User.email -> Employee.user_id -> Employee.name.

    Returns:
        Summary with totals + per-record success/error log. One bad record never
        aborts the batch.
    """
    try:
        payload = frappe.request.get_json(silent=True) or kwargs or {}
        updates = _extract_updates(payload)

    except Exception as e:
        _audit_log(
            "sync_employee_master: fatal payload parse error",
            f"Caller: {frappe.session.user if frappe.session else 'guest'}\n"
            f"Error: {str(e)}",
        )
        raise

    # ------------------------------------------------------------------
    # Audit log #1: API entered. Captures the raw payload, caller, and
    # remote address so support can trace every HMIS call.
    # ------------------------------------------------------------------
    caller = frappe.session.user if frappe.session else "guest"
    remote_addr = getattr(frappe.request, "remote_addr", None) or "unknown"
    _audit_log(
        "sync_employee_master: payload received",
        f"Caller: {caller}\n"
        f"Remote: {remote_addr}\n"
        f"Method: {frappe.request.method if frappe.request else 'unknown'}\n"
        f"Update count: {len(updates)}\n"
        f"Method: {frappe.request.method if frappe.request else 'unknown'}\n"
        f"Payload: {frappe.as_json(payload, indent=2)}",
    )

    if not updates:
        _audit_log(
            "sync_employee_master: empty payload",
            f"Caller: {caller}\nRemote: {remote_addr}\n"
            f"Payload was non-JSON or contained no 'updates' array.",
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
                        master_name = _resolve_master(target_field, value)
                        if not master_name:
                            record_errors.append(
                                f"{source_field} '{value}' not found in {target_field} master; skipped"
                            )
                            continue
                        updates_to_apply[target_field] = master_name
                    else:
                        updates_to_apply[target_field] = value

                if not updates_to_apply:
                    raise ValueError("No supported fields supplied for update")

                (
                    frappe.qb.update("Employee")
                    .set(updates_to_apply)
                    .where(frappe.qb.Field("name") == employee_id)
                    .run()
                )

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
            f"Caller: {caller}\n"
            f"Remote: {remote_addr}\n"
            f"Total: {total} | Success so far: {success} | Failed so far: {failed}\n"
            f"Error: {str(e)}",
        )
        raise

    frappe.db.commit()

    # ------------------------------------------------------------------
    # Audit log #2: API completed. Records outcome so success and failure
    # rates are visible without parsing each record's error_log.
    # ------------------------------------------------------------------
    _audit_log(
        "sync_employee_master: completed",
        f"Caller: {caller}\n"
        f"Remote: {remote_addr}\n"
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