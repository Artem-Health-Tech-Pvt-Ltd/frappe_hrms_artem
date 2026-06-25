import frappe
from frappe import _

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