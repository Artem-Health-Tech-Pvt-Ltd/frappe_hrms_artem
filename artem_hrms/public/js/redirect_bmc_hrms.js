// Redirect /desk → /desk/bmc-hrms once per session, only after Frappe is ready.
//
// Triggers on `app_ready` / `desk_ready` (Frappe's Vue lifecycle events) so the
// sidebar has time to render before the redirect. Short delay (500ms) — long
// enough to let Frappe mount, short enough that no user click can land first.
// sessionStorage guard prevents loops and double-fires.

(function () {
	const TARGET = "/desk/bmc-hrms";
	const FLAG = "bmc_hrms_redirected";

	function maybeRedirect() {
		try {
			if (sessionStorage.getItem(FLAG)) return;
		} catch (e) {
			// sessionStorage blocked (private mode, iframe, etc.) — bail safely.
			return;
		}

		const path = window.location.pathname;
		if (path === "/desk" || path === "/desk/" || path === "/" || path === "/desk/people") {
			try {
				sessionStorage.setItem(FLAG, "1");
			} catch (e) {
				// Ignore: still attempt redirect.
			}
			window.location.replace(TARGET);
		}
	}

	// Hook into Frappe's lifecycle so the Vue sidebar has rendered before we navigate.
	$(document).on("app_ready", maybeRedirect);
	$(document).on("desk_ready", maybeRedirect);

	// Fallback for non-Vue paths (e.g. web forms): still attempt the redirect
	// after a short delay, but only if Frappe hasn't signalled readiness.
	setTimeout(function () {
		if (!window.frappe || !frappe.boot) {
			maybeRedirect();
		}
	}, 500);
})();