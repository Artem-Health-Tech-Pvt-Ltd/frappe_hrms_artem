"""Wipe and recreate the Employee Lifecycle workspace.

Like the BMC HRMS pattern: existing rows (Workspace doc, sidebar row,
User Permissions, Desktop Icon) are deleted first, then a fresh
workspace is built. This guarantees the patch output matches the
code's view of the workspace on every run.
"""
import json

import frappe

WORKSPACE_NAME = "Employee Lifecycle"
APP_NAME = "artem_hrms"
LOGO_URL = f"/assets/{APP_NAME}/images/bmc_hr_logo.png"


LIFECYCLE_CARDS = [
    ("Onboarding", "user-plus", [
        ("Employee Onboarding", "DocType", "Employee Onboarding"),
    ]),
    ("Promotion", "trending-up", [
        ("Employee Promotion", "DocType", "Employee Promotion"),
    ]),
    ("Separation", "user-minus", [
        ("Employee Separation", "DocType", "Employee Separation"),
        ("Employee Transfer", "DocType", "Employee Transfer"),
    ]),
    ("Other", "shield", [
        ("Employee Grievance", "DocType", "Employee Grievance"),
        ("Employee Health Insurance", "DocType", "Employee Health Insurance"),
        ("Employee Skill Map", "DocType", "Employee Skill Map"),
    ]),
]


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
    workspace.icon = "milestone"
    workspace.sequence_id = 102.0
    workspace.module = ""
    workspace.app = APP_NAME
    workspace.extend("roles", [
        {"role": "HR User"},
        {"role": "HR Manager"},
        {"role": "System Manager"},
    ])

    idx = 1
    for card_label, card_icon, links in LIFECYCLE_CARDS:
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
            "id": "bmc-lifecycle-h",
            "type": "header",
            "data": {
                "text": '<span class="h3"><b>Employee Lifecycle</b></span>',
                "col": 12,
            },
        },
    ]
    for card_label, _, _ in LIFECYCLE_CARDS:
        content_blocks.append({
            "id": "card-" + card_label.lower().replace(" ", "-"),
            "type": "card",
            "data": {"card_name": card_label, "col": 4},
        })
    workspace.content = json.dumps(content_blocks)

    workspace.insert(ignore_permissions=True)
    return workspace


def _create_desktop_icon():
    if frappe.db.exists("Desktop Icon", {"label": WORKSPACE_NAME}):
        frappe.db.delete("Desktop Icon", {"label": WORKSPACE_NAME})
    icon_doc = frappe.new_doc("Desktop Icon")
    icon_doc.label = WORKSPACE_NAME
    icon_doc.module_name = "HR"
    icon_doc.app = APP_NAME
    icon_doc.icon_type = "Link"
    icon_doc.icon = "milestone"
    icon_doc.logo_url = LOGO_URL
    icon_doc.route = f"/desk/{frappe.scrub(WORKSPACE_NAME)}"
    icon_doc.link_type = "External"
    icon_doc.external_link = f"/desk/{frappe.scrub(WORKSPACE_NAME)}"
    icon_doc.standard = 0
    icon_doc.insert(ignore_permissions=True)


def execute():
    _wipe(WORKSPACE_NAME)
    _create_workspace()
    _create_desktop_icon()
    frappe.db.commit() # nosemgrep
    try:
        frappe.cache.delete_keys("bootinfo:*")
    except Exception:
        frappe.cache.delete_key("bootinfo")
    frappe.cache.delete_key("desk_sidebar_items")
    frappe.cache.delete_key("get_sidebar_items")
    print(
        f"Workspace '{WORKSPACE_NAME}' wiped and recreated with "
        f"{len(LIFECYCLE_CARDS)} cards."
    )
