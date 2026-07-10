"""Filter top-right user dropdown by role.

Why this lives at import-time monkey-patching and not in `extend_bootinfo`:

`frappe.sessions.get()` calls our `extend_bootinfo` hook at line 170, but
`bootinfo["navbar_settings"]` isn't populated until line 185. Anything we do at
boot time is overwritten seconds later. So we patch the two source functions
(`get_navbar_settings` and `frappe.client_cache.get_doc`) so the filtered doc
is what reaches bootinfo in the first place.

Admin / System Manager -> full menu.
Everyone else -> only Desktop, Display, Reload.
"""

import frappe
from frappe.core.doctype.navbar_settings import navbar_settings as _ns_module


_ADMIN_ROLES = {"administrator", "system manager"}
_ALLOWED = {"desktop", "display", "reload"}


def _should_filter():
    user = frappe.session.user
    if user == "Guest":
        return False
    roles = {r.lower() for r in frappe.get_roles(user)}
    return not (roles & _ADMIN_ROLES)


def _filter_items(items):
    return [
        row for row in (items or [])
        if (row.get("item_label") or "").strip().lower() in _ALLOWED
    ]


def _apply_filter(doc):
    items = doc.get("settings_dropdown") or []
    filtered = _filter_items(items)
    if hasattr(doc, "set") and callable(getattr(doc, "set")):
        doc.set("settings_dropdown", filtered)
    else:
        doc["settings_dropdown"] = filtered


# --- Patch 1: get_navbar_settings() at the module level ---
_original_get_navbar_settings = _ns_module.get_navbar_settings


def _patched_get_navbar_settings():
    doc = _original_get_navbar_settings()
    if _should_filter():
        _apply_filter(doc)
    return doc


_ns_module.get_navbar_settings = _patched_get_navbar_settings


# --- Patch 2: frappe.client_cache.get_doc for "Navbar Settings" ---
_original_client_cache_get_doc = frappe.client_cache.get_doc


def _patched_client_cache_get_doc(doctype, *args, **kwargs):
    result = _original_client_cache_get_doc(doctype, *args, **kwargs)
    if doctype == "Navbar Settings" and _should_filter():
        _apply_filter(result)
    return result


frappe.client_cache.get_doc = _patched_client_cache_get_doc


# Kept as a no-op for backward compatibility with the extend_bootinfo hook.
def boot_session(bootinfo):
    pass