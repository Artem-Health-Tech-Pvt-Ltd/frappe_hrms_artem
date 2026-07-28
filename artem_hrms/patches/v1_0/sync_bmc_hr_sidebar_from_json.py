"""Sync the BMC HR Workspace Sidebar from the checked-in JSON file.

Runs idempotently on every migrate. Reads:
  apps/artem_hrms/artem_hrms/workspace_sidebar/bmc_hr.json

Behavior:
- If the row exists in DB: replace its items child table with the JSON contents.
- If the row is missing: insert it from the JSON.
- Always normalize header_icon to "users" (kept consistent with the fix_bmc_hr_sidebar_icons patch).
"""
import json
import os

import frappe


JSON_PATH = os.path.normpath(
    os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "..", "..", "workspace_sidebar", "bmc_hr.json",
    )
)
SIDEBAR_NAME = "BMC HR"


def _load():
    with open(JSON_PATH) as f:
        return json.load(f)


def _apply(doc, payload):
    doc.items = []
    for it in payload.get("items", []):
        row = {k: v for k, v in it.items() if k != "name"}
        doc.append("items", row)
    if payload.get("header_icon"):
        doc.header_icon = payload["header_icon"]


def execute():
    payload = _load()
    if frappe.db.exists("Workspace Sidebar", SIDEBAR_NAME):
        doc = frappe.get_doc("Workspace Sidebar", SIDEBAR_NAME)
        _apply(doc, payload)
        doc.save(ignore_permissions=True)
    else:
        doc = frappe.get_doc({"doctype": "Workspace Sidebar", "name": SIDEBAR_NAME, **payload})
        _apply(doc, payload)
        doc.insert(ignore_permissions=True)
