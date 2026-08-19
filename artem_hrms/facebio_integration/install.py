import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_field

CUSTOM_FIELDS = [
    {
        "fieldname": "facebio_employee_id",
        "label": "FaceBio Employee ID",
        "fieldtype": "Data",
        "read_only": 1,
        "insert_after": "attendance_device_id",
    },
    {
        "fieldname": "facebio_uuid",
        "label": "FaceBio UUID",
        "fieldtype": "Data",
        "read_only": 1,
        "insert_after": "facebio_employee_id",
    },
    {
        "fieldname": "facebio_last_sync_status",
        "label": "FaceBio Sync Status",
        "fieldtype": "Select",
        "options": "\nNot Synced\nPending\nSynced\nFailed",
        "read_only": 1,
        "default": "Not Synced",
        "insert_after": "facebio_uuid",
    },
    {
        "fieldname": "facebio_last_sync_at",
        "label": "FaceBio Last Sync At",
        "fieldtype": "Datetime",
        "read_only": 1,
        "insert_after": "facebio_last_sync_status",
    },
    {
        "fieldname": "facebio_last_error",
        "label": "FaceBio Last Error",
        "fieldtype": "Text",
        "read_only": 1,
        "insert_after": "facebio_last_sync_at",
    },
]

def execute():
    for field in CUSTOM_FIELDS:
        if not frappe.db.exists(
            "Custom Field", {"dt": "Employee", "fieldname": field["fieldname"]}
        ):
            create_custom_field("Employee", field)
