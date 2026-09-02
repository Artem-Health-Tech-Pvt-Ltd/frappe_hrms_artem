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
			fieldname: "ward",
			label: __("Ward"),
			fieldtype: "MultiSelectList",
			get_data: function (txt) {
				return frappe
					.xcall(
						"artem_hrms.artem_hrms.report.attendance_source_report.attendance_source_report.get_ward_options",
						{ txt: txt || "" }
					)
					.then((wards) =>
						(wards || []).map((w) => ({ value: w, description: "" }))
					);
			},
			on_change: function () {
				cascade_after_ward_change();
			},
		},
		{
			fieldname: "branch",
			label: __("Organization (Branch)"),
			fieldtype: "MultiSelectList",
			get_data: function (txt) {
				const wards = get_ms_values("ward");
				return frappe
					.xcall(
						"artem_hrms.artem_hrms.report.attendance_source_report.attendance_source_report.get_branch_options",
						{ txt: txt || "", wards: wards }
					)
					.then((branches) =>
						(branches || []).map((b) => ({ value: b.name, description: "" }))
					);
			},
			on_change: function () {
				cascade_after_branch_change();
			},
		},
		{
			fieldname: "department",
			label: __("Department"),
			fieldtype: "MultiSelectList",
			get_data: function (txt) {
				const orgs = get_ms_values("branch");
				const wards = get_ms_values("ward");
				const args = { txt: txt || "" };

				let method;
				if (wards.length && !orgs.length) {
					method = "get_department_query";
					args.wards = wards;
				} else if (orgs.length) {
					method = "get_department_query";
					args.branches = orgs;
				} else {
					// No Ward/Org -> disable dept (enforced via read-only + server-side validation)
					return Promise.resolve([]);
				}

				return frappe
					.xcall(
						"artem_hrms.artem_hrms.report.attendance_source_report.attendance_source_report." + method,
						args
					)
					.then((depts) =>
						(depts || []).map((d) => ({ value: d.name || d, description: "" }))
					);
			},
		},
	],

	onload: function (report) {
		toggle_department_filter();
		report.page.set_primary_action(
			__("Download Formatted Excel"),
			function () {
				const filters = frappe.query_report.get_filter_values(true);
				open_url_post(frappe.request.url, {
					cmd: "artem_hrms.artem_hrms.report.attendance_source_report.attendance_source_report.download_excel",
					filters: JSON.stringify(filters || {}),
				});
			},
			null,
			__("Downloading...")
		);
	},

	after_datatable_render: function (datatable) {
		inject_month_group_header_source(datatable);
	},
};

// ---------------------------------------------------------------------------
// Grouped month header overlay (matches Attendance Report styling)
// ---------------------------------------------------------------------------
//
// The Attendance Source Report has 17 columns including a single Attendance Date
// column. We render the same colour-coded month header above the date column,
// and split the other columns into "Details" (identity + HOD + sources) and
// "Summary" (attendance + times + flags) groups so the layout matches the
// Attendance Report style.

const AS_MONTH_NAMES = [
	"January", "February", "March", "April", "May", "June",
	"July", "August", "September", "October", "November", "December",
];
const AS_MONTH_PALETTE = [
	"#1f77b4", "#ff7f0e", "#2ca02c", "#d62728",
	"#9467bd", "#8c564b", "#e377c2", "#7f7f7f",
	"#bcbd22", "#17becf", "#393b79", "#637939",
];

// Column groups (matching Attendance Source Report column order)
//   Details  : ward, branch, employee, employee_name, department
//   Date     : attendance_date  (highlighted per-month)
//   Identity : hod_name
//   Sources  : check_in_source, check_out_source
//   Summary  : attendance, shift_time, check_in_time, check_out_time,
//              working_hours, late_punch, early_out, missed_punch
const AS_DETAIL_FIELDS = ["ward", "branch", "employee", "employee_name", "department"];
const AS_DATE_FIELDS = ["attendance_date"];
const AS_IDENTITY_FIELDS = ["hod_name"];
const AS_SOURCES_FIELDS = ["check_in_source", "check_out_source"];
const AS_SUMMARY_FIELDS = [
	"attendance", "shift_time", "check_in_time", "check_out_time",
	"working_hours", "late_punch", "early_out", "missed_punch",
];

