import frappe
from frappe import _


@frappe.whitelist(allow_guest=True)
def login_to_helpdesk(key: str = None, username: str = None, redirect_to: str = "/helpdesk/home"):
	# 1. HMIS Backend Call: Generate key and return the Helpdesk URL
	if username and not key:
		username = username.replace("@bmcinternal.com", "")
		if "@" in username:
			username = username + "bmcinternal.com"
		else:
			username = username + "@bmcinternal.com"
		normalized_username = "-".join(username.split())

		user = frappe.db.get_value("User", {"name": normalized_username, "enabled": 1})

		if not user:
			frappe.throw(_("User does not exist or is disabled"))

		key = frappe.generate_hash()
		frappe.cache.set_value(f"one_time_login_key:{key}", user, expires_in_sec=60)

		return {
			"url": frappe.utils.get_url(f"/api/method/artem_hrms.api.login.login_to_helpdesk?key={key}"),
			"full_name": user,
			"message": _("Logged in"),
		}

	# 2. Browser Visit: Authenticate user session and redirect to Helpdesk
	user = frappe.cache.get_value(f"one_time_login_key:{key}")
	if not user:
		frappe.throw(_("Invalid or expired key"), frappe.PermissionError)

	frappe.cache.delete_value(f"one_time_login_key:{key}")
	frappe.local.login_manager.login_as(user)

	frappe.response["type"] = "redirect"
	frappe.response["location"] = redirect_to
