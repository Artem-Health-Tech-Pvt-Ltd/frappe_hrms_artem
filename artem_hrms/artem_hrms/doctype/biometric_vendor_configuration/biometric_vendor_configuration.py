# Copyright (c) 2026, Artem and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class BiometricVendorConfiguration(Document):
	def validate(self):
		if not self.payload_mappings:
			frappe.throw("At least one Payload Mapping row is required.")

		# Ensure unique vendor_key within the child table.
		seen = set()
		for row in self.payload_mappings:
			if row.vendor_key in seen:
				frappe.throw(f"Duplicate vendor_key '{row.vendor_key}' in Payload Mappings.")
			seen.add(row.vendor_key)

		# Validate frappe_field exists on Employee DocType.
		employee_meta = frappe.get_meta("Employee")
		valid_fields = {df.fieldname for df in employee_meta.fields}
		for row in self.payload_mappings:
			if row.frappe_field not in valid_fields:
				frappe.throw(
					f"Row {row.idx}: frappe_field '{row.frappe_field}' is not a valid field on Employee."
				)
