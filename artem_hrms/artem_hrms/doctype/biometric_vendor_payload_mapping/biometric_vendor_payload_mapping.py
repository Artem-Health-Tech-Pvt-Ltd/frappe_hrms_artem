# Copyright (c) 2026, Artem and contributors
# For license information, please see license.txt

from frappe.model.document import Document

BRANCH_MAPPING = {
	"Lokmanya Tilak Municipal Medical College and General Hospital Sion": "Lokmanya Tilak Municipal Medical College and General Hospital, Sion"
}


def normalize_branch_name(value):
	if value and str(value).strip() in BRANCH_MAPPING:
		return BRANCH_MAPPING[str(value).strip()]
	return value


class BiometricVendorPayloadMapping(Document):
	def transform_value(self, value):
		"""Normalize branch name if 'branch' is configured."""
		if self.frappe_field == "branch":
			return normalize_branch_name(value)
		return value

