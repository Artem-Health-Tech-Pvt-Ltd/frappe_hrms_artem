import frappe


def main():
	frappe.set_user("Administrator")

	roles_to_check = ["Employee"]
	doctypes_to_check = [
		"Employee", "Attendance", "Leave Application",
		"Shift Assignment", "Shift Request", "Employee Checkin",
		"Attendance Request", "Job Opening", "Job Applicant",
		"Expense Claim", "Appraisal", "Salary Slip",
		"Employee Tax Exemption Declaration", "Employee Benefit Claim",
		"Compensatory Off Request",
	]

	print(f"{'DocType':<45} {'Employee role read?'}  (std_perms / custom_perms)")
	print("-" * 90)
	for dt in doctypes_to_check:
		if not frappe.db.exists("DocType", dt):
			print(f"{dt:<45} (DocType does not exist)")
			continue
		std_perms = frappe.get_all(
			"DocPerm",
			filters={"parent": dt, "role": ["in", roles_to_check], "read": 1},
			fields=["role"],
		)
		custom_perms = frappe.get_all(
			"Custom DocPerm",
			filters={"parent": dt, "role": ["in", roles_to_check], "read": 1},
			fields=["role"],
		)
		in_perm = bool(std_perms or custom_perms)
		print(f"{dt:<45} {'YES' if in_perm else 'no':<15}  std={len(std_perms)} custom={len(custom_perms)}")