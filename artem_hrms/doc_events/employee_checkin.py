import frappe
from frappe import _
from frappe.utils import get_datetime

# Custom field on Branch that, when checked, blocks web/manual check-ins for
# any employee whose branch is set to that branch.
WEB_CHECKIN_RESTRICTION_FIELD = "custom_restrict_web_checkin"

# Check-ins coming from the biometric sync set this; everything else (manual
# entry, web form, API, etc.) is treated as a "web" check-in.
BIOMETRIC_SOURCE = "Biometric"

BRANCH_MAPPING = {
	"Lokmanya Tilak Municipal Medical College and General Hospital Sion": (
		"Lokmanya Tilak Municipal Medical College and General Hospital, Sion"
	)
}


def normalize_branch_name(value):
	if value and str(value).strip() in BRANCH_MAPPING:
		return BRANCH_MAPPING[str(value).strip()]
	return value


def normalize_checkin_branch(doc):
	"""Normalize branch name if received without comma in checkin payload."""
	if not doc:
		return

	if doc.get("branch"):
		normalized = normalize_branch_name(doc.get("branch"))
		if hasattr(doc, "set"):
			doc.set("branch", normalized)
		else:
			doc["branch"] = normalized

		if not doc.get("custom_branch"):
			if hasattr(doc, "set"):
				doc.set("custom_branch", normalized)
			else:
				doc["custom_branch"] = normalized

	if doc.get("custom_branch"):
		normalized = normalize_branch_name(doc.get("custom_branch"))
		if hasattr(doc, "set"):
			doc.set("custom_branch", normalized)
		else:
			doc["custom_branch"] = normalized


@frappe.whitelist()
def get_next_log_type_for_employee(employee, timestamp=None, current_doc_name=None):
	"""Determine whether log_type should be IN or OUT for an employee on a given timestamp.

	Rules:
	- 24-hour day window (00:00:00 to 23:59:59) - resets every midnight.
	- 1st log of the day (odd)  -> IN
	- 2nd log of the day (even) -> OUT
	- 3rd log of the day (odd)  -> IN
	- 4th log of the day (even) -> OUT
	- Odd check-in = IN, Even check-in = OUT.
	- Independent of device (Web check-in or Biometric device).
	- Overrides whatever log_type was provided by vendor or user.
	"""
	if not employee:
		return "IN"

	checkin_dt = get_datetime(timestamp) if timestamp else frappe.utils.now_datetime()
	start_of_day = checkin_dt.replace(hour=0, minute=0, second=0, microsecond=0)
	end_of_day = checkin_dt.replace(hour=23, minute=59, second=59, microsecond=999999)

	filters = {
		"employee": employee,
		"time": ["between", [start_of_day, end_of_day]],
		"docstatus": ["<", 2],
	}
	if current_doc_name:
		filters["name"] = ["!=", current_doc_name]

	existing_logs = frappe.get_all(
		"Employee Checkin",
		filters=filters,
		fields=["name", "time"],
		order_by="time asc, creation asc",
	)

	prior_logs_count = 0
	for log in existing_logs:
		log_time_val = log.get("time") if isinstance(log, dict) else getattr(log, "time", None)
		if not log_time_val:
			continue
		log_time = get_datetime(log_time_val)
		log_name = log.get("name") if isinstance(log, dict) else getattr(log, "name", None)

		if log_time < checkin_dt:
			prior_logs_count += 1
		elif log_time == checkin_dt:
			if current_doc_name and log_name != current_doc_name:
				prior_logs_count += 1
			elif not current_doc_name:
				prior_logs_count += 1

	return "IN" if (prior_logs_count % 2 == 0) else "OUT"


def assign_dynamic_log_type(doc):
	"""Calculate and set log_type based on alternating IN/OUT for the 24-hour day."""
	if not doc:
		return

	employee = doc.get("employee")
	checkin_time = doc.get("time")

	if not employee or not checkin_time:
		return

	doc_name = doc.get("name") if not getattr(doc, "__islocal", False) else None
	log_type = get_next_log_type_for_employee(employee, checkin_time, current_doc_name=doc_name)

	if hasattr(doc, "set"):
		doc.set("log_type", log_type)
	else:
		doc["log_type"] = log_type


