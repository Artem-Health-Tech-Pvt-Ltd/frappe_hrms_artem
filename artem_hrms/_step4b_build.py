import json

import frappe


def main():
	frappe.set_user("Administrator")

	ws_name = "Employee Dashboard"
	if not frappe.db.exists("Workspace", ws_name):
		print(f"Workspace {ws_name} does not exist; aborting")
		return

	frappe.delete_doc("Workspace", ws_name, force=True)
	frappe.db.commit()

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
	ws.for_user = ""

	# ------------------------------------------------------------------
	# Shortcuts (top row tiles, with count badges)
	# ------------------------------------------------------------------
	shortcuts = [
		{
			"type": "DocType", "link_to": "Attendance Request",
			"label": "Attendance Request", "doc_view": "List",
			"stats": 1, "color": "Grey", "icon": "request",
		},
		{
			"type": "DocType", "link_to": "Employee Checkin",
			"label": "Employee Checkin", "doc_view": "List",
			"stats": 1, "color": "Grey", "icon": "checkin",
		},
		{
			"type": "DocType", "link_to": "Shift Assignment",
			"label": "Shift Assignment", "doc_view": "List",
			"stats": 1, "color": "Grey", "icon": "shift",
		},
		{
			"type": "DocType", "link_to": "Shift Request",
			"label": "Shift Request", "doc_view": "List",
			"stats": 1, "color": "Grey", "icon": "request",
		},
		{
			"type": "DocType", "link_to": "Leave Application",
			"label": "Leave Application", "doc_view": "List",
			"stats": 1, "color": "Grey", "icon": "leave",
		},
	]
	for i, s in enumerate(shortcuts, start=1):
		ws.append("shortcuts", {**s, "idx": i})

	# ------------------------------------------------------------------
	# Link cards (Card Break + child Links)
	# ------------------------------------------------------------------
	links = [
		# Attendance card
		{"type": "Card Break", "label": "Attendance", "link_count": 2,
		 "hidden": 0, "is_query_report": 0, "onboard": 0},
		{"type": "Link", "label": "Attendance Request",
		 "link_to": "Attendance Request", "link_type": "DocType",
		 "hidden": 0, "is_query_report": 0, "onboard": 0},
		{"type": "Link", "label": "Employee Checkin",
		 "link_to": "Employee Checkin", "link_type": "DocType",
		 "hidden": 0, "is_query_report": 0, "onboard": 0},

		# Shift card
		{"type": "Card Break", "label": "Shift", "link_count": 2,
		 "hidden": 0, "is_query_report": 0, "onboard": 0},
		{"type": "Link", "label": "Shift Assignment",
		 "link_to": "Shift Assignment", "link_type": "DocType",
		 "hidden": 0, "is_query_report": 0, "onboard": 0},
		{"type": "Link", "label": "Shift Request",
		 "link_to": "Shift Request", "link_type": "DocType",
		 "hidden": 0, "is_query_report": 0, "onboard": 0},

		# Leave card
		{"type": "Card Break", "label": "Leave", "link_count": 1,
		 "hidden": 0, "is_query_report": 0, "onboard": 0},
		{"type": "Link", "label": "Leave Application",
		 "link_to": "Leave Application", "link_type": "DocType",
		 "hidden": 0, "is_query_report": 0, "onboard": 0},
	]
	for i, l in enumerate(links, start=1):
		ws.append("links", {**l, "idx": i})

	# ------------------------------------------------------------------
	# Content blocks (page layout)
	# ------------------------------------------------------------------
	content_blocks = [
		# 1. Intro header (replaces duplicate title)
		{
			"id": "emp-intro",
			"type": "header",
			"data": {
				"text": '<span class="h4"><b>Welcome to your HR dashboard</b></span>',
				"col": 12,
			},
		},
		# 2. Shortcut row — 5 tiles (col=2.4 × 5 = 12)
		{"id": "emp-sc-1", "type": "shortcut",
		 "data": {"shortcut_name": "Attendance Request", "col": 2.4}},
		{"id": "emp-sc-2", "type": "shortcut",
		 "data": {"shortcut_name": "Employee Checkin", "col": 2.4}},
		{"id": "emp-sc-3", "type": "shortcut",
		 "data": {"shortcut_name": "Shift Assignment", "col": 2.4}},
		{"id": "emp-sc-4", "type": "shortcut",
		 "data": {"shortcut_name": "Shift Request", "col": 2.4}},
		{"id": "emp-sc-5", "type": "shortcut",
		 "data": {"shortcut_name": "Leave Application", "col": 2.4}},
		# 3. Spacer
		{"id": "emp-sp-1", "type": "spacer", "data": {"col": 12}},
		# 4. Quick Access section header
		{
			"id": "emp-qa",
			"type": "header",
			"data": {
				"text": '<span class="h5"><b>Quick Access</b></span>',
				"col": 12,
			},
		},
		# 5. Three link cards (col=4 × 3 = 12)
		{"id": "emp-card-1", "type": "card",
		 "data": {"card_name": "Attendance", "col": 4}},
		{"id": "emp-card-2", "type": "card",
		 "data": {"card_name": "Shift", "col": 4}},
		{"id": "emp-card-3", "type": "card",
		 "data": {"card_name": "Leave", "col": 4}},
	]
	ws.content = json.dumps(content_blocks)
	ws.charts = []
	ws.custom_blocks = []

	ws.insert(ignore_permissions=True)
	frappe.db.commit()
	print(f"✓ Workspace recreated: {ws_name}")
	print(f"  shortcuts: {len(shortcuts)}")
	print(f"  link cards: 3 (Attendance, Shift, Leave)")
	print(f"  content blocks: {len(content_blocks)}")


if __name__ == "__main__":
	main()