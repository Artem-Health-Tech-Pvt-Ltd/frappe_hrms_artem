"""Create the BMC HRMS workspace and its sidebar (no module / no app).

Safe to re-run: existing rows are deleted before recreate.
"""
import frappe

WORKSPACE_NAME = "BMC HRMS"
APP_NAME = "artem_hrms"


def _wipe_existing():
    """Wipe any prior state so we can recreate cleanly.

    Drops User Permissions and UnBlock-style references first so the Workspace
    row can be force-deleted without LinkExistsError. Also clears the Workspace
    Sidebar even if the Workspace itself has stale content that block deletes.
    """
    for up in frappe.get_all(
        "User Permission",
        filters={"allow": "Workspace", "for_value": WORKSPACE_NAME},
        pluck="name",
    ):
        try:
            frappe.delete_doc("User Permission", up, force=1, ignore_permissions=True)
        except Exception:
            pass

    # Drop the sidebar first so nothing references the workspace we are deleting.
    if frappe.db.exists("Workspace Sidebar", WORKSPACE_NAME):
        try:
            frappe.delete_doc(
                "Workspace Sidebar", WORKSPACE_NAME, force=1, ignore_permissions=True
            )
        except Exception:
            pass

    if frappe.db.exists("Workspace", WORKSPACE_NAME):
        try:
            frappe.delete_doc(
                "Workspace", WORKSPACE_NAME, force=1, ignore_permissions=True
            )
        except Exception:
            # Last resort: if a doc link still exists, drop the row directly.
            frappe.db.delete("Workspace", {"name": WORKSPACE_NAME})

    # Drop any stale Desktop Icon pointing at the workspace.
    if frappe.db.exists("Desktop Icon", {"label": WORKSPACE_NAME}):
        try:
            frappe.delete_doc(
                "Desktop Icon", WORKSPACE_NAME, force=1, ignore_permissions=True
            )
        except Exception:
            frappe.db.delete("Desktop Icon", {"label": WORKSPACE_NAME})

    # Also empty workspace.content in case the recreate path still leaves one.
    frappe.db.sql(
        "UPDATE `tabWorkspace` SET content = %s WHERE name = %s",
        ("[]", WORKSPACE_NAME),
    )


def _ensure_links(workspace):
    workspace.append(
        "links",
        {
            "type": "Card Break",
            "label": "HR",
            "icon": "users",
        },
    )
    for label, link_to in [
        ("Employee", "Employee"),
        ("Employee Checkin", "Employee Checkin"),
        ("Attendance", "Attendance"),
        ("Leave Application", "Leave Application"),
        ("Shift Assignment", "Shift Assignment"),
    ]:
        workspace.append(
            "links",
            {
                "type": "Link",
                "label": label,
                "link_type": "DocType",
                "link_to": link_to,
                "link_count": 0,
                "icon": "file",
            },
        )


# def _ensure_shortcuts(workspace):
#     for label, link_to in [
#         ("Attendance", "Attendance"),
#         ("Leave Application", "Leave Application"),
#         ("Employee", "Employee"),
#     ]:
#         workspace.append(
#             "shortcuts",
#             {
#                 "type": "DocType",
#                 "label": label,
#                 "link_to": link_to,
#             },
#         )


def _create_workspace():
    workspace = frappe.new_doc("Workspace")
    workspace.name = WORKSPACE_NAME
    workspace.title = WORKSPACE_NAME
    workspace.label = WORKSPACE_NAME
    workspace.public = 1
    workspace.for_user = ""
    workspace.is_standard = 0
    workspace.icon = "users"
    workspace.sequence_id = 100.0
    workspace.module = ""
    workspace.app = ""
    workspace.content = "[]"
    # Intentionally not calling _ensure_links: the page renderer converts
    # Workspace.links into Editor.js blocks, which renders as "block can not
    # be displayed correctly" in Frappe 16. Sidebar items handle navigation,
    # so the workspace page body is intentionally left empty for the user
    # to populate via the UI.
    workspace.insert(ignore_permissions=True)
    # Belt-and-braces: also zero content via SQL so an old value cannot survive
    # in the in-memory doc due to any framework-triggered recompute.
    frappe.db.sql(
        "UPDATE `tabWorkspace` SET content = %s WHERE name = %s",
        ("[]", workspace.name),
    )
    return workspace


LOGO_REL_PATH = "public/images/bmc_hr_logo.png"
LOGO_URL = f"/assets/{APP_NAME}/images/bmc_hr_logo.png"


def _apply_logo():
    """Wire bmc_hr_logo.png to the Desktop Icon tile via logo_url.

    Workspace.icon is a Frappe-hex Icon field, so it stays as 'users'.
    Desktop Icon.logo_url accepts a URL and renders the actual image on /desk.
    """
    if frappe.db.exists("Desktop Icon", WORKSPACE_NAME):
        frappe.db.set_value(
            "Desktop Icon",
            WORKSPACE_NAME,
            {"icon": "users", "logo_url": LOGO_URL},
            update_modified=False,
        )


