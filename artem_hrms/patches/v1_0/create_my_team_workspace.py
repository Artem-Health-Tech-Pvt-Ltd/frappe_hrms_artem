"""Build the My Team workspace from code.

Mirrors the BMC HRMS / BMC Attendance pattern: wipe any existing
state, then build a fresh Workspace doc. The role allowlist matches
BMC Attendance / Employee Lifecycle (HR User, HR Manager, System
Manager) so plain Employees don't see it.

The workspace is built in code (no fixture JSON), so `bench migrate`
orphan-cleanup won't see a stale json path and try to delete it.
"""
import json

import frappe

WORKSPACE_NAME = "My Team"
APP_NAME = "artem_hrms"


def _wipe(name):
    for up in frappe.get_all(
        "User Permission",
        filters={"allow": "Workspace", "for_value": name},
        pluck="name",
    ):
        try:
            frappe.delete_doc("User Permission", up, force=1, ignore_permissions=True)
        except Exception:
            pass

    if frappe.db.exists("Workspace Sidebar", name):
        try:
            frappe.delete_doc("Workspace Sidebar", name, force=1, ignore_permissions=True)
        except Exception:
            pass

    if frappe.db.exists("Workspace", name):
        try:
            frappe.delete_doc("Workspace", name, force=1, ignore_permissions=True)
        except Exception:
            frappe.db.delete("Workspace", {"name": name})

    if frappe.db.exists("Desktop Icon", {"label": name}):
        try:
            frappe.delete_doc("Desktop Icon", name, force=1, ignore_permissions=True)
        except Exception:
            frappe.db.delete("Desktop Icon", {"label": name})


def _create_workspace():
    workspace = frappe.new_doc("Workspace")
    workspace.name = WORKSPACE_NAME
    workspace.title = WORKSPACE_NAME
    workspace.label = WORKSPACE_NAME
    workspace.public = 1
    workspace.for_user = ""
    workspace.icon = "users"
    workspace.sequence_id = 50.0
    # app="" and module="" so the post-migrate orphan-cleanup filter
    # (which matches on `app is set` + `module is set`) skips this doc
    # even when no fixture file claims it. We manage the workspace
    # entirely from this patch.
    workspace.app = ""
    workspace.module = ""
    workspace.parent_page = "BMC HRMS"
    workspace.extend("roles", [
        {"role": "HR User"},
        {"role": "HR Manager"},
        {"role": "System Manager"},
    ])

    # Links table - drives page_data.cards on the JS side. Cards let the
    # user click through to Employee list and key reports about the team.
    # Three Card Break rows (Team / Quick Actions / Reports) so the row
    # sums to 12 columns at col-md-4 each — same pattern as Employee
    # Lifecycle's recreate_employee_lifecycle_workspace.py.
    idx = 1
    for card_label, icon, link_count in [
        ("Team", "users", 3),
        ("Quick Actions", "zap", 3),
        ("Reports", "bar-chart-2", 2),
    ]:
        workspace.append(
            "links",
            {
                "type": "Card Break",
                "label": card_label,
                "icon": icon,
                "link_count": link_count,
                "idx": idx,
            },
        )
        idx += 1

    link_rows = [
        ("Team", [
            ("Employees", "DocType", "Employee"),
            ("Attendance", "DocType", "Attendance"),
            ("Leave Application", "DocType", "Leave Application"),
        ]),
        ("Quick Actions", [
            ("Mark Attendance", "DocType", "Attendance"),
            ("Shift Assignment", "DocType", "Shift Assignment"),
            ("Employee CheckIn", "DocType", "Employee CheckIn"),
        ]),
        ("Reports", [
            ("Attendance Report", "DocType", "Attendance Report"),
            ("Employee Leave Balance", "DocType", "Employee Leave Balance"),
        ]),
    ]
    for card_label, links in link_rows:
        for link_label, link_type, link_to in links:
            workspace.append(
                "links",
                {
                    "type": "Link",
                    "label": link_label,
                    "link_type": link_type,
                    "link_to": link_to,
                    "link_count": 0,
                    "idx": idx,
                },
            )
            idx += 1

    content_blocks = [
        {
            "id": "card-" + slug,
            "type": "card",
            "data": {"card_name": label, "col": 4},
        }
        for label, _ in link_rows
        for slug in [label.lower().replace(" ", "-")]
    ]
    content_blocks.append(
        {
            "id": "myteam-numcard-total",
            "type": "number_card",
            "data": {"number_card_name": "Total Employees", "col": 12},
        },
    )
    workspace.content = json.dumps(content_blocks)
    workspace.append(
        "number_cards",
        {"number_card_name": "Total Employees", "label": "Total Employees"},
    )
    workspace.flags.ignore_links = True
    workspace.insert(ignore_permissions=True)
    return workspace


def _ensure_number_card():
    """Create a 'Total Employees' number card if it doesn't exist.

    Counts Employee records (status = Active) so HR sees the live headcount
    at a glance on the My Team workspace.
    """
    card_name = "Total Employees"
    if frappe.db.exists("Number Card", card_name):
        frappe.db.set_value(
            "Number Card",
            card_name,
            {
                "document_type": "Employee",
                "label": card_name,
                "function": "Count",
                "is_standard": 0,
                "show_full_number": 0,
                "filters_json": json.dumps([["Employee", "status", "=", "Active", False]]),
            },
            update_modified=False,
        )
        return

    card = frappe.new_doc("Number Card")
    card.name = card_name
    card.label = card_name
    card.document_type = "Employee"
    card.function = "Count"
    card.is_standard = 0
    card.show_full_number = 0
    card.filters_json = json.dumps([["Employee", "status", "=", "Active", False]])
    card.insert(ignore_permissions=True)


def execute():
    _wipe(WORKSPACE_NAME)
    _ensure_number_card()
    _create_workspace()
    frappe.db.commit() # nosemgrep
    try:
        frappe.cache.delete_keys("bootinfo:*")
        frappe.cache.delete_keys("document:*")
    except Exception:
        pass
    print(
        f"Workspace '{WORKSPACE_NAME}' wiped and rebuilt with role "
        f"allowlist: HR User, HR Manager, System Manager. Total Employees "
        f"number card attached."
    )
