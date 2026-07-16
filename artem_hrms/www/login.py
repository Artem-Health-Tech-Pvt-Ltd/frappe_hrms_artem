# Copyright (c) 2026, Artem Hrms
# License: MIT. See LICENSE

import frappe
import frappe.utils
from frappe import _
from frappe.core.doctype.navbar_settings.navbar_settings import get_app_logo
from frappe.utils import cint
from frappe.utils.jinja import guess_is_path

no_cache = True


def get_context(context):
	if frappe.session.user != "Guest":
		frappe.local.flags.redirect_location = "/desk"
		raise frappe.Redirect

	context.no_header = True
	context["title"] = "Login"
	context["hide_login"] = True
	context["provider_logins"] = []
	context["disable_signup"] = cint(frappe.get_website_settings("disable_signup"))
	context["disable_user_pass_login"] = cint(frappe.get_system_settings("disable_user_pass_login"))
	context["logo"] = "/assets/artem_hrms/images/bmc_hr_logo.svg"
	context["app_name"] = "BMC"

	context["social_login"] = False

	if cint(frappe.db.get_value("LDAP Settings", "LDAP Settings", "enabled")):
		from frappe.integrations.doctype.ldap_settings.ldap_settings import LDAPSettings

		context["ldap_settings"] = LDAPSettings.get_ldap_client_settings()

	login_label = [_("Email")]
	if frappe.utils.cint(frappe.get_system_settings("allow_login_using_mobile_number")):
		login_label.append(_("Mobile"))
	if frappe.utils.cint(frappe.get_system_settings("allow_login_using_user_name")):
		login_label.append(_("Username"))

	context["login_label"] = f" {_('or')} ".join(login_label)
	context["login_with_email_link"] = cint(frappe.get_system_settings("login_with_email_link"))
	context["login_with_frappe_cloud_url"] = None
	context["login_name_placeholder"] = "jane@example.com"

	return context
