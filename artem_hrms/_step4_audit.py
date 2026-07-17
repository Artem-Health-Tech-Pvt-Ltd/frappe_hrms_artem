import frappe


def main():
	frappe.set_user("Administrator")

	def has(doctype, name):
		return bool(frappe.db.exists(doctype, name))

	print("=" * 70)
	print("DOCTYPES referenced in workspaces")
	print("=" * 70)
	doctypes = [
		"Attendance Request", "Employee Checkin", "Shift Assignment",
		"Shift Request", "Leave Application", "Employee Onboarding",
		"Employee Promotion", "Employee Transfer", "Employee",
		"Training Program", "Training Event", "Training Feedback",
		"Training Result", "Grievance Type", "Employee Grievance",
		"Daily Work Summary", "Daily Work Summary Group",
		"Daily Work Summary Replies", "Compensatory Leave Request",
		"Employee Onboarding Template", "Employee Skill Map",
		"Employee Attendance Tool", "Upload Attendance",
		"Shift Assignment Tool", "Organization", "Department",
		"Designation", "Shift Location", "Shift Schedule",
		"Shift Type", "Shift Schedule Assignment",
	]
	for dt in doctypes:
		print(f"  {'✓' if has('DocType', dt) else '✗ MISSING':<10} {dt}")

	print("\n" + "=" * 70)
	print("REPORTS referenced (palalvi, Shift Summary, etc.)")
	print("=" * 70)
	reports = [
		"palalvi", "Shift Summary", "Monthly Attendance Sheet",
		"Shift Attendance", "Employee Hours Utilization Based On Shift",
		"Employees Working on a Holiday", "Employee Exits",
		"Employee Birthday", "Employee Information", "Employee Analytics",
		"Bulk Attendance",
	]
	for r in reports:
		print(f"  {'✓' if has('Report', r) else '✗ MISSING':<10} {r}")

	print("\n" + "=" * 70)
	print("DASHBOARDS referenced")
	print("=" * 70)
	dashboards = ["Human Resource", "Attendance", "Employee Lifecycle",
				  "Expense Claims", "Recruitment", "Payroll"]
	for d in dashboards:
		print(f"  {'✓' if has('Dashboard', d) else '✗ MISSING':<10} {d}")

	print("\n" + "=" * 70)
	print("NUMBER CARDS referenced (HR Dashboard)")
	print("=" * 70)
	# search by name pattern
	nc = frappe.get_all("Number Card",
						filters=[["name", "in", [
							"Total Employee", "Present Today", "Absent Today",
							"Half Day Today", "Checkins Today",
							"Pending Regularization",
						]]],
						fields=["name", "document_type", "label",
								"function", "aggregate_function_based_on",
								"filters_json", "show_percentage_stats",
								"stats_time_interval"])
	for n in nc:
		print(f"  ✓ {n.name:<35} doctype={n.document_type} fn={n.function} based_on={n.aggregate_function_based_on}")
	for n in ["Total Employee", "Present Today", "Absent Today",
			  "Half Day Today", "Checkins Today", "Pending Regularization"]:
		if not has("Number Card", n):
			print(f"  ✗ MISSING  {n}")

	print("\n" + "=" * 70)
	print("DASHBOARD CHARTS referenced")
	print("=" * 70)
	for c in ["Attendance Count", "Shift-wise Employee Count"]:
		if has("Dashboard Chart", c):
			cd = frappe.get_doc("Dashboard Chart", c)
			print(f"  ✓ {c:<35} chart_type={cd.chart_type} doctype={cd.document_type}")
		else:
			print(f"  ✗ MISSING  {c}")

	print("\n" + "=" * 70)
	print("CUSTOM HTML BLOCKS (Attendance Log etc.)")
	print("=" * 70)
	for b in frappe.get_all("Custom HTML Block", pluck="name"):
		if "ttendance" in b.lower() or "log" in b.lower():
			print(f"  ✓ {b}")
	print("\nAll Custom HTML Blocks:")
	for b in frappe.get_all("Custom HTML Block", pluck="name"):
		print(f"  - {b}")