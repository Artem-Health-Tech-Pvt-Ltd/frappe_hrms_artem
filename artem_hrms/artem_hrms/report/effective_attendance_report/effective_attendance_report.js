// Cache the current user's permitted branches so the multi-select dropdown
// can pre-select all of them by default and so the get_data xcall stays cheap.
let ea_permitted_branches = null;

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
			// Multi-select branch filter. Options are restricted at runtime to
			// branches the logged-in user is permitted to view. When left
			// empty, the report defaults to all permitted branches server-side.
			fieldname: "branch",
			label: __("Organization (Branch)"),
			fieldtype: "MultiSelectList",
			get_data: function (txt) {
				const selected = get_ms_values("branch");
				return frappe
					.xcall(
						"artem_hrms.artem_hrms.report.effective_attendance_report.effective_attendance_report.get_permitted_branches_for_multiselect",
						{ txt: txt || "", branches: selected }
					)
					.then((branches) =>
						(branches || []).map((b) => ({ value: b, description: "" }))
					);
			},
		},
	],

	onload: function (report) {
		// Prefetch permitted branches once per report load. On failure, leave
		// the cache as an empty list (the Python-side default will then fall
		// back to all branches, matching admin behavior).
		frappe.xcall(
			"artem_hrms.artem_hrms.report.effective_attendance_report.effective_attendance_report.get_permitted_branches"
		)
			.then((branches) => {
				ea_permitted_branches = Array.isArray(branches) ? branches : [];
				// Pre-select every permitted branch so the report shows all of
				// them by default; the user can then narrow further.
				if (ea_permitted_branches.length) {
					frappe.query_report.set_filter_value("branch", ea_permitted_branches);
				}
			})
			.catch(() => {
				ea_permitted_branches = [];
			});

		// Prominent top-right "Download Formatted Excel" button.
		report.page.set_primary_action(
			__("Download Formatted Excel"),
			function () {
				const filters = report.get_values();
				const branches = get_ms_values("branch");
				if (!branches.length) {
					frappe.msgprint(__("Please select at least one Organization (Branch) first"));
					return;
				}
				open_url_post(frappe.request.url, {
					cmd: "artem_hrms.artem_hrms.report.effective_attendance_report.effective_attendance_report.download_excel",
					filters: JSON.stringify(filters),
				});
			},
			null,
			__("Downloading...")
		);
	},

	after_datatable_render: function (datatable) {
		inject_month_group_header_effective(datatable);
	},
};

function get_ms_values(fieldname) {
	const v = frappe.query_report.get_filter_value(fieldname);
	if (!v) return [];
	if (Array.isArray(v)) return v.filter(Boolean);
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

// ---------------------------------------------------------------------------
// Grouped month header overlay (mirrors Attendance Report styling)
// ---------------------------------------------------------------------------

const EA_MONTH_NAMES = [
	"January", "February", "March", "April", "May", "June",
	"July", "August", "September", "October", "November", "December",
];
const EA_MONTH_PALETTE = [
	"#1f77b4", "#ff7f0e", "#2ca02c", "#d62728",
	"#9467bd", "#8c564b", "#e377c2", "#7f7f7f",
	"#bcbd22", "#17becf", "#393b79", "#637939",
];

function inject_month_group_header_effective(datatable) {
	try {
		const filters = frappe.query_report.get_filter_values(true) || {};
		if (!filters.from_date || !filters.to_date) return;

		const start = frappe.datetime.str_to_obj(filters.from_date);
		const end = frappe.datetime.str_to_obj(filters.to_date);
		if (!start || !end || end < start) return;

		// Build contiguous day list from filters
		const days = [];
		const d = new Date(start.getFullYear(), start.getMonth(), start.getDate());
		const e = new Date(end.getFullYear(), end.getMonth(), end.getDate());
		while (d <= e) {
			days.push(new Date(d));
			d.setDate(d.getDate() + 1);
		}
		if (!days.length) return;

		// Group day columns by (year, month)
		const groups = [];
		let cur = null;
		days.forEach((dt) => {
			const key = `${dt.getFullYear()}-${dt.getMonth()}`;
			if (!cur || cur.key !== key) {
				cur = { key, year: dt.getFullYear(), month: dt.getMonth(), count: 1 };
				groups.push(cur);
			} else {
				cur.count += 1;
			}
		});

		// Identify day columns by fieldname pattern d1..dN
		const cols = (datatable.datamanager && datatable.datamanager.columns) || [];
		const dayColIndexes = cols
			.map((c, idx) => ({ idx, fieldname: c.id || c.fieldname }))
			.filter((c) => /^d\d+$/.test(c.fieldname || ""))
			.sort((a, b) => parseInt(a.fieldname.slice(1), 10) - parseInt(b.fieldname.slice(1), 10))
			.map((c) => c.idx);
		if (!dayColIndexes.length) return;

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
			`;
			document.head.appendChild(style);
		}

		const overlay = document.createElement("div");
		overlay.className = "month-group-header";

		// Reserve space matching the 6 identity columns (Sr/Employee/Name/Designation/Joining/row_label)
		const spacer = document.createElement("div");
		spacer.style.cssText = "flex:0 0 auto; min-width:670px;"; // 60+110+170+120+100+110
		overlay.appendChild(spacer);

		groups.forEach((g) => {
			const cell = document.createElement("div");
			cell.className = "mg-cell";
			const colour = EA_MONTH_PALETTE[g.month % EA_MONTH_PALETTE.length];
			cell.textContent = `${EA_MONTH_NAMES[g.month]} ${g.year}`;
			cell.style.background = colour;
			cell.title = `${g.count} day(s)`;
			cell.style.flex = g.count + " 1 0";
			overlay.appendChild(cell);
		});

		headerRow.parentNode.insertBefore(overlay, headerRow);
	} catch (e) {
		console.warn("month-group-header (effective) failed", e);
	}
}