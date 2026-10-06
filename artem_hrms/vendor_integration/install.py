import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

CUSTOM_FIELDS = {
    "Branch": [
        {
            "fieldname": "custom_biometric_vendor",
            "label": "Biometric Vendor Configuration",
            "fieldtype": "Link",
            "options": "Biometric Vendor Configuration",
            "insert_after": "branch_name",
            "description": "Select the biometric vendor configuration used for attendance sync at this branch.",
        }
    ],
    "Employee": [
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
    ],
}


def execute():
    """Idempotently create required custom fields for Branch and Employee DocTypes."""
    for dt, fields in CUSTOM_FIELDS.items():
        fields_to_create = []
        for field in fields:
            if not frappe.db.exists(
                "Custom Field", {"dt": dt, "fieldname": field["fieldname"]}
            ):
                fields_to_create.append(field)

        if fields_to_create:
            create_custom_fields({dt: fields_to_create})
            frappe.db.commit()


if __name__ == "__main__":
    execute()