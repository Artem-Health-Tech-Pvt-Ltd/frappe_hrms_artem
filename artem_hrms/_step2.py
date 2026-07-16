import frappe


def main():
	frappe.set_user("Administrator")

	# 1. Verify Compensatory Off DocType real name
	print("=== Compensatory Off DocType lookup ===")
	for dt in frappe.get_all("DocType", filters=[["name", "like", "%Compensat%"]], pluck="name"):
		print(f"  - {dt}")

	# 2. Verify My Team / HR Dashboard / Attendance Dashboard real names
	print("\n=== Pages named 'My Team' or similar ===")
	for p in frappe.get_all("Page", filters=[["name", "like", "%My Team%"]], pluck="name"):
		print(f"  - {p}")
	for p in frappe.get_all("Page", filters=[["name", "like", "%my-team%"]], pluck="name"):
		print(f"  - {p}")

	print("\n=== Dashboards ===")
	for d in frappe.get_all("Dashboard", pluck="name"):
		print(f"  - {d}")

	print("\n=== Workspaces ===")
	for w in frappe.get_all("Workspace", pluck="name"):
		print(f"  - {w}")