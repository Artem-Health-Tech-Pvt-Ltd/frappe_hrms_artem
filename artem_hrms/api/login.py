import frappe
from frappe import _


@frappe.whitelist(allow_guest=True)
def login_via_key(key: str, redirect_to: str = "/helpdesk/home"):
	"""Logs in user using a one-time key and redirects to the target location.

	Defaults to '/helpdesk/home' if redirect_to is not specified.
	Matches Frappe core's standard authentication mechanism in `frappe.www.login.login_via_key`.
	"""
	cache = frappe.cache
	user = cache.get_value(f"one_time_login_key:{key}")
	if not user:
		frappe.throw(_("Invalid or expired key"), frappe.PermissionError)

	cache.delete_value(f"one_time_login_key:{key}")
	frappe.local.login_manager.login_as(user)

	frappe.response["type"] = "redirect"
	frappe.response["location"] = redirect_to or "/helpdesk/home"


@frappe.whitelist(allow_guest=True)
def login_via_key_helpdesk(key: str):
	"""Explicit endpoint for Helpdesk login via one-time key.

	Redirects directly to '/helpdesk/home'.
	"""
	return login_via_key(key=key, redirect_to="/helpdesk/home")
