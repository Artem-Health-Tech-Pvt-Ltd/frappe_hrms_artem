import frappe
from frappe import _

# Custom field on Branch that, when checked, blocks web/manual check-ins for
# any employee whose branch is set to that branch.
WEB_CHECKIN_RESTRICTION_FIELD = "custom_restrict_web_checkin"

# Check-ins coming from the biometric sync set this; everything else (manual
# entry, web form, API, etc.) is treated as a "web" check-in.
BIOMETRIC_SOURCE = "Biometric"


def employee_validation(doc, method=None):
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

    def validate_distance_from_shift_location(self):
        if self.custom_source == "Biometric":
            return

        super().validate_distance_from_shift_location()
