# hrms/api/custom_auth.py
import frappe
from frappe import _

@frappe.whitelist(allow_guest=True)
def custom_login(username):
    # Remove @bmcinternal.com from username
    username = username.replace("@bmcinternal.com", "")

    # If username still contains '@', append 'bmcinternal.com'
    # otherwise append '@bmcinternal.com'
    if "@" in username:
        username = username + "bmcinternal.com"
    else:
        username = username + "@bmcinternal.com"

    # Normalize username: replace whitespace with hyphens
    normalized_username = "-".join(username.split())

    # Authenticate the user
    user = frappe.db.get_value("User", {"name": normalized_username, "enabled": 1})
    if not user:
        frappe.throw(_("User does not exist"))

    if not frappe.db.exists("User", normalized_username):
        frappe.throw(
            _("User with id {0} does not exist").format(normalized_username),
            frappe.DoesNotExistError
        )

    key = frappe.generate_hash()
    frappe.cache.set_value(f"one_time_login_key:{key}", normalized_username, expires_in_sec=60)

    frappe.local.response['message'] = {
        "link": frappe.utils.get_url(f"/api/method/frappe.www.login.login_via_key?key={key}"),
        "full_name": user,
        "message": _("Logged in")
    }
