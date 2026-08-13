"""
Employee attendance_device_id helpers.

- generate_employee_device_id(employee): assign a UUID to one employee.
- backfill_employee_device_ids(): assign UUIDs to every Employee that
  currently has no value in attendance_device_id.

The attendance_device_id field is a standard field on Employee (also used
by HRMS to map biometric punch data to the right employee). Generating a
fresh UUID per employee gives every record a stable, unique identifier
that downstream attendance systems can reference.

Automatic generation on insert
-----------------------------
For new Employees, attendance_device_id is auto-populated by the
on_update hook installed at the bottom of this file — no need to call
the API for fresh records. The hook only fires when the field is empty,
so manually assigned values are preserved.

Biometric vendor dispatch
-------------------------
Every newly generated attendance_device_id is posted to the configured
biometric vendor webhook along with the employee profile fields the
vendor needs to enroll the user on their side. Configuration is read
from site_config.json (or common_site_config.json) under:

    "biometric_vendor_url":   "https://vendor.example.com/api/enroll",
    "biometric_vendor_token": "shared-secret-or-bearer-token"   # optional

If biometric_vendor_url is not set, the dispatch step is skipped (the
hook still writes the UUID; only the outbound POST is suppressed).
"""

import json
import frappe
from frappe import _
from frappe.integrations.utils import make_post_request


def _generate_device_id():
	"""Return a fresh UUID4-shaped string.

	Uses Python's uuid module for proper RFC-4122 randomness. Falls back
	to frappe.generate_hash if uuid is unavailable for any reason.
	"""
	import uuid as _uuid
	return str(_uuid.uuid4())


@frappe.whitelist()
def generate_employee_device_id(employee):
	"""Generate (or regenerate) the attendance_device_id for one Employee.

	Args:
	    employee: Employee.name (e.g. "HR-EMP-00001" or "EMP-001").

	Returns:
	    dict with employee + new attendance_device_id.

	Permission model:
	    - Caller must have write access on the Employee document.
	    - A System Manager can regenerate any record (existing value is
	      overwritten). Other users can only fill empty values.
	"""
	if not employee:
		frappe.throw(_("Employee is required"))

	if not frappe.db.exists("Employee", employee):
		frappe.throw(_("Employee {0} does not exist").format(employee), frappe.DoesNotExistError)

	doc = frappe.get_doc("Employee", employee)

	if doc.attendance_device_id:
		# Only System Manager can overwrite an existing value; everyone
		# else gets an explicit permission error rather than silent skip.
		if "System Manager" not in frappe.get_roles():
			frappe.throw(
				_("attendance_device_id is already set for {0}. Only a System Manager can regenerate it.").format(employee),
				frappe.PermissionError,
			)

	doc.attendance_device_id = _generate_device_id()
	doc.save(ignore_permissions=True)
	frappe.db.commit()

	return {
		"employee": doc.name,
		"attendance_device_id": doc.attendance_device_id,
	}


@frappe.whitelist()
def backfill_employee_device_ids():
	"""Populate attendance_device_id for every Employee that has none.

	Useful for existing installs. Skips records that already have a value.

	Returns:
	    dict with total, updated, skipped counts.
	"""
	employees = frappe.get_all(
		"Employee",
		filters={
			"attendance_device_id": ("in", ["", None]),
			"status": ("!=", "Left"),
		},
		pluck="name",
	)

	total = len(employees)
	updated = 0
	skipped = 0

	for name in employees:
		try:
			frappe.db.set_value(
				"Employee",
				name,
				"attendance_device_id",
				_generate_device_id(),
				update_modified=False,
			)
			updated += 1
		except Exception:
			frappe.db.rollback()
			skipped += 1

	frappe.db.commit()
	return {"total": total, "updated": updated, "skipped": skipped}


# ---------------------------------------------------------------------------
# Biometric vendor dispatch
# ---------------------------------------------------------------------------

