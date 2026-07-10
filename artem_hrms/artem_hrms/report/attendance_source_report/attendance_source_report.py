# Copyright (c) 2026
# Attendance Source Report - server side logic
#
# Fieldname configuration:
BRANCH_WARD_FIELD = "custom_ward"      # Ward field on Branch doctype
EMPLOYEE_HOD_FIELD = "custom_hod"             # HOD field on Employee (stores Employee ID of HOD)
CHECKIN_SOURCE_FIELD = "custom_source" # Source field on Employee Checkin (Data)
                                       # "Biometric" -> Biometric, empty/null -> Web,
                                       # value containing "mobile" -> Mobile App

import frappe
from frappe import _
from frappe.utils import getdate


def execute(filters=None):
	filters = frappe._dict(filters or {})
	validate_filters(filters)

	columns = get_columns()
	data = get_data(filters)
	return columns, data


def validate_filters(filters):
	if not filters.from_date or not filters.to_date:
		frappe.throw(_("From Date and To Date are mandatory"))

	if getdate(filters.from_date) > getdate(filters.to_date):
		frappe.throw(_("From Date cannot be after To Date"))

	# Department filter is only valid when Organization (Branch) is chosen
	if filters.department and not filters.branch:
		frappe.throw(_("Please select an Organization (Branch) before filtering by Department"))


def get_columns():
	return [
		{"label": _("Sr. No."), "fieldname": "sr_no", "fieldtype": "Int", "width": 70},
		{"label": _("Ward Name"), "fieldname": "ward", "fieldtype": "Data", "width": 120},
		{"label": _("Organization (Branch)"), "fieldname": "branch", "fieldtype": "Link", "options": "Branch", "width": 150},
		{"label": _("Employee ID"), "fieldname": "employee", "fieldtype": "Link", "options": "Employee", "width": 110},
		{"label": _("Employee Name"), "fieldname": "employee_name", "fieldtype": "Data", "width": 180},
		{"label": _("Department Name"), "fieldname": "department", "fieldtype": "Link", "options": "Department", "width": 140},
		{"label": _("Attendance Date"), "fieldname": "attendance_date", "fieldtype": "Date", "width": 110},
		{"label": _("HOD"), "fieldname": "hod_name", "fieldtype": "Data", "width": 150},
		{"label": _("Attendance Marked"), "fieldname": "attendance_marked", "fieldtype": "Data", "width": 100},
		{"label": _("Check-In Source"), "fieldname": "check_in_source", "fieldtype": "Data", "width": 110},
		{"label": _("Check-Out Source"), "fieldname": "check_out_source", "fieldtype": "Data", "width": 110},
		{"label": _("Attendance"), "fieldname": "attendance", "fieldtype": "Data", "width": 100},
		{"label": _("Shift Time"), "fieldname": "shift_time", "fieldtype": "Data", "width": 120},
		{"label": _("Check-In Time"), "fieldname": "check_in_time", "fieldtype": "Data", "width": 100},
		{"label": _("Check-Out Time"), "fieldname": "check_out_time", "fieldtype": "Data", "width": 100},
		{"label": _("Late Punch"), "fieldname": "late_punch", "fieldtype": "Data", "width": 90},
		{"label": _("Early Out"), "fieldname": "early_out", "fieldtype": "Data", "width": 90},
		{"label": _("Missed Punch"), "fieldname": "missed_punch", "fieldtype": "Data", "width": 100},
	]


def get_data(filters):
	# CHANGED: rows are now driven by the Attendance list.
	# One report row per submitted Attendance record in the date range.
	attendance_records = get_attendance_records(filters)
	if not attendance_records:
		return []

	employee_ids = list({rec.employee for rec in attendance_records})

	checkin_map = get_checkin_map(filters, employee_ids)
	shift_map = get_shift_map()

	data = []
	for sr_no, att in enumerate(attendance_records, start=1):
		key = (att.employee, getdate(att.attendance_date))
		checkins = checkin_map.get(key, [])

		row = build_row(att, checkins, shift_map)
		row["sr_no"] = sr_no
		data.append(row)

	return data


def get_attendance_records(filters):
	# CHANGED: was get_employees(). Now the query starts from Attendance and
	# joins Employee / Branch / HOD to fill the linked-doctype columns.
	# All filters (branch, ward, department) apply to these attendance rows.
	Attendance = frappe.qb.DocType("Attendance")
	Employee = frappe.qb.DocType("Employee")
	Branch = frappe.qb.DocType("Branch")
	# Self-join on Employee to resolve HOD's employee ID -> HOD's name
	HOD = frappe.qb.DocType("Employee").as_("hod_emp")

	query = (
		frappe.qb.from_(Attendance)
		.inner_join(Employee)
		.on(Attendance.employee == Employee.name)
		.left_join(Branch)
		.on(Employee.branch == Branch.name)
		.left_join(HOD)
		.on(Employee[EMPLOYEE_HOD_FIELD] == HOD.name)
		.select(
			Attendance.employee,
			Attendance.employee_name,
			Attendance.attendance_date,
			Attendance.status,
			Attendance.shift,
			Attendance.in_time,
			Attendance.out_time,
			Attendance.late_entry,
			Attendance.early_exit,
			Employee.branch,
			Employee.department,
			Employee.default_shift,
			Branch[BRANCH_WARD_FIELD].as_("ward"),
			HOD.employee_name.as_("hod_name"),
		)
		.where(Attendance.docstatus == 1)
		.where(Attendance.attendance_date >= filters.from_date)
		.where(Attendance.attendance_date <= filters.to_date)
		.orderby(Attendance.attendance_date)
		.orderby(Attendance.employee)
	)

	if filters.get("branch"):
		query = query.where(Employee.branch == filters.branch)
	if filters.get("ward"):
		query = query.where(Branch[BRANCH_WARD_FIELD] == filters.ward)
	if filters.get("department"):
		query = query.where(Employee.department == filters.department)

	return query.run(as_dict=True)


