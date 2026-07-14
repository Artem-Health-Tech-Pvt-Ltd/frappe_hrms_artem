# Copyright (c) 2026
# Attendance Report - server side logic
#
# One row per employee per month in the selected date range.
# Day columns 1..31 show: P = Present, HD = Half Day, A = Absent,
# leave days show the Leave Type abbreviation (Casual Leave -> CL,
# Sick Leave -> SL, ...), or "L" if no leave type is set.
#
# Filters:
#   1) Date range (mandatory)
#   2) Ward       - multi select (values come from Branch.custom_ward)
#   3) Branch     - multi select
#   4) Department - multi select, only usable when Branch is selected
#
# Fieldname configuration:
BRANCH_WARD_FIELD = "custom_ward"  # Ward field on Branch doctype

import frappe
from frappe import _
from frappe.utils import formatdate, getdate

NUM_DAY_COLUMNS = 31


def execute(filters=None):
	filters = frappe._dict(filters or {})
	filters.branch = parse_list(filters.get("branch"))
	filters.ward = parse_list(filters.get("ward"))
	filters.department = parse_list(filters.get("department"))

	validate_filters(filters)

	columns = get_columns()
	data = get_data(filters)
	return columns, data


def parse_list(value):
	"""MultiSelectList filters arrive as JSON strings; normalize to a list."""
	if not value:
		return []
	if isinstance(value, str):
		value = frappe.parse_json(value)
	return value or []


def validate_filters(filters):
	if not filters.get("from_date") or not filters.get("to_date"):
		frappe.throw(_("From Date and To Date are mandatory"))

	if getdate(filters.from_date) > getdate(filters.to_date):
		frappe.throw(_("From Date cannot be after To Date"))

	# Department filter is only valid when at least one Branch is chosen
	if filters.department and not filters.branch:
		frappe.throw(_("Please select at least one Organization (Branch) before filtering by Department"))


def get_columns():
	columns = [
		{"label": _("Sr. No."), "fieldname": "sr_no", "fieldtype": "Int", "width": 60},
		{"label": _("Ward"), "fieldname": "ward", "fieldtype": "Data", "width": 100},
		{"label": _("Organization"), "fieldname": "branch", "fieldtype": "Link", "options": "Branch", "width": 140},
		{"label": _("Employee ID"), "fieldname": "employee", "fieldtype": "Link", "options": "Employee", "width": 110},
		{"label": _("Employee Name"), "fieldname": "employee_name", "fieldtype": "Data", "width": 160},
		{"label": _("Department"), "fieldname": "department", "fieldtype": "Link", "options": "Department", "width": 130},
		{"label": _("Designation"), "fieldname": "designation", "fieldtype": "Data", "width": 110},
		{"label": _("Month"), "fieldname": "month", "fieldtype": "Data", "width": 80},
	]

	for day in range(1, NUM_DAY_COLUMNS + 1):
		columns.append(
			{"label": str(day), "fieldname": f"d{day}", "fieldtype": "Data", "width": 42}
		)

	columns += [
		{"label": _("Total Present"), "fieldname": "total_present", "fieldtype": "Int", "width": 90},
		{"label": _("Total Absent"), "fieldname": "total_absent", "fieldtype": "Int", "width": 90},
		{"label": _("Total Leave"), "fieldname": "total_leave", "fieldtype": "Int", "width": 90},
		{"label": _("Remarks"), "fieldname": "remarks", "fieldtype": "Data", "width": 120},
	]

	return columns


def leave_abbreviation(leave_type):
	"""Casual Leave -> CL, Sick Leave -> SL, Leave Without Pay -> LWP ..."""
	if not leave_type:
		return "L"
	return "".join(word[0] for word in leave_type.split() if word).upper()


def day_value(status, leave_type):
	if status in ("Present", "Work From Home"):
		return "P"
	if status == "Half Day":
		return "HD"
	if status == "Absent":
		return "A"
	if status == "On Leave":
		return leave_abbreviation(leave_type)
	return ""


