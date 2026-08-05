// Copyright (c) 2026
// Attendance Report - client side filters + grouped month header

frappe.query_reports["Attendance Report"] = {
	filters: [
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: frappe.datetime.month_start(),
			reqd: 1,
			on_change: function () {
				frappe.query_report && frappe.query_report.refresh && frappe.query_report.refresh();
			},
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
			reqd: 1,
			on_change: function () {
				validate_date_range();
			},
		},
		{
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
			on_change: function () {
				frappe.query_report.refresh();
			},
		},
		{
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
		// Prominent top-right "Download Formatted Excel" button.
		report.page.set_primary_action(
			__("Download Formatted Excel"),
			function () {
				const filters = frappe.query_report.get_filter_values(true) || {};
				if (!filters.from_date || !filters.to_date) {
					frappe.msgprint(__("Please select a From Date and To Date first"));
					return;
				}
				open_url_post(frappe.request.url, {
					cmd: "artem_hrms.artem_hrms.report.attendance_report.attendance_report.download_excel",
					filters: JSON.stringify(filters),
				});
			},
			null,
			__("Downloading...")
		);
	},

	// Real grouped month header rendered above the day columns.
	after_datatable_render: function (datatable) {
		inject_month_group_header(datatable);
	},
};

function toggle_department_filter() {
	const branches = frappe.query_report.get_filter_value("branch");
	const dept_filter = frappe.query_report.get_filter("department");
	if (!dept_filter) return;

	if (branches && branches.length) {
		dept_filter.df.read_only = 0;
	} else {
		frappe.query_report.set_filter_value("department", []);
		dept_filter.df.read_only = 1;
	}
	dept_filter.refresh_input();
}

function validate_date_range() {
	let from_date = frappe.query_report.get_filter_value("from_date");
	let to_date = frappe.query_report.get_filter_value("to_date");
	if (!(from_date && to_date)) return;

	let start = frappe.datetime.str_to_obj(from_date);
	let end = frappe.datetime.str_to_obj(to_date);
	let day_diff = Math.floor((end - start) / (24 * 60 * 60 * 1000));
	if (day_diff > 90) {
		frappe.throw({
			message: __("Please set a date range less than 90 days."),
			title: __("Date Range Exceeded"),
		});
	}
	frappe.query_report.refresh();
}

// ---------------------------------------------------------------------------
// Grouped month header overlay
// ---------------------------------------------------------------------------

const MONTH_NAMES_AR = [
	"January", "February", "March", "April", "May", "June",
	"July", "August", "September", "October", "November", "December",
];
const MONTH_PALETTE_AR = [
	"#1f77b4", "#ff7f0e", "#2ca02c", "#fb939379",
	"#9467bd", "#daa095", "#8ae4af", "#d3d3d3",
	"#e2e22c", "#17becf", "#8285d7", "#c3dc95",
];

function ar_month_name(idx) {
	return MONTH_NAMES_AR[idx] || "";
}

function get_range_dates() {
	const filters = frappe.query_report.get_filter_values(true) || {};
	if (!filters.from_date || !filters.to_date) return [];
	const start = frappe.datetime.str_to_obj(filters.from_date);
	const end = frappe.datetime.str_to_obj(filters.to_date);
	const out = [];
	const d = new Date(start.getFullYear(), start.getMonth(), start.getDate());
	const e = new Date(end.getFullYear(), end.getMonth(), end.getDate());
	while (d <= e) {
		out.push(new Date(d));
		d.setDate(d.getDate() + 1);
	}
	return out;
}

function get_day_fieldnames(datatable) {
	// Day columns use fieldname `d_YYYY-MM-DD` per attendance_report.py
	const cols = (datatable.datamanager && datatable.datamanager.columns) || [];
	return cols
		.filter((c) => typeof (c.id || c.fieldname) === "string" && /^d_\d{4}-\d{2}-\d{2}$/.test(c.id || c.fieldname))
		.map((c) => ({ fieldname: c.id || c.fieldname, date: (c.id || c.fieldname).slice(2) }));
}

function inject_month_group_header(datatable) {
	try {
		const dates = get_range_dates();
		if (!dates.length) return;
		const dayCols = get_day_fieldnames(datatable);
		if (!dayCols.length) return;

		// group day columns by year-month
		const groups = [];
		let cur = null;
		dayCols.forEach((c) => {
			const [y, m] = c.date.split("-").map(Number);
			const key = `${y}-${m}`;
			if (!cur || cur.key !== key) {
				cur = { key, year: y, month: m - 1, count: 1 };
				groups.push(cur);
			} else {
				cur.count += 1;
			}
		});

		const headerRow = datatable.wrapper.querySelector(".header-row");
		if (!headerRow) return;

		// remove previous overlay (re-runs after refresh)
		const existing = datatable.wrapper.querySelector(".month-group-header");
		if (existing) existing.remove();

		// inject shared CSS once
		if (!document.getElementById("bmc-month-group-style")) {
			const style = document.createElement("style");
			style.id = "bmc-month-group-style";
			style.textContent = `
				.dt .month-group-header { display:flex; gap:4px; padding:4px 6px; background:#f5f7fa; border-bottom:1px solid #d1d8dd; font-weight:600; }
				.dt .month-group-header .mg-cell { padding:6px 10px; color:#fff; border-radius:3px; font-size:12px; text-align:center; flex:1 1 0; }
			`;
			document.head.appendChild(style);
		}

		const overlay = document.createElement("div");
		overlay.className = "month-group-header";

		// Reserve the same horizontal space as the identity columns (sr_no + ward + branch + employee + employee_name + department + designation = 7)
		// by adding a left spacer that matches those columns' widths in flex.
		const spacer = document.createElement("div");
		spacer.style.cssText = "flex:0 0 auto; min-width:710px;"; // matches sum of prefix column widths (60+100+140+110+160+130+110)
		overlay.appendChild(spacer);

		groups.forEach((g) => {
			const cell = document.createElement("div");
			cell.className = "mg-cell";
			const colour = MONTH_PALETTE_AR[g.month % MONTH_PALETTE_AR.length];
			cell.textContent = `${ar_month_name(g.month)} ${g.year}`;
			cell.style.background = colour;
			cell.title = `${g.count} day(s)`;
			overlay.appendChild(cell);
		});

		headerRow.parentNode.insertBefore(overlay, headerRow);
	} catch (e) {
		console.warn("month-group-header injection failed", e);
	}
}