def employee_validation(doc, method=None):
	normalize_checkin_branch(doc)
	assign_dynamic_log_type(doc)

	employee = frappe.db.get_value(
		"Employee",
		doc.employee,
		["status", "relieving_date", "employee_name"],
		as_dict=True
	)

	if not employee:
		frappe.throw(_("Employee not found."))

	# Allow check-in only for Active employees
	if employee.status != "Active":
		frappe.throw(
			_("Check-in is not allowed because Employee '{0}' is {1}.").format(
				employee.employee_name, employee.status
			)
		)

	# Prevent check-in after relieving date
	if employee.relieving_date:
		checkin_date = frappe.utils.getdate(doc.time)
		relieving_date = frappe.utils.getdate(employee.relieving_date)

		if checkin_date > relieving_date:
			frappe.throw(
				_("Check-in is not allowed because Employee '{0}' has been relieved on {1}.").format(
					employee.employee_name, relieving_date
				)
			)


def restrict_web_checkin(doc, method=None):
	"""before_insert hook: block web/manual check-ins for restricted branches.

	Biometric syncs set `custom_source = "Biometric"` and pass through.
	"""
	normalize_checkin_branch(doc)
	assign_dynamic_log_type(doc)

	if (doc.get("custom_source") or "").strip() == BIOMETRIC_SOURCE:
		return

	employee = doc.get("employee")
	if not employee:
		return

	branch = (
		doc.get("custom_branch")
		or frappe.db.get_value("Employee", employee, "branch")
	)
	if not branch:
		return

	restricted = frappe.db.get_value("Branch", branch, WEB_CHECKIN_RESTRICTION_FIELD)
	if not restricted:
		return

	employee_name = frappe.db.get_value("Employee", employee, "employee_name") or employee
	frappe.throw(
		_(
			"Web check-in is disabled for branch '{0}'. Employee '{1}' must use the biometric device to check in."
		).format(branch, employee_name)
	)


@frappe.whitelist()
def is_branch_web_checkin_restricted_for_user(user=None):
	"""Return True if `user`'s employee's branch has web check-in disabled.

	Used by the client script to redirect the user away from the new
	check-in form before it renders.
	"""
	user = user or frappe.session.user
	row = frappe.db.sql(
		"""
		SELECT b.{field} AS restricted
		FROM `tabEmployee` e
		LEFT JOIN `tabBranch` b ON b.name = e.branch
		WHERE e.user_id = %(user)s OR e.name = %(user)s
		LIMIT 1
		""".format(field=WEB_CHECKIN_RESTRICTION_FIELD),
		{"user": user},
		as_dict=True,
	)
	if not row:
		return False
	return bool(row[0].get("restricted"))


@frappe.whitelist()
def is_employee_branch_web_checkin_restricted(employee):
	"""Return True if the given employee's branch has web check-in disabled.

	Used by the client script when an employee is selected on the form.
	"""
	if not employee:
		return False
	row = frappe.db.sql(
		"""
		SELECT b.{field} AS restricted
		FROM `tabEmployee` e
		LEFT JOIN `tabBranch` b ON b.name = e.branch
		WHERE e.name = %(employee)s
		LIMIT 1
		""".format(field=WEB_CHECKIN_RESTRICTION_FIELD),
		{"employee": employee},
		as_dict=True,
	)
	if not row:
		return False
	return bool(row[0].get("restricted"))




from hrms.hr.doctype.employee_checkin.employee_checkin import EmployeeCheckin

class CustomEmployeeCheckin(EmployeeCheckin):

    def validate(self):
        normalize_checkin_branch(self)
        assign_dynamic_log_type(self)
        super().validate()

    def before_insert(self):
        normalize_checkin_branch(self)
        assign_dynamic_log_type(self)
        if hasattr(super(), "before_insert"):
            super().before_insert()

    def validate_distance_from_shift_location(self):
        if self.custom_source == "Biometric":
            return

        super().validate_distance_from_shift_location()