def get_attendance_records(filters):
	Attendance = frappe.qb.DocType("Attendance")
	Employee = frappe.qb.DocType("Employee")
	Branch = frappe.qb.DocType("Branch")

	query = (
		frappe.qb.from_(Attendance)
		.inner_join(Employee)
		.on(Attendance.employee == Employee.name)
		.left_join(Branch)
		.on(Employee.branch == Branch.name)
		.select(
			Attendance.employee,
			Attendance.employee_name,
			Attendance.attendance_date,
			Attendance.status,
			Attendance.leave_type,
			Employee.branch,
			Employee.department,
			Employee.designation,
			Branch[BRANCH_WARD_FIELD].as_("ward"),
		)
		.where(Attendance.docstatus == 1)
		.where(Attendance.attendance_date >= filters.from_date)
		.where(Attendance.attendance_date <= filters.to_date)
		.orderby(Attendance.employee)
		.orderby(Attendance.attendance_date)
	)

	if filters.branch:
		query = query.where(Employee.branch.isin(filters.branch))
	if filters.ward:
		query = query.where(Branch[BRANCH_WARD_FIELD].isin(filters.ward))
	if filters.department:
		query = query.where(Employee.department.isin(filters.department))

	return query.run(as_dict=True)


def get_data(filters):
	records = get_attendance_records(filters)
	if not records:
		return []

	# group by (employee, year, month)
	grouped = {}
	for rec in records:
		date = getdate(rec.attendance_date)
		key = (rec.employee, date.year, date.month)
		group = grouped.setdefault(
			key,
			{
				"ward": rec.ward,
				"branch": rec.branch,
				"employee": rec.employee,
				"employee_name": rec.employee_name,
				"department": rec.department,
				"designation": rec.designation,
				"month": formatdate(rec.attendance_date, "MMM-yy"),
				"_year": date.year,
				"_month": date.month,
				"days": {},
				"leave_counts": {},
			},
		)
		value = day_value(rec.status, rec.leave_type)
		group["days"][date.day] = value

		if rec.status == "On Leave":
			abbr = leave_abbreviation(rec.leave_type)
			group["leave_counts"][abbr] = group["leave_counts"].get(abbr, 0) + 1

	# sort: employee name, then chronologically by month
	groups = sorted(
		grouped.values(),
		key=lambda g: ((g["employee_name"] or ""), g["_year"], g["_month"]),
	)

	data = []
	for sr_no, group in enumerate(groups, start=1):
		row = {
			"sr_no": sr_no,
			"ward": group["ward"],
			"branch": group["branch"],
			"employee": group["employee"],
			"employee_name": group["employee_name"],
			"department": group["department"],
			"designation": group["designation"],
			"month": group["month"],
		}

		total_present = total_absent = total_leave = 0
		for day in range(1, NUM_DAY_COLUMNS + 1):
			value = group["days"].get(day, "")
			row[f"d{day}"] = value
			if value in ("P", "HD"):
				total_present += 1
			elif value == "A":
				total_absent += 1
			elif value:  # any leave abbreviation (CL, SL, L, ...)
				total_leave += 1

		row["total_present"] = total_present
		row["total_absent"] = total_absent
		row["total_leave"] = total_leave

		if group["leave_counts"]:
			row["remarks"] = ", ".join(
				f"{count} {abbr}" for abbr, count in sorted(group["leave_counts"].items())
			)
		else:
			row["remarks"] = "-"

		data.append(row)

	return data


@frappe.whitelist()
def get_ward_options(txt=""):
	"""Distinct ward values from Branch, for the Ward MultiSelectList filter."""
	filters = {}
	if txt:
		filters[BRANCH_WARD_FIELD] = ["like", f"%{txt}%"]

	wards = frappe.get_all(
		"Branch",
		filters=filters,
		pluck=BRANCH_WARD_FIELD,
		distinct=True,
	)
	return sorted({w for w in wards if w})