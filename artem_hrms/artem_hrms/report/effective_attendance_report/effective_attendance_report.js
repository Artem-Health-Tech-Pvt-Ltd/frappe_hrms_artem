
frappe.query_reports["Effective Attendance Report"] = {
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
			// Single branch only - report runs for exactly one selected branch
			fieldname: "branch",
			label: __("Organization (Branch)"),
			fieldtype: "Link",
			options: "Branch",
			reqd: 1,
		},
	],

	onload: function (report) {
		report.page.add_inner_button(__("Download Formatted Excel"), function () {
			const filters = report.get_values();
			if (!filters || !filters.branch) {
				frappe.msgprint(__("Please select an Organization (Branch) first"));
				return;
			}
			open_url_post(frappe.request.url, {
				cmd: "artem_hrms.artem_hrms.report.effective_attendance_report.effective_attendance_report.download_excel",
				filters: JSON.stringify(filters),
			});
		});
	},
};