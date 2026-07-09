// Copyright (c) 2026
// Attendance Source Report - client side filters

frappe.query_reports["Attendance Source Report"] = {
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
			fieldname: "branch",
			label: __("Organization (Branch)"),
			fieldtype: "Link",
			options: "Branch",
			on_change: function () {
				toggle_department_filter();
				frappe.query_report.refresh();
			},
		},
		{
			fieldname: "ward",
			label: __("Ward"),
			fieldtype: "Data",
		},
		{
			fieldname: "department",
			label: __("Department"),
			fieldtype: "Link",
			options: "Department",
		},
	],

	onload: function (report) {
		toggle_department_filter();
	},
};

function toggle_department_filter() {
	const branch = frappe.query_report.get_filter_value("branch");
	const dept_filter = frappe.query_report.get_filter("department");
	if (!dept_filter) return;

	if (branch) {
		// Branch chosen -> enable Department
		dept_filter.df.read_only = 0;
	} else {
		// No branch -> clear and disable (but keep visible in the filter bar)
		frappe.query_report.set_filter_value("department", "");
		dept_filter.df.read_only = 1;
	}
	dept_filter.refresh_input();
}