import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_field

CUSTOM_FIELDS = [
    {
        "fieldname": "vendor_employee_id",
        "label": "Vendor Employee ID",
        "fieldtype": "Data",
        "read_only": 1,
        "insert_after": "attendance_device_id",
    },
    {
        "fieldname": "vendor_uuid",
        "label": "Vendor UUID",
        "fieldtype": "Data",
        "read_only": 1,
        "insert_after": "vendor_employee_id",
    },
    {
        "fieldname": "vendor_last_sync_status",
        "label": "Vendor Sync Status",
        "fieldtype": "Select",
        "options": "\nNot Synced\nPending\nSynced\nFailed",
        "read_only": 1,
        "default": "Not Synced",
        "insert_after": "vendor_uuid",
    },
    {
        "fieldname": "vendor_last_sync_at",
        "label": "Vendor Last Sync At",
        "fieldtype": "Datetime",
        "read_only": 1,
        "insert_after": "vendor_last_sync_status",
    },
    {
        "fieldname": "vendor_last_error",
        "label": "Vendor Last Error",
        "fieldtype": "Text",
        "read_only": 1,
        "insert_after": "vendor_last_sync_at",
    },
]


def execute():
    for field in CUSTOM_FIELDS:
        if not frappe.db.exists(
            "Custom Field", {"dt": "Employee", "fieldname": field["fieldname"]}
        ):
            create_custom_field("Employee", field)