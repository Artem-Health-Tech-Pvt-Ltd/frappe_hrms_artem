import frappe

def update_administrative_officer_permissions(doc, method=None):
	old_ao = None

	if not doc.is_new():
		# Retrieve the cached value from before the save operation
		old_ao = doc.get_value_before_save("custom_administrative_officer")

	# Remove old AO permission
	if old_ao and old_ao != doc.custom_administrative_officer:
		old_ao_user = frappe.db.get_value("Employee", old_ao, "user_id")

		if old_ao_user:
			permission_name = frappe.db.get_value(
				"User Permission",
				{
					"user": old_ao_user,
					"allow": "Employee",
					"for_value": doc.name,
				},
				"name"
			)

			if permission_name:
				frappe.delete_doc("User Permission", permission_name)

	# Add new AO permission
	if doc.custom_administrative_officer:
		new_ao_user = frappe.db.get_value(
			"Employee",
			doc.custom_administrative_officer,
			"user_id"
		)

		if new_ao_user and doc.name:
			if not frappe.db.exists(
				"User Permission",
				{
					"user": new_ao_user,
					"allow": "Employee",
					"for_value": doc.name
				}
			):
				frappe.get_doc({
					"doctype": "User Permission",
					"user": new_ao_user,
					"allow": "Employee",
					"for_value": doc.name,
					"apply_to_all_doctypes": 1
				}).insert(ignore_permissions=True)
