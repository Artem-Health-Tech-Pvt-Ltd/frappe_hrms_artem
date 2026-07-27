"""Create the BMC HRMS workspace, BMC Attendance workspace, sidebar, and
desktop icon. Layered on top of v1.

Safe to re-run: existing rows are deleted before recreate.
"""
import json

import frappe

WORKSPACE_NAME = "BMC HRMS"
ATTENDANCE_WORKSPACE_NAME = "BMC Attendance"
LIFECYCLE_WORKSPACE_NAME = "Employee Lifecycle"
APP_NAME = "artem_hrms"
LOGO_URL = f"/assets/{APP_NAME}/images/bmc_hr_logo.png"


def _wipe(name):
    """Wipe workspace + sidebar + desktop icon for the given workspace name."""
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

    frappe.db.sql(
        "UPDATE `tabWorkspace` SET content = %s WHERE name = %s",
        ("[]", name),
    )


# Cards on the BMC HRMS home page (mirrors Employee Dashboard).
# (card_label, icon, [(link_label, link_type, link_to), ...])
HRMS_CARDS = [
    ("Attendance", "calendar-check", [
        ("Attendance Request", "DocType", "Attendance Request"),
        ("Employee Checkin", "DocType", "Employee Checkin"),
    ]),
    ("Shift", "shift", [
        ("Shift Assignment", "DocType", "Shift Assignment"),
        ("Shift Request", "DocType", "Shift Request"),
    ]),
    ("Leave", "calendar-minus", [
        ("Leave Application", "DocType", "Leave Application"),
    ]),
    # ("Custom Reports", "list", [
    #     ("palalvi", "DocType", "Employee"),
    #     ("Shift Summary", "DocType", "Shift Assignment"),
    # ]),
]


def _create_bmc_hrms_workspace():
    """BMC HRMS - welcome header + 4 cards on the home page.

    Card Breaks live in the `links` child table (drives page_data.cards).
    Card blocks in `content` reference them by card_name so Editor.js
    renders them as visible cards.
    """
    workspace = frappe.new_doc("Workspace")
    workspace.name = WORKSPACE_NAME
    workspace.title = WORKSPACE_NAME
    workspace.label = WORKSPACE_NAME
    workspace.public = 1
    workspace.for_user = ""
    workspace.icon = "users"
    workspace.sequence_id = 100.0
    workspace.module = ""
    workspace.app = ""

    # Links table - Card Break + Link rows feed page_data.cards on the JS side.
    idx = 1
    for card_label, card_icon, links in HRMS_CARDS:
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

    # Content - header + paragraph + 4 card blocks. Each card block
    # has a unique id (so Editor.js doesn't double-render) and a
    # card_name matching the Card Break label in the links table.
    content_blocks = [
        {
            "id": "bmc-hrms-h",
            "type": "header",
            "data": {
                "text": '<span class="h3"><b> Employee Dashboard</b></span>',
                "col": 12,
            },
        },
        # {
        #     "id": "bmc-hrms-p",
        #     "type": "paragraph",
        #     "data": {
        #         "text": "Quick access to attendance, shifts, leave, and reports."
        #     },
        # },
    ]
    for idx, (card_label, _, _) in enumerate(HRMS_CARDS):
        content_blocks.append({
            "id": "bmc-hrms-card-" + str(idx),
            "type": "card",
            "data": {"card_name": card_label, "col": 4},
        })
    workspace.content = json.dumps(content_blocks)

    workspace.insert(ignore_permissions=True)
    return workspace


