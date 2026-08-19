import frappe


def main():
	frappe.set_user("Administrator")

	# ============================================================
	# 1. Workspace doc: Employee Dashboard
	# ============================================================
	ws_name = "Employee Dashboard"
	if frappe.db.exists("Workspace", ws_name):
		frappe.delete_doc("Workspace", ws_name, force=True)

	ws = frappe.new_doc("Workspace")
	ws.name = ws_name
	ws.label = ws_name
	ws.title = ws_name
	ws.app = "artem_hrms"
	ws.module = "HR"
	ws.icon = "dashboard"
	ws.public = 1
	ws.is_hidden = 0
	ws.hide_custom = 0
	ws.standard = 1
	ws.for_user = ""

	# links: 3 cards, each with shortcut DocTypes
	links = [
		# ---- Card: Attendance ----
		{"type": "Card Break", "label": "Attendance", "link_count": 2, "hidden": 0, "is_query_report": 0, "onboard": 0},
		{"type": "Link", "label": "Attendance Request", "link_to": "Attendance Request", "link_type": "DocType", "hidden": 0, "is_query_report": 0, "onboard": 0},
		{"type": "Link", "label": "Employee Checkin", "link_to": "Employee Checkin", "link_type": "DocType", "hidden": 0, "is_query_report": 0, "onboard": 0},

		# ---- Card: Shift ----
		{"type": "Card Break", "label": "Shift", "link_count": 2, "hidden": 0, "is_query_report": 0, "onboard": 0},
		{"type": "Link", "label": "Shift Assignment", "link_to": "Shift Assignment", "link_type": "DocType", "hidden": 0, "is_query_report": 0, "onboard": 0},
		{"type": "Link", "label": "Shift Request", "link_to": "Shift Request", "link_type": "DocType", "hidden": 0, "is_query_report": 0, "onboard": 0},

		# ---- Card: Leave ----
		{"type": "Card Break", "label": "Leave", "link_count": 1, "hidden": 0, "is_query_report": 0, "onboard": 0},
		{"type": "Link", "label": "Leave Application", "link_to": "Leave Application", "link_type": "DocType", "hidden": 0, "is_query_report": 0, "onboard": 0},
	]

	for i, l in enumerate(links, start=1):
		ws.append("links", {**l, "idx": i})

	# shortcuts (top of page)
	shortcuts = [
		{"type": "DocType", "link_to": "Attendance Request", "label": "Attendance Request", "doc_view": "List", "stats": 0, "color": "Grey", "icon": "request"},
		{"type": "DocType", "link_to": "Employee Checkin", "label": "Employee Checkin", "doc_view": "List", "stats": 0, "color": "Grey", "icon": "checkin"},
		{"type": "DocType", "link_to": "Shift Assignment", "label": "Shift Assignment", "doc_view": "List", "stats": 0, "color": "Grey", "icon": "shift"},
		{"type": "DocType", "link_to": "Shift Request", "label": "Shift Request", "doc_view": "List", "stats": 0, "color": "Grey", "icon": "request"},
		{"type": "DocType", "link_to": "Leave Application", "label": "Leave Application", "doc_view": "List", "stats": 0, "color": "Grey", "icon": "leave"},
	]
	for i, s in enumerate(shortcuts, start=1):
		ws.append("shortcuts", {**s, "idx": i})

	# minimal content blocks so page renders
	ws.content = (
		'[{"id":"hdr-emp","type":"header","data":{"text":"<span class=\\"h4\\"><b>Quick Access</b></span>","col":12}}]'
	)
	ws.charts = []
	ws.custom_blocks = []

	ws.insert(ignore_permissions=True)
	frappe.db.commit() # nosemgrep # nosemgrep
	print(f"✓ Workspace created: {ws_name}")

	# ============================================================
	# 2. Workspace Sidebar: BMC HR
	# ============================================================
	sb_name = "BMC HR"
	if frappe.db.exists("Workspace Sidebar", sb_name):
		frappe.delete_doc("Workspace Sidebar", sb_name, force=True)

	sb = frappe.new_doc("Workspace Sidebar")
	sb.title = sb_name
	sb.app = "artem_hrms"
	sb.module = "HR"
	sb.header_icon = "hr"
	sb.standard = 1
	sb.for_user = ""

	# Item layout — matches admin screenshot order
	items = [
		# Home → Employee Dashboard workspace
		{"type": "Link", "label": "Home", "link_to": "Employee Dashboard", "link_type": "Workspace",
		 "icon": "home", "child": 0, "collapsible": 1, "indent": 0, "keep_closed": 0, "show_arrow": 0},

		# Employee Dashboard (DocType: Employee)
		{"type": "Link", "label": "Employee Dashboard", "link_to": "Employee", "link_type": "DocType",
		 "icon": "users", "child": 0, "collapsible": 1, "indent": 0, "keep_closed": 0, "show_arrow": 0},

		# Recruitment section header
		{"type": "Section Break", "label": "Recruitment", "icon": "briefcase",
		 "child": 0, "collapsible": 1, "indent": 1, "keep_closed": 1, "show_arrow": 0},
		{"type": "Link", "label": "Job Opening", "link_to": "Job Opening", "link_type": "DocType",
		 "icon": "list", "child": 1, "collapsible": 1, "indent": 0, "keep_closed": 0, "show_arrow": 0},
		{"type": "Link", "label": "Job Applicant", "link_to": "Job Applicant", "link_type": "DocType",
		 "icon": "user-plus", "child": 1, "collapsible": 1, "indent": 0, "keep_closed": 0, "show_arrow": 0},

		# Attendance (parent DocType)
		{"type": "Link", "label": "Attendance", "link_to": "Attendance", "link_type": "DocType",
		 "icon": "calendar-check", "child": 0, "collapsible": 1, "indent": 0, "keep_closed": 0, "show_arrow": 0},
		{"type": "Link", "label": "Attendance Request", "link_to": "Attendance Request", "link_type": "DocType",
		 "icon": "request", "child": 1, "collapsible": 1, "indent": 0, "keep_closed": 0, "show_arrow": 0},
		{"type": "Link", "label": "Employee Checkin", "link_to": "Employee Checkin", "link_type": "DocType",
		 "icon": "checkin", "child": 1, "collapsible": 1, "indent": 0, "keep_closed": 0, "show_arrow": 0},

		# Leaves (parent DocType)
		{"type": "Link", "label": "Leaves", "link_to": "Leave Application", "link_type": "DocType",
		 "icon": "calendar-minus", "child": 0, "collapsible": 1, "indent": 0, "keep_closed": 0, "show_arrow": 0},
		{"type": "Link", "label": "Compensatory Off", "link_to": "Compensatory Leave Request", "link_type": "DocType",
		 "icon": "calendar-plus", "child": 1, "collapsible": 1, "indent": 0, "keep_closed": 0, "show_arrow": 0},

		# Employee Lifecycle (Dashboard exists for this)
		{"type": "Link", "label": "Employee Lifecycle", "link_to": "Employee Lifecycle", "link_type": "Dashboard",
		 "icon": "trending-up", "child": 0, "collapsible": 1, "indent": 0, "keep_closed": 0, "show_arrow": 0},

		# Expense Claims
		{"type": "Link", "label": "Expense Claims", "link_to": "Expense Claims", "link_type": "Dashboard",
		 "icon": "wallet", "child": 0, "collapsible": 1, "indent": 0, "keep_closed": 0, "show_arrow": 0},

		# Performance (Dashboard)
		{"type": "Link", "label": "Performance", "link_to": "Performance", "link_type": "Workspace",
		 "icon": "star", "child": 0, "collapsible": 1, "indent": 0, "keep_closed": 0, "show_arrow": 0},

		# Salary Payout (Workspace)
		{"type": "Link", "label": "Salary Payout", "link_to": "Payroll", "link_type": "Workspace",
		 "icon": "money-bill", "child": 0, "collapsible": 1, "indent": 0, "keep_closed": 0, "show_arrow": 0},

		# Tax & Benefits (Workspace)
		{"type": "Link", "label": "Tax & Benefits", "link_to": "Tax & Benefits", "link_type": "Workspace",
		 "icon": "percent", "child": 0, "collapsible": 1, "indent": 0, "keep_closed": 0, "show_arrow": 0},

		# HR Dashboard
		{"type": "Link", "label": "HR Dashboard", "link_to": "Human Resource", "link_type": "Dashboard",
		 "icon": "layout-dashboard", "child": 0, "collapsible": 1, "indent": 0, "keep_closed": 0, "show_arrow": 0},

		# Attendance Dashboard
		{"type": "Link", "label": "Attendance Dashboard", "link_to": "Attendance", "link_type": "Dashboard",
		 "icon": "bar-chart-3", "child": 0, "collapsible": 1, "indent": 0, "keep_closed": 0, "show_arrow": 0},

		# My Team — fallback as Workspace if no Page exists
		{"type": "Link", "label": "My Team", "link_to": "Home", "link_type": "Workspace",
		 "icon": "users-round", "child": 0, "collapsible": 1, "indent": 0, "keep_closed": 0, "show_arrow": 0},

		# Overview (Workspace)
		{"type": "Link", "label": "Overview", "link_to": "HR Setup", "link_type": "Workspace",
		 "icon": "layout-dashboard", "child": 0, "collapsible": 1, "indent": 0, "keep_closed": 0, "show_arrow": 0},
	]

	for i, it in enumerate(items, start=1):
		sb.append("items", {**it, "idx": i})

	sb.insert(ignore_permissions=True)
	frappe.db.commit() # nosemgrep
	print(f"✓ Workspace Sidebar created: {sb_name}")

	# ============================================================
	# 3. Desktop Icon (entry point for BMC HR)
	# ============================================================
	di_name = "BMC HR"
	if frappe.db.exists("Desktop Icon", di_name):
		frappe.delete_doc("Desktop Icon", di_name, force=True)

	di = frappe.new_doc("Desktop Icon")
	di.label = di_name
	di.module_name = "HR"
	di.link_to = sb_name
	di.link_type = "Workspace Sidebar"
	di.icon = "milestone"
	di.icon_type = "Link"
	di.app = "artem_hrms"
	di.standard = 1
	di.parent_icon = "Frappe HR"
	di.hidden = 0
	di.restrict_removal = 0
	di.roles = []

	di.insert(ignore_permissions=True)
	frappe.db.commit() # nosemgrep
	print(f"✓ Desktop Icon created: {di_name}")

	print("\nAll three docs created. Auto-export to fixtures runs on next save via dev mode hooks.")
	print("Run: bench --site hrms.com migrate to pull fixtures via hooks.py")