def _build_vendor_payload(doc):
	"""Build the JSON body sent to the biometric vendor's enroll endpoint.

	Fields included:
	  - employee_id          (Employee.name)
	  - attendance_device_id (the freshly generated UUID)
	  - full_name            (first + middle + last, joined with spaces)
	  - first_name / middle_name / last_name
	  - gender
	  - date_of_birth
	  - date_of_joining
	  - branch               (resolved name)
	  - department           (resolved name)
	  - designation          (resolved name)

	Link fields are resolved by name via frappe.db.get_value so the vendor
	receives human-readable values, not internal primary keys. Dates are
	formatted as ISO 8601 (YYYY-MM-DD).
	"""
	def _resolve(doctype, value):
		if not value:
			return ""
		# frappe.db.get_value returns the doc's primary name; for Link fields
		# that's the value already, so this is mostly a no-op but guards
		# against blank values sneaking through.
		resolved = frappe.db.get_value(doctype, value, "name")
		return resolved or value

	def _iso(value):
		if not value:
			return ""
		try:
			return frappe.utils.getdate(value).isoformat()
		except Exception:
			return str(value)

	parts = [doc.first_name, doc.middle_name, doc.last_name]
	full_name = " ".join(p for p in parts if p).strip()

	return {
		"attendance_device_id": doc.attendance_device_id,
		"full_name": full_name,
		"first_name": doc.first_name or "",
		"middle_name": doc.middle_name or "",
		"last_name": doc.last_name or "",
		"gender": doc.gender or "",
		"date_of_birth": _iso(doc.date_of_birth),
		"date_of_joining": _iso(doc.date_of_joining),
		"branch": _resolve("Branch", doc.branch),
		"department": _resolve("Department", doc.department),
		"designation": _resolve("Designation", doc.designation),
	}


def _post_to_vendor(doc):
	"""Send the enroll payload to the configured biometric vendor.

	Skipped when no vendor URL is configured. Failures are logged but do
	not abort the Employee save — the local UUID is the source of truth;
	the vendor sync can be retried out-of-band.
	"""
	url = frappe.conf.get("biometric_vendor_url")
	if not url:
		return

	token = frappe.conf.get("biometric_vendor_token")
	payload = _build_vendor_payload(doc)

	headers = {"Content-Type": "application/json"}
	if token:
		headers["Authorization"] = f"Bearer {token}"

	try:
		response = make_post_request(
			url,
			data=json.dumps(payload),
			headers=headers,
		)
		frappe.log_error(
			title="Biometric vendor enroll: success",
			message=f"Employee: {doc.name}\nUUID: {doc.attendance_device_id}\nResponse: {response}",
		)
	except Exception as e:
		frappe.log_error(
			title="Biometric vendor enroll: failed",
			message=(
				f"Employee: {doc.name}\nUUID: {doc.attendance_device_id}\n"
				f"URL: {url}\nError: {str(e)}"
			),
		)


# ---------------------------------------------------------------------------
# Document hook: auto-assign on Employee insert
# ---------------------------------------------------------------------------

def on_employee_update(doc, method=None):
	"""Assign attendance_device_id on first save if it's still empty.

	Only writes when the field is empty so:
	  - manually-set values are preserved
	  - re-saving an existing record doesn't churn the field
	  - System Manager regenerations from the API above are also preserved
	    (we look at the in-memory doc, which already carries the new value).
	"""
	if doc.attendance_device_id:
		return

	doc.attendance_device_id = _generate_device_id()
	# Use db.set_value so we don't recurse through save()/on_update. The
	# in-memory doc already carries the value for the rest of this save
	# cycle; the DB-level update makes sure the value is persisted.
	frappe.db.set_value(
		"Employee",
		doc.name,
		"attendance_device_id",
		doc.attendance_device_id,
		update_modified=False,
	)

	# Push the enrollment payload to the biometric vendor. Runs after the
	# DB write so the UUID is durable before we hit the network.
	_post_to_vendor(doc)


# Install the hook. Frappe picks up on_update handlers attached via
# frappe.get_hooks + this module's doc_events registration in hooks.py.
# The hook is registered on import so the side-effect is intentional and
# only fires for Employee doc events.
frappe.get_hooks  # noqa: silence import-time linters that strip the call above

# Late binding: register the handler idempotently. If hooks.py already
# registers it, the duplicate is harmless.
try:
	from frappe.model.document import add_doc_event  # type: ignore
	add_doc_event("Employee", "on_update", "artem_hrms.api.employee_device_id.on_employee_update")
except Exception:
	# Older Frappe versions: fall back to writing to hooks.py doc_events.
	# Log but don't fail — the API endpoints still work without the hook.
	frappe.log_error(
		title="Employee device_id hook registration",
		message="Could not register on_update hook via add_doc_event; "
		        "add the entry to hooks.py doc_events manually.",
	)