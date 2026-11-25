// Copyright (c) 2016, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

function is_uuid(val) {
	if (!val) return false;
	const uuidRegex = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
	return uuidRegex.test(String(val).trim());
}

function freeze_uuid_attendance_device_id(frm) {
	// Only freeze if attendance_device_id holds a generated UUID.
	// 10- or 12-digit numeric values remain editable.
	if (is_uuid(frm.doc.attendance_device_id)) {
		frm.set_df_property("attendance_device_id", "read_only", 1);
	} else {
		frm.set_df_property("attendance_device_id", "read_only", 0);
	}
}

frappe.ui.form.on("Employee", {
	refresh: function (frm) {
		frm.set_df_property("holiday_list", "hidden", 0);
		freeze_uuid_attendance_device_id(frm);
	},
	attendance_device_id: function (frm) {
		freeze_uuid_attendance_device_id(frm);
	},
});