def _create_bmc_attendance_workspace():
    """BMC Attendance - header + paragraph + the two custom HTML blocks.

    No cards, no link-table pollution. The page renders the existing
    Attendance-Dashboard and Attendance-Table custom HTML blocks.

    Roles gate visibility: every role *except* Employee is allowed, so
    a plain Employee user doesn't see this workspace.
    """
    workspace = frappe.new_doc("Workspace")
    workspace.name = ATTENDANCE_WORKSPACE_NAME
    workspace.title = ATTENDANCE_WORKSPACE_NAME
    workspace.label = ATTENDANCE_WORKSPACE_NAME
    workspace.public = 1
    workspace.for_user = ""
    workspace.icon = "calendar"
    workspace.sequence_id = 101.0
    workspace.module = ""
    workspace.app = APP_NAME
    workspace.extend("roles", [
        {"role": "HR User"},
        {"role": "HR Manager"},
        {"role": "System Manager"},
    ])

    # Register the two blocks in the custom_blocks child table so they
    # show up in page_data.custom_blocks and Editor.js's custom_block
    # tool can resolve their HTML by name. Both blocks are loaded by
    # fixtures *before* this patch runs, so link validation passes.
    for cb_name in ("Attendance-Dashboard", "Attendance-Table"):
        workspace.append(
            "custom_blocks",
            {"custom_block_name": cb_name, "label": cb_name},
        )

    # Single source of truth: declared once, used for both insert
    # and the raw SQL backup below. No duplicated literal list.
    content_blocks = [
        {
            "id": "bmc-att-h",
            "type": "header",
            "data": {"text": '<span class="h3"><b>BMC Attendance</b></span>', "col": 12},
        },
        {
            "id": "card-Attendance-Dashboard",
            "type": "custom_block",
            "data": {"custom_block_name": "Attendance-Dashboard", "col": 12},
        },
        {
            "id": "card-Attendance-Table",
            "type": "custom_block",
            "data": {"custom_block_name": "Attendance-Table", "col": 12},
        },
    ]
    content_json = json.dumps(content_blocks)

    workspace.content = content_json
    workspace.insert(ignore_permissions=True)

    # Belt-and-braces: some Frappe versions strip custom_block content
    # entries on insert when the matching custom_blocks row was added
    # in the same transaction. Force the content back via raw SQL so
    # the render-side custom_block entries always survive.
    frappe.db.sql(
        "UPDATE `tabWorkspace` SET content = %s WHERE name = %s",
        (content_json, ATTENDANCE_WORKSPACE_NAME),
    )
    return workspace


def _create_sidebar(workspace):
    """Sidebar with all menu items. Items use mixed link_type (DocType /
    Workspace / Report) so each click navigates to something different."""
    sidebar = frappe.new_doc("Workspace Sidebar")
    sidebar.title = WORKSPACE_NAME
    sidebar.app = APP_NAME
    sidebar.module = ""
    sidebar.header_icon = "users"

    items = [
        {"type": "Link", "label": "Home", "icon": "home", "idx": 1,
         "link_type": "Workspace", "link_to": WORKSPACE_NAME},

        {"type": "Section Break", "label": "HR", "icon": "users", "idx": 10, "collapsible": 1},
        {"type": "Link", "label": "Employee", "icon": "users", "idx": 11,
         "link_type": "DocType", "link_to": "Employee"},
        {"type": "Link", "label": "Employee Checkin", "icon": "", "idx": 12,
         "link_type": "DocType", "link_to": "Employee Checkin"},
        {"type": "Link", "label": "Attendance", "icon": "calendar-check", "idx": 13,
         "link_type": "DocType", "link_to": "Attendance"},
        {"type": "Link", "label": "Attendance Request", "icon": "git-pull-request-arrow", "idx": 14,
         "link_type": "DocType", "link_to": "Attendance Request"},
        {"type": "Link", "label": "Compensatory Off", "icon": "calendar-plus", "idx": 15,
         "link_type": "DocType", "link_to": "Compensatory Leave Request"},
        {"type": "Link", "label": "Leaves", "icon": "calendar-minus", "idx": 16,
         "link_type": "DocType", "link_to": "Leave Application"},
        {"type": "Link", "label": "Shift Assignment", "icon": "assign", "idx": 17,
         "link_type": "DocType", "link_to": "Shift Assignment"},
        {"type": "Link", "label": "Recruitment", "icon": "briefcase", "idx": 18,
         "link_type": "DocType", "link_to": "Job Opening"},
        {"type": "Link", "label": "Job Applicant", "icon": "user-plus", "idx": 19,
         "link_type": "DocType", "link_to": "Job Applicant"},
        {"type": "Link", "label": "Expense Claim", "icon": "wallet", "idx": 20,
         "link_type": "DocType", "link_to": "Expense Claim"},
        {"type": "Link", "label": "Salary Payout", "icon": "money-coins-1", "idx": 21,
         "link_type": "DocType", "link_to": "Salary Slip"},
        
        {"type": "Section Break", "label": "Lifecycle", "icon": "milestone", "idx": 25, "collapsible": 1},
        {"type": "Link", "label": "Employee Lifecycle", "icon": "milestone", "idx": 26,
         "link_type": "Workspace", "link_to": LIFECYCLE_WORKSPACE_NAME},
        {"type": "Link", "label": "Employee Onboarding", "icon": "user-plus", "idx": 27,
         "link_type": "DocType", "link_to": "Employee Onboarding"},
        {"type": "Link", "label": "Employee Promotion", "icon": "trending-up", "idx": 28,
         "link_type": "DocType", "link_to": "Employee Promotion"},
        {"type": "Link", "label": "Employee Separation", "icon": "user-minus", "idx": 29,
         "link_type": "DocType", "link_to": "Employee Separation"},

        {"type": "Section Break", "label": "Dashboard", "icon": "layout", "idx": 30, "collapsible": 1},
        {"type": "Link", "label": "Attendance Dashboard", "icon": "blocks", "idx": 31,
         "link_type": "Workspace", "link_to": ATTENDANCE_WORKSPACE_NAME},
        {"type": "Link", "label": "My Team", "icon": "users-round", "idx": 32,
         "link_type": "Workspace", "link_to": "My Team"},

        {"type": "Section Break", "label": "Reports", "icon": "list", "idx": 99, "collapsible": 1},
        # Reports section - children nested under the Reports header (child=1)
        {"type": "Link", "label": "Employee Leave Balance", "icon": "table", "idx": 100,
         "child": 1,
         "link_type": "Report", "link_to": "Employee Leave Balance"},
        {"type": "Link", "label": "Attendance Report", "icon": "file-text", "idx": 101,
         "child": 1,
         "link_type": "Report", "link_to": "Attendance Report"},
        {"type": "Link", "label": "Effective Attendance Report", "icon": "file-check", "idx": 102,
         "child": 1,
         "link_type": "Report", "link_to": "Effective Attendance Report"},
        {"type": "Link", "label": "Attendance Source Report", "icon": "list", "idx": 103,
         "child": 1,
         "link_type": "Report", "link_to": "Attendance Source Report"},
    ]

    for item in items:
        sidebar.append("items", item)

    sidebar.insert(ignore_permissions=True)
    return sidebar