import json

def _build_content():
    blocks = [
        {
            "type": "card_break", # Note: v16 uses lowercase snake_case for types
            "data": {"label": "HR", "icon": "users"}
        },
        {
            "type": "link",
            "data": {"link_type": "DocType", "link_to": "Employee", "label": "Employee"}
        }
    ]
    # This must be a stringified JSON
    return json.dumps(blocks)

# def _build_content():
#     cards = [
#         {
#             "type": "Card Break",
#             "label": "HR",
#             "icon": "users",
#             "links": [
#                 {"type": "Link", "label": "Employee", "link_type": "DocType", "link_to": "Employee"},
#                 {"type": "Link", "label": "Employee Checkin", "link_type": "DocType", "link_to": "Employee Checkin"},
#                 {"type": "Link", "label": "Attendance", "link_type": "DocType", "link_to": "Attendance"},
#                 {"type": "Link", "label": "Leave Application", "link_type": "DocType", "link_to": "Leave Application"},
#                 {"type": "Link", "label": "Shift Assignment", "link_type": "DocType", "link_to": "Shift Assignment"},
#             ],
#         }
#     ]
#     blocks = []
#     for card in cards:
#         blocks.append({"type": "Card Break", "label": card["label"], "icon": card["icon"]})
#         for link in card["links"]:
#             blocks.append({"type": "Link", **link})
#     blocks.append(
#         {
#             "type": "Shortcut Block",
#             "label": "Quick Access",
#             "shortcuts": [
#                 {"type": "DocType", "label": "Attendance", "link_to": "Attendance"},
#                 {"type": "DocType", "label": "Leave Application", "link_to": "Leave Application"},
#                 {"type": "DocType", "label": "Employee", "link_to": "Employee"},
#             ],
#         }
#     )
#     return blocks


def _create_desktop_icon():
    if frappe.db.exists("Desktop Icon", {"label": WORKSPACE_NAME}):
        frappe.db.delete("Desktop Icon", {"label": WORKSPACE_NAME})
    icon = frappe.new_doc("Desktop Icon")
    icon.label = WORKSPACE_NAME
    icon.module_name = ""
    icon.app = APP_NAME
    icon.icon_type = "Link"
    icon.icon = "users"
    icon.route = f"/desk/{frappe.scrub(WORKSPACE_NAME)}"
    icon.link_type = "Workspace Sidebar"
    icon.link_to = WORKSPACE_NAME
    icon.standard = 0
    icon.insert(ignore_permissions=True)


def _create_sidebar(workspace):
    sidebar = frappe.new_doc("Workspace Sidebar")
    sidebar.title = WORKSPACE_NAME
    sidebar.app = APP_NAME
    sidebar.module = ""
    sidebar.header_icon = "users"
    sidebar.append(
        "items",
        {
            "type": "Section Break",
            "label": "HR",
            "icon": "users",
            "idx": 1,
            "collapsible": 1,
        },
    )
    hr_docs = [
        ("Employee", "Employee"),
        ("Employee Checkin", "Employee Checkin"),
        ("Attendance", "Attendance"),
        ("Leave Application", "Leave Application"),
        ("Shift Assignment", "Shift Assignment"),
    ]
    for idx, (label, link_to) in enumerate(hr_docs, start=2):
        sidebar.append(
            "items",
            {
                "type": "Link",
                "label": label,
                "link_type": "DocType",
                "link_to": link_to,
                "icon": "file",
                "idx": idx,
            },
        )
    sidebar.append(
        "items",
        {
            "type": "Section Break",
            "label": "Reports",
            "icon": "list",
            "idx": 99,
            "collapsible": 1,
        },
    )
    sidebar.append(
        "items",
        {
            "type": "Link",
            "label": "Employee Leave Balance",
            "link_type": "Report",
            "link_to": "Employee Leave Balance",
            "icon": "table",
            "idx": 100,
        },
    )
    sidebar.insert(ignore_permissions=True)
    return sidebar


def execute():
    _wipe_existing()
    workspace = _create_workspace()
    _create_sidebar(workspace)
    _create_desktop_icon()
    _apply_logo()
    frappe.db.commit()
    # Clear every bootinfo cache key so all users pick up the fresh Workspace row.
    try:
        frappe.cache.delete_keys("bootinfo:*")
    except Exception:
        frappe.cache.delete_key("bootinfo")
    frappe.cache.delete_key("desk_sidebar_items")
    frappe.cache.delete_key("get_sidebar_items")
    print(f"Workspace '{WORKSPACE_NAME}', sidebar, and desktop icon are in place.")