function inject_month_group_header_source(datatable) {
	try {
		const filters = frappe.query_report.get_filter_values(true) || {};
		const start = filters.from_date ? frappe.datetime.str_to_obj(filters.from_date) : null;
		const end = filters.to_date ? frappe.datetime.str_to_obj(filters.to_date) : null;

		const cols = (datatable.datamanager && datatable.datamanager.columns) || [];
		if (!cols.length) return;

		// Resolve column indexes for each group
		const idxFor = (fields) => {
			const set = new Set(fields);
			return cols
				.map((c, i) => ({ i, name: c.id || c.fieldname }))
				.filter((c) => set.has(c.name))
				.map((c) => c.i);
		};
		const detailIdx = idxFor(AS_DETAIL_FIELDS);
		const dateIdx = idxFor(AS_DATE_FIELDS);
		const identityIdx = idxFor(AS_IDENTITY_FIELDS);
		const sourcesIdx = idxFor(AS_SOURCES_FIELDS);
		const summaryIdx = idxFor(AS_SUMMARY_FIELDS);
		if (!detailIdx.length || !dateIdx.length) return;

		const headerRow = datatable.wrapper.querySelector(".header-row");
		if (!headerRow) return;
		const existing = datatable.wrapper.querySelector(".month-group-header");
		if (existing) existing.remove();

		if (!document.getElementById("bmc-month-group-style")) {
			const style = document.createElement("style");
			style.id = "bmc-month-group-style";
			style.textContent = `
				.dt .month-group-header { display:flex; gap:4px; padding:4px 6px; background:#f5f7fa; border-bottom:1px solid #d1d8dd; font-weight:600; }
				.dt .month-group-header .mg-cell { padding:6px 10px; color:#fff; border-radius:3px; font-size:12px; text-align:center; }
				.dt .month-group-header .mg-detail { background:#1F4E78; }
				.dt .month-group-header .mg-identity { background:#7f7f7f; }
				.dt .month-group-header .mg-sources { background:#393b79; }
				.dt .month-group-header .mg-summary { background:#9467bd; }
			`;
			document.head.appendChild(style);
		}

		const overlay = document.createElement("div");
		overlay.className = "month-group-header";

		// Build a single month label for the date column, or "Date" if no range.
		const monthLabel = (() => {
			if (!start || !end) return __("Date");
			// If both endpoints fall in the same month -> single label, else "Date Range".
			if (start.getFullYear() === end.getFullYear() && start.getMonth() === end.getMonth()) {
				return `${AS_MONTH_NAMES[start.getMonth()]} ${start.getFullYear()}`;
			}
			return `${AS_MONTH_NAMES[start.getMonth()]} – ${AS_MONTH_NAMES[end.getMonth()]} ${end.getFullYear()}`;
		})();
		const monthCell = document.createElement("div");
		monthCell.className = "mg-cell";
		const monthColour = (start && end && start.getFullYear() === end.getFullYear() && start.getMonth() === end.getMonth())
			? AS_MONTH_PALETTE[start.getMonth() % AS_MONTH_PALETTE.length]
			: "#318AD8";
		monthCell.textContent = monthLabel;
		monthCell.style.background = monthColour;
		monthCell.title = monthLabel;

		// Build "Details" spacer (sum of widths for the columns in detailIdx)
		const detailWidthSum = detailIdx.reduce((acc, i) => acc + (cols[i].width || 100), 0);
		const detailCell = document.createElement("div");
		detailCell.className = "mg-cell mg-detail";
		detailCell.textContent = __("Employee Details");
		detailCell.style.minWidth = detailWidthSum + "px";

		overlay.appendChild(detailCell);
		overlay.appendChild(monthCell);

		if (identityIdx.length) {
			const cell = document.createElement("div");
			cell.className = "mg-cell mg-identity";
			cell.textContent = __("Approval");
			const w = identityIdx.reduce((acc, i) => acc + (cols[i].width || 100), 0);
			cell.style.minWidth = w + "px";
			overlay.appendChild(cell);
		}
		if (sourcesIdx.length) {
			const cell = document.createElement("div");
			cell.className = "mg-cell mg-sources";
			cell.textContent = __("Sources");
			const w = sourcesIdx.reduce((acc, i) => acc + (cols[i].width || 100), 0);
			cell.style.minWidth = w + "px";
			overlay.appendChild(cell);
		}
		if (summaryIdx.length) {
			const cell = document.createElement("div");
			cell.className = "mg-cell mg-summary";
			cell.textContent = __("Summary");
			const w = summaryIdx.reduce((acc, i) => acc + (cols[i].width || 100), 0);
			cell.style.minWidth = w + "px";
			overlay.appendChild(cell);
		}

		headerRow.parentNode.insertBefore(overlay, headerRow);
	} catch (e) {
		console.warn("month-group-header (source) failed", e);
	}
}

// ---------------------------------------------------------------------------
// Cascade helpers
// ---------------------------------------------------------------------------

function get_ms_values(fieldname) {
	const v = frappe.query_report.get_filter_value(fieldname);
	if (!v) return [];
	if (Array.isArray(v)) return v.filter(Boolean);
	// Single-select fallback or stray string
	if (typeof v === "string") {
		if (v.startsWith("[") && v.endsWith("]")) {
			try {
				const parsed = JSON.parse(v);
				if (Array.isArray(parsed)) return parsed.filter(Boolean);
			} catch (e) {
				/* fallthrough */
			}
		}
		return v ? [v] : [];
	}
	return [];
}

function cascade_after_ward_change() {
	// When Ward changes -> reset Organization & Department (they need to be re-derived)
	frappe.query_report.set_filter_value("branch", []);
	frappe.query_report.set_filter_value("department", "");
	toggle_department_filter();
	frappe.query_report.refresh();
}

function cascade_after_branch_change() {
	// When Organization changes -> reset Department (it must re-resolve)
	frappe.query_report.set_filter_value("department", "");
	toggle_department_filter();
	frappe.query_report.refresh();
}

function toggle_department_filter() {
	const orgs = get_ms_values("branch");
	const wards = get_ms_values("ward");
	const dept_filter = frappe.query_report.get_filter("department");
	if (!dept_filter) return;

	if (orgs.length || wards.length) {
		dept_filter.df.read_only = 0;
	} else {
		frappe.query_report.set_filter_value("department", "");
		dept_filter.df.read_only = 1;
	}
	dept_filter.refresh_input();
}