def get_checkin_map(filters, employee_ids):
	checkins = frappe.get_all(
		"Employee Checkin",
		filters={
			"employee": ["in", employee_ids],
			"time": [
				"between",
				[f"{filters.from_date} 00:00:00", f"{filters.to_date} 23:59:59"],
			],
		},
		fields=["employee", "time", "log_type", CHECKIN_SOURCE_FIELD],
		order_by="time asc",
	)

	checkin_map = {}
	for c in checkins:
		key = (c.employee, getdate(c.time))
		checkin_map.setdefault(key, []).append(c)
	return checkin_map


def get_shift_map():
	shifts = frappe.get_all("Shift Type", fields=["name", "start_time", "end_time"])
	return {s.name: s for s in shifts}


def get_source_label(checkin):
	"""
	Map the Employee Checkin source field (custom_source) to a display label:
	  - "Biometric"                -> "Biometric"
	  - empty / null               -> "Web"
	  - value containing "mobile"  -> "Mobile App"
	  - any other value            -> shown as-is
	"""
	if not checkin:
		return ""

	source = (checkin.get(CHECKIN_SOURCE_FIELD) or "").strip()
	if not source:
		return "Web"
	if source.lower() == "biometric":
		return "Biometric"
	if "mobile" in source.lower():
		return "Mobile App"
	return source


def get_first_in_and_last_out(checkins):
	"""
	First IN log of the day  -> check-in
	Last OUT log of the day  -> check-out
	(checkins list is already sorted by time asc)
	"""
	in_logs = [c for c in checkins if c.log_type == "IN"]
	out_logs = [c for c in checkins if c.log_type == "OUT"]

	first_in = in_logs[0] if in_logs else None
	last_out = out_logs[-1] if out_logs else None
	return first_in, last_out


def yes_no(value):
	return "Yes" if value else "No"


def get_attendance_status_label(status):
	"""Map Attendance status to the single 'Attendance' column value."""
	if not status:
		return ""
	if status == "On Leave":
		return "Leave"
	return status  # Present / Absent / Half Day / Work From Home


def fmt_time(value):
	"""Format datetime / timedelta / time to HH:MM string."""
	if value is None:
		return ""
	# timedelta (Shift Type start/end times come as timedelta)
	if hasattr(value, "total_seconds") and not hasattr(value, "hour"):
		total_minutes = int(value.total_seconds() // 60)
		return f"{total_minutes // 60:02d}:{total_minutes % 60:02d}"
	# datetime / time
	try:
		return value.strftime("%H:%M")
	except Exception:
		return str(value)


def build_row(att, checkins, shift_map):
	# CHANGED: takes the attendance record directly (it already carries the
	# joined Employee / Branch / HOD values). Every row has an attendance record.

	# First IN = check-in, Last OUT = check-out (from Employee Checkin)
	first_in, last_out = get_first_in_and_last_out(checkins)

	check_in_source = get_source_label(first_in)
	check_out_source = get_source_label(last_out)

	# Check-in / check-out times: prefer the actual checkin logs,
	# fall back to Attendance in/out time if no logs exist
	in_time = first_in.time if first_in else att.in_time
	out_time = last_out.time if last_out else att.out_time

	# Shift: prefer the shift on the attendance record, fall back to employee default
	shift_name = att.shift or att.default_shift
	shift = shift_map.get(shift_name)
	shift_time = (
		f"{fmt_time(shift.start_time)} - {fmt_time(shift.end_time)}" if shift else ""
	)

	# Late punch / early out from the HRMS flags on the attendance record
	late_punch = bool(att.late_entry)
	early_out = bool(att.early_exit)

	# Missed punch: one of IN/OUT exists but not the other
	missed_punch = bool(in_time) != bool(out_time)

	return {
		"ward": att.ward,
		"branch": att.branch,
		"employee": att.employee,
		"employee_name": att.employee_name,
		"department": att.department,
		"attendance_date": att.attendance_date,
		"hod_name": att.hod_name,
		"attendance_marked": "Yes",  # a row only exists when attendance is marked
		"check_in_source": check_in_source,
		"check_out_source": check_out_source,
		"attendance": get_attendance_status_label(att.status),
		"shift_time": shift_time,
		"check_in_time": fmt_time(in_time),
		"check_out_time": fmt_time(out_time),
		"late_punch": yes_no(late_punch),
		"early_out": yes_no(early_out),
		"missed_punch": yes_no(missed_punch),
	}