import frappe

# Extensible field map: HMIS master field name -> Employee doctype field name.
FIELD_MAP = {
    "employment_type": "employment_type",
    "designation": "designation",
    "department": "department",
    "branch": "branch",
}

# Fields whose values must match an existing master record.
MASTER_LINK_FIELDS = {"designation", "department", "branch"}

# HMIS-side labels -> Frappe Employment Type names.
EMPLOYMENT_TYPE_ALIASES = {
    "permanent": "Full-time",
    "full-time": "Full-time",
    "fulltime": "Full-time",
    "contract": "Contract",
    "contractual":"Contract"
}


def generate_normalized_username(user_id_input):
    """Matches the custom_login pattern for username/email generation."""
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
    """
    Resolve identifier using the normalized custom_login pattern.
    Checks:
    1. Direct match on Employee Name (e.g., EMP-001)
    2. Normalized username/email match in User Doctype -> Employee.user_id
    3. Direct user_id match on Employee Doctype
    """
    raw_id = (identifier or "").strip()
    if not raw_id:
        raise ValueError("username / employee ID is required")

    # 1. Direct match on Employee primary key (e.g., EMP-001)
    if frappe.db.exists("Employee", raw_id):
        return raw_id

    # Normalize user ID per your custom login pattern (e.g., 'Ultimas@123' -> 'Ultimas@123@bmcinternal.com')
    normalized_user = generate_normalized_username(raw_id)

    # 2. Check if User exists by name or email with normalized string
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
        # Lookup Employee by user_id linked to User's email/name
        employee = frappe.db.get_value(
            "Employee",
            {"user_id": user_record.email or user_record.name},
            "name"
        )
        if employee:
            return employee

    # 3. Direct match on Employee.user_id with normalized username
    employee = frappe.db.get_value("Employee", {"user_id": normalized_user}, "name")
    if employee:
        return employee

    raise ValueError(f"No Employee found matching '{raw_id}' (normalized: '{normalized_user}')")


def _resolve_master(doctype, value):
    """Return the existing master name for `value` in `doctype`, or None if missing."""
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
    # Force execution context to Administrator
    frappe.set_user("Administrator")

    payload = frappe.request.get_json(silent=True) or kwargs or {}
    updates = _extract_updates(payload)

    if not updates:
        frappe.throw("Payload must include a non-empty 'updates' array")

    total = len(updates)
    success = 0
    failed = 0
    error_log = []

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

            # ONLY THIS PART CHANGED TO FIX THE DATABASE ERROR SAFELY
            doc = frappe.get_doc("Employee", employee_id)
            doc.update(updates_to_apply)
            doc.save(ignore_permissions=True)

            if record_errors:
                error_log.append({
                    "username": username,
                    "status": "partial",
                    "message": "; ".join(record_errors),
                })
            success += 1

        except Exception as e:
            failed += 1
            error_log.append({
                "username": username,
                "status": "error",
                "message": str(e),
            })

    frappe.db.commit()

    return {
        "status": "ok",
        "caller": frappe.session.user,
        "total": total,
        "success": success,
        "failed": failed,
        "errors": error_log,
    }