def _create_desktop_icon(label, route_path, link_to, icon="users"):
    """Create a Desktop Icon with link_type='Workspace Sidebar'."""
    if frappe.db.exists("Desktop Icon", {"label": label}):
        frappe.db.delete("Desktop Icon", {"label": label})
    icon_doc = frappe.new_doc("Desktop Icon")
    icon_doc.label = label
    icon_doc.module_name = ""
    icon_doc.app = APP_NAME
    icon_doc.icon_type = "Link"
    icon_doc.icon = icon
    icon_doc.logo_url = LOGO_URL
    icon_doc.route = route_path
    icon_doc.link_type = "Workspace Sidebar"
    icon_doc.link_to = link_to
    icon_doc.standard = 0
    icon_doc.insert(ignore_permissions=True)


def _apply_logo():
    if frappe.db.exists("Desktop Icon", WORKSPACE_NAME):
        frappe.db.set_value(
            "Desktop Icon",
            WORKSPACE_NAME,
            {"icon": "users", "logo_url": LOGO_URL},
            update_modified=False,
        )


def execute():
    # Wipe BMC HRMS state.
    if frappe.db.exists("Workspace Sidebar", WORKSPACE_NAME):
        try:
            frappe.delete_doc("Workspace Sidebar", WORKSPACE_NAME, force=1, ignore_permissions=True)
        except Exception:
            pass
    if frappe.db.exists("Workspace", WORKSPACE_NAME):
        try:
            frappe.delete_doc("Workspace", WORKSPACE_NAME, force=1, ignore_permissions=True)
        except Exception:
            frappe.db.delete("Workspace", {"name": WORKSPACE_NAME})
    if frappe.db.exists("Desktop Icon", {"label": WORKSPACE_NAME}):
        try:
            frappe.delete_doc("Desktop Icon", WORKSPACE_NAME, force=1, ignore_permissions=True)
        except Exception:
            frappe.db.delete("Desktop Icon", {"label": WORKSPACE_NAME})

    # BMC Attendance - wipe and recreate from scratch.
    _wipe(ATTENDANCE_WORKSPACE_NAME)
    _create_bmc_attendance_workspace()

    # BMC HRMS - rebuild with cards.
    frappe.db.sql("UPDATE `tabWorkspace` SET content = %s WHERE name = %s", ("[]", WORKSPACE_NAME))
    _create_bmc_hrms_workspace()
    _create_sidebar(None)
    _create_desktop_icon(WORKSPACE_NAME, f"/desk/{frappe.scrub(WORKSPACE_NAME)}", WORKSPACE_NAME)
    _apply_logo()

    frappe.db.commit()
    try:
        frappe.cache.delete_keys("bootinfo:*")
    except Exception:
        frappe.cache.delete_key("bootinfo")
    frappe.cache.delete_key("desk_sidebar_items")
    frappe.cache.delete_key("get_sidebar_items")
    print(
        f"Workspaces '{WORKSPACE_NAME}' (with 4 cards) and "
        f"'{ATTENDANCE_WORKSPACE_NAME}' rebuilt, sidebar with mixed link_type "
        f"items, desktop icons wired."
    )
