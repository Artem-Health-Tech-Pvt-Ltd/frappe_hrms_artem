// Copyright (c) 2026
// Attendance Report - client side filters

frappe.query_reports["Attendance Report"] = {
	filters: [
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: frappe.datetime.month_start(),
			reqd: 1,
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
			reqd: 1,
		},
		{
			// multiple wards
			fieldname: "ward",
			label: __("Ward"),
			fieldtype: "MultiSelectList",
			get_data: function (txt) {
				return frappe
					.xcall(
						"artem_hrms.artem_hrms.report.attendance_report.attendance_report.get_ward_options",
						{ txt: txt || "" }
					)
					.then((wards) =>
						(wards || []).map((w) => ({ value: w, description: "" }))
					);
			},
		},
		{
			// multiple branches
			fieldname: "branch",
			label: __("Organization (Branch)"),
			fieldtype: "MultiSelectList",
			get_data: function (txt) {
				return frappe.db.get_link_options("Branch", txt);
			},
			on_change: function () {
				toggle_department_filter();
				frappe.query_report.refresh();
			},
		},
		{
			// multiple departments - only when at least one branch is selected
			fieldname: "department",
			label: __("Department"),
			fieldtype: "MultiSelectList",
			get_data: function (txt) {
				return frappe.db.get_link_options("Department", txt);
			},
		},
	],

	onload: function (report) {
		toggle_department_filter();
	},
};

function toggle_department_filter() {
	const branches = frappe.query_report.get_filter_value("branch");
	const dept_filter = frappe.query_report.get_filter("department");
	if (!dept_filter) return;

	if (branches && branches.length) {
		// at least one branch chosen -> enable Department
		dept_filter.df.read_only = 0;
	} else {
		// no branch -> clear and disable (kept visible in the filter bar)
		frappe.query_report.set_filter_value("department", []);
		dept_filter.df.read_only = 1;
	}
	dept_filter.refresh_input();
}