import frappe


# Extensible field map: HMIS master field name -> Employee doctype field name.
# Add new entries here to sync additional fields without changing the API contract.
FIELD_MAP = {
    "employment_type": "employment_type",
    "designation": "designation",
    "department": "department",
    "branch": "branch",
    "ao_id": "custom_ao_id",
    "hod_id": "custom_hod_id",
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


@frappe.whitelist(allow_guest=False)
def sync_employee_master(**kwargs):
    """Bulk-sync employee fields from the HMIS master website.

    Accepts:
        {
          "updates": [
            {"username": "EMP-001", "employment_type": "Contract"},
            {"username": "EMP-002", "employment_type": "Permanent"}
          ]
        }

    Lookup chain: username (User.name) -> User.email -> Employee.user_id -> Employee.name.

    Returns:
        Summary with totals + per-record success/error log. One bad record never
        aborts the batch.
    """
    payload = frappe.request.get_json(silent=True) or kwargs or {}
    updates = _extract_updates(payload)

    if not updates:
        frappe.throw("Payload must include a non-empty 'updates' array")

    total = len(updates)
    success = 0
    failed = 0
    error_log = []

    for record in updates:
        username = (record.get("username") or "").strip()
        try:
            employee_id = _resolve_employee_id(username)

            updates_to_apply = {}
            for source_field, target_field in FIELD_MAP.items():
                if source_field in record and record[source_field] is not None:
                    updates_to_apply[target_field] = record[source_field]

            if not updates_to_apply:
                raise ValueError("No supported fields supplied for update")

            (
                frappe.qb.update("Employee")
                .set(updates_to_apply)
                .where(frappe.qb.Field("name") == employee_id)
                .run()
            )

            success += 1

        except Exception as e:
            failed += 1
            error_log.append({
                "username": username or record.get("username"),
                "status": "error",
                "message": str(e),
            })

    frappe.db.commit()

    return {
        "status": "ok",
        "total": total,
        "success": success,
        "failed": failed,
        "errors": error_log,
    }