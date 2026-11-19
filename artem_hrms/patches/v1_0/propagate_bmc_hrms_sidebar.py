"""Propagate the BMC HRMS sidebar to child workspaces.

The Desk sidebar is loaded by ``frappe.boot.workspace_sidebar_item``, keyed
by the active workspace's title (lowercased). When a user clicks a sidebar
item like "My Team" (which points to a child Workspace), Frappe routes to
``/desk/my-team`` and looks up ``workspace_sidebar_item["my team"]``. That
key doesn't exist (only "bmc hrms" exists), so the rendered sidebar is
empty — the user sees only "Home".

Fix: create a copy of the BMC HRMS ``Workspace Sidebar`` row for each child
workspace, so navigating to those routes shows the same HR navigation.

The three sidebar items the user wanted click-locked
("Employee Lifecycle", "Attendance Dashboard", "My Team") stay as Section
Breaks inside the BMC HRMS sidebar; this patch doesn't touch them.

Safe to re-run: wipes any pre-existing matching sidebar rows before
recreating them so the items stay in sync with the BMC HRMS source.
"""

import frappe

SOURCE_SIDEBAR = "BMC HRMS"
CHILD_WORKSPACES = ["Employee Lifecycle", "BMC Attendance", "My Team"]
APP_NAME = "artem_hrms"


def _copy_items(src_doc, dst_doc):
    """Deep-copy items child table from src to dst, preserving idx."""
    idx = 1
    for item in src_doc.items:
        dst_doc.append(
            "items",
            {
                "type": item.type,
                "label": item.label,
                "link_type": item.link_type,
                "link_to": item.link_to,
                "icon": item.icon,
                "child": item.child,
                "indent": item.indent,
                "collapsible": item.collapsible,
                "keep_closed": item.keep_closed,
                "url": item.url,
                "show_arrow": item.show_arrow,
                "idx": idx,
            },
        )
        idx += 1


def _wipe(name):
    if frappe.db.exists("Workspace Sidebar", name):
        try:
            frappe.delete_doc(
                "Workspace Sidebar", name, force=1, ignore_permissions=True
            )
        except Exception as e:
            print(f"  could not wipe '{name}': {e}")


def _create_for_workspace(workspace_name, src_doc):
    _wipe(workspace_name)
    sidebar = frappe.new_doc("Workspace Sidebar")
    sidebar.title = workspace_name
    sidebar.app = APP_NAME
    sidebar.module = ""
    sidebar.header_icon = src_doc.header_icon or "users"
    _copy_items(src_doc, sidebar)
    sidebar.insert(ignore_permissions=True)
    return sidebar


def execute():
    if not frappe.db.exists("Workspace Sidebar", SOURCE_SIDEBAR):
        print(f"Source sidebar '{SOURCE_SIDEBAR}' not found. Run setup_bmc_hrms_workspace_v4 first.")
        return

    src = frappe.get_doc("Workspace Sidebar", SOURCE_SIDEBAR)
    print(
        f"Source '{SOURCE_SIDEBAR}' has {len(src.items)} items; "
        f"copying to {len(CHILD_WORKSPACES)} child workspaces."
    )

    created = []
    for ws_name in CHILD_WORKSPACES:
        if not frappe.db.exists("Workspace", ws_name):
            print(f"  skipping '{ws_name}': Workspace not found")
            continue
        _create_for_workspace(ws_name, src)
        created.append(ws_name)

    if created:
        frappe.db.commit()
        try:
            frappe.cache.delete_key("desk_sidebar_items")
            frappe.cache.delete_key("get_sidebar_items")
        except Exception:
            pass
        print(f"Created Workspace Sidebar rows for: {', '.join(created)}")


if __name__ == "__main__":
    execute()
