# Copyright (c) 2026, Artem and contributors
# For license information, please see license.txt

import json

import frappe
from frappe.model.document import Document


class BiometricVendorConfiguration(Document):
	def validate(self):
		if not self.payload_mappings:
			frappe.throw("At least one Payload Mapping row is required.")

		# Validate Custom Headers JSON
		if self.custom_headers:
			try:
				parsed = json.loads(self.custom_headers)
				if not isinstance(parsed, dict):
					frappe.throw("Creation Custom Headers must be a valid JSON object.")
			except Exception as e:
				frappe.throw(f"Invalid JSON in Creation Custom Headers: {e}")

		if getattr(self, "update_custom_headers", None):
			try:
				parsed = json.loads(self.update_custom_headers)
				if not isinstance(parsed, dict):
					frappe.throw("Update Custom Headers must be a valid JSON object.")
			except Exception as e:
				frappe.throw(f"Invalid JSON in Update Custom Headers: {e}")

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
