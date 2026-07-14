import frappe


def main():
	frappe.set_user("Administrator")

	# Look for Organization-like DocType
	print("DocType 'Organization' variants:")
	for n in frappe.get_all("DocType", filters=[["name", "like", "%rganization%"]], pluck="name"):
		print(f"  - {n}")

	print("\nReport 'palalvi' search (any):")
	for r in frappe.get_all("Report", filters=[["name", "like", "%palalvi%"]], pluck="name"):
		print(f"  - {r}")

	print("\nReport 'Shift Summary' search:")
	for r in frappe.get_all("Report", filters=[["name", "like", "%Shift Summary%"]], pluck="name"):
		print(f"  - {r}")

	print("\nReport 'Employee Hours Utilization' search:")
	for r in frappe.get_all("Report", filters=[["name", "like", "%Hours Utilization%"]], pluck="name"):
		print(f"  - {r}")

	print("\nReport 'Bulk Attendance' search:")
	for r in frappe.get_all("Report", filters=[["name", "like", "%Bulk Attendance%"]], pluck="name"):
		print(f"  - {r}")

	# Daily Work Summary Replies — could be a child table
	print("\n'Daily Work Summary Replies' as any doctype:")
	for n in frappe.get_all("DocType", filters=[["name", "like", "%Summary Reply%"]], pluck="name"):
		print(f"  - {n}")

	# How many Number Cards exist total?
	print(f"\nTotal Number Cards in DB: {frappe.db.count('Number Card')}")
	for n in frappe.get_all("Number Card", fields=["name", "label", "document_type", "function", "aggregate_function_based_on"], limit=30):
		print(f"  - {n.name:<35} label={n.label!r:<30} doctype={n.document_type} fn={n.function} based_on={n.aggregate_function_based_on}")

	# Dashboard charts
	print(f"\nTotal Dashboard Charts: {frappe.db.count('Dashboard Chart')}")
	for c in frappe.get_all("Dashboard Chart", fields=["name", "chart_type", "document_type", "based_on"], limit=50):
		print(f"  - {c.name:<35} type={c.chart_type} doctype={c.document_type} based_on={c.based_on}")

	# All workspaces — find which ones we need to touch
	print("\nWorkspaces already in artem_hrms (app filter):")
	for w in frappe.get_all("Workspace", filters=[["app", "=", "artem_hrms"]], fields=["name", "title", "module", "public", "app"]):
		print(f"  - {w.name:<30} title={w.title!r:<30} app={w.app} pub={w.public}")

	# Workspace docs that match the sidebar items (to see which exist as pages)
	print("\nWorkspaces that match requested workspace names:")
	for name in ["Employee Dashboard", "Employee Lifecycle", "Shift & Attendance",
				 "Attendance", "Human Resource", "Overview", "My Team",
				 "HR Dashboard", "Expense Claims", "Performance",
				 "Payroll", "Tax & Benefits", "Recruitment", "Leaves",
				 "HR Setup", "Home", "BMC"]:
		if frappe.db.exists("Workspace", name):
			w = frappe.get_doc("Workspace", name)
			print(f"  ✓ {name:<25} title={w.title!r:<28} app={w.app} pub={w.public} module={w.module}")
		else:
			print(f"  ✗ missing: {name}")

	print("\nWorkspaces currently owned by artem_hrms (app field):")
	all_ws = frappe.get_all("Workspace", fields=["name", "title", "module", "public", "app"])
	for w in all_ws:
		if w.app == "artem_hrms":
			print(f"  ✓ {w.name:<30} title={w.title!r:<30} module={w.module} pub={w.public}")