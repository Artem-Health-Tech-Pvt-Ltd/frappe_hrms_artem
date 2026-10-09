import frappe

def execute():

    for property_setter in get_property_setters():

        frappe.make_property_setter(property_setter, validate_fields_for_doctype=False)

def get_property_setters():

    return [

        # Attendance Request

        {

            "doctype": "Attendance Request",

            "doctype_or_field": "DocField",

            "fieldname": "reason",

            "property": "options",

            "property_type": "Text",

            "value": "Work From Home\nOn Duty\nOutdoor Duty",
        },

]