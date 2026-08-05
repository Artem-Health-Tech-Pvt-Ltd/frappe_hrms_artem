"""Drop the HR Dashboard workspace, sidebar entry, and desktop icon.

The HR Dashboard page is no longer wanted. This patch removes the
Workspace doc, any Workspace Sidebar row, related User Permissions,
and the Desktop Icon whose label matches.
"""
import frappe

WORKSPACE_NAME = "HR Dashboard"


def _wipe_workspace(name):
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


def execute():
    if not frappe.db.exists("Workspace", WORKSPACE_NAME):
        print(f"Workspace '{WORKSPACE_NAME}' does not exist - nothing to drop.")
        return

    _wipe_workspace(WORKSPACE_NAME)
    frappe.db.commit()
    try:
        frappe.cache.delete_keys("bootinfo:*")
    except Exception:
        frappe.cache.delete_key("bootinfo")
    frappe.cache.delete_key("desk_sidebar_items")
    frappe.cache.delete_key("get_sidebar_items")
    print(f"Workspace '{WORKSPACE_NAME}' dropped.")
