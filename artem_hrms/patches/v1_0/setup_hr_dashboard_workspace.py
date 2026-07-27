"""Create the HR Dashboard workspace with cards + desktop icon.

Idempotent: if the workspace already exists, this patch is a no-op for
content/links/roles (the user may have customised them via the UI). The
desktop icon is always re-created since it's purely a routing hook.

Mirrors the Employee Lifecycle pattern: header + cards on the page body.
"""
import json

import frappe

WORKSPACE_NAME = "HR Dashboard"
APP_NAME = "artem_hrms"
LOGO_URL = f"/assets/{APP_NAME}/images/bmc_hr_logo.png"


# Cards for the HR Dashboard page. HR-relevant metrics + actions.
# (card_label, icon, [(link_label, link_type, link_to), ...])
HR_DASHBOARD_CARDS = [
    ("Headcount", "users", [
        ("Employee", "DocType", "Employee"),
        ("Department", "DocType", "Department"),
        ("Designation", "DocType", "Designation"),
    ]),
    ("Attendance", "calendar-check", [
        ("Attendance", "DocType", "Attendance"),
        ("Attendance Request", "DocType", "Attendance Request"),
        ("Employee Checkin", "DocType", "Employee Checkin"),
    ]),
    ("Leave", "calendar-minus", [
        ("Leave Application", "DocType", "Leave Application"),
        ("Leave Allocation", "DocType", "Leave Allocation"),
    ]),
    ("Payroll", "money-coins-1", [
        ("Salary Slip", "DocType", "Salary Slip"),
        ("Salary Structure", "DocType", "Salary Structure"),
        ("Payroll Entry", "DocType", "Payroll Entry"),
    ]),
    ("Expense", "wallet", [
        ("Expense Claim", "DocType", "Expense Claim"),
    ]),
    ("Lifecycle", "milestone", [
        ("Employee Promotion", "DocType", "Employee Promotion"),
        ("Employee Separation", "DocType", "Employee Separation"),
        ("Employee Onboarding", "DocType", "Employee Onboarding"),
        ("Employee Transfer", "DocType", "Employee Transfer"),
    ]),
]


def _create_workspace():
    """HR Dashboard - header + cards on the page."""
    workspace = frappe.new_doc("Workspace")
    workspace.name = WORKSPACE_NAME
    workspace.title = WORKSPACE_NAME
    workspace.label = WORKSPACE_NAME
    workspace.public = 1
    workspace.for_user = ""
    workspace.icon = "layout-dashboard"
    workspace.sequence_id = 103.0
    workspace.module = ""
    workspace.app = APP_NAME
    workspace.extend("roles", [
        {"role": "HR User"},
        {"role": "HR Manager"},
        {"role": "System Manager"},
    ])

    idx = 1
    for card_label, card_icon, links in HR_DASHBOARD_CARDS:
        workspace.append(
            "links",
            {
                "type": "Card Break",
                "label": card_label,
                "icon": card_icon,
                "link_count": len(links),
                "idx": idx,
            },
        )
        idx += 1
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
            "id": "bmc-hr-h",
            "type": "header",
            "data": {
                "text": '<span class="h3"><b>HR Dashboard</b></span>',
                "col": 12,
            },
        },
    ]
    for card_label, _, _ in HR_DASHBOARD_CARDS:
        content_blocks.append({
            "id": "card-" + card_label.lower().replace(" ", "-"),
            "type": "card",
            "data": {"card_name": card_label, "col": 4},
        })
    workspace.content = json.dumps(content_blocks)

    workspace.insert(ignore_permissions=True)
    return workspace


def _create_desktop_icon():
    """Desktop Icon for /desk/hr-dashboard. Uses External + internal route
    to bypass the Workspace Sidebar requirement."""
    if frappe.db.exists("Desktop Icon", {"label": WORKSPACE_NAME}):
        frappe.db.delete("Desktop Icon", {"label": WORKSPACE_NAME})
    icon_doc = frappe.new_doc("Desktop Icon")
    icon_doc.label = WORKSPACE_NAME
    icon_doc.module_name = ""
    icon_doc.app = APP_NAME
    icon_doc.icon_type = "Link"
    icon_doc.icon = "layout-dashboard"
    icon_doc.logo_url = LOGO_URL
    icon_doc.route = f"/desk/{frappe.scrub(WORKSPACE_NAME)}"
    icon_doc.link_type = "External"
    icon_doc.external_link = f"/desk/{frappe.scrub(WORKSPACE_NAME)}"
    icon_doc.standard = 0
    icon_doc.insert(ignore_permissions=True)


def execute():
    # Idempotent: skip recreation if the workspace already exists.
    if frappe.db.exists("Workspace", WORKSPACE_NAME):
        print(
            f"Workspace '{WORKSPACE_NAME}' already exists - skipping "
            f"recreation. The desktop icon is still re-wired."
        )
    else:
        _create_workspace()
        print(f"Workspace '{WORKSPACE_NAME}' created with {len(HR_DASHBOARD_CARDS)} cards.")

    # Always re-wire the desktop icon.
    _create_desktop_icon()

    frappe.db.commit()
    try:
        frappe.cache.delete_keys("bootinfo:*")
    except Exception:
        frappe.cache.delete_key("bootinfo")
    frappe.cache.delete_key("desk_sidebar_items")
    frappe.cache.delete_key("get_sidebar_items")
    print(
        f"Workspace '{WORKSPACE_NAME}' (idempotent) processed, "
        f"desktop icon wired to /desk/{frappe.scrub(WORKSPACE_NAME)}."
    )
