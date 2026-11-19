// Employee Checkin - block web/manual check-ins for restricted branches.
//
// When a user (whose employee's Branch has
// `custom_disable_web_checkin == 1`) tries to:
//   1. Click "Add Employee Checkin" from the list view
//   2. Navigate to Form/Employee Checkin/new
// we show a one-time frappe.msgprint warning and redirect them back to
// the Employee Checkin list view. The New form is never allowed to render.
//
// Biometric check-ins (custom_source = "Biometric") bypass this block.
// Users can still VIEW existing check-ins (list view + open existing
// documents) — only the create flow is blocked.

frappe.provide("artem_hrms.employee_checkin");

(function () {
    const RESTRICT_MSG = __(
        "Your branch does not allow web check-ins. " +
        "Please use the biometric device to mark attendance."
    );

    const cache = { user: null, in_flight: null };

    function check_user_restricted() {
        if (cache.user !== null) return Promise.resolve(cache.user);
        if (cache.in_flight) return cache.in_flight;
        cache.in_flight = frappe
            .xcall(
                "artem_hrms.doc_events.employee_checkin.is_branch_web_checkin_restricted_for_user",
                { user: frappe.session.user }
            )
            .then((v) => {
                cache.user = !!v;
                cache.in_flight = null;
                return cache.user;
            })
            .catch(() => {
                cache.in_flight = null;
                return false;
            });
        return cache.in_flight;
    }

    function show_msg_and_redirect_to_list() {
        // Show the message exactly once per attempt so users aren't spammed.
        if (show_msg_and_redirect_to_list._shown) {
            frappe.set_route("List", "Employee Checkin");
            return;
        }
        show_msg_and_redirect_to_list._shown = true;

        frappe.msgprint({
            title: __("Web Check-In Disabled"),
            indicator: "red",
            message: RESTRICT_MSG,
        });

        frappe.set_route("List", "Employee Checkin");

        // Reset the flag so a future click can show it again.
        setTimeout(() => {
            show_msg_and_redirect_to_list._shown = false;
        }, 1500);
    }

    function is_new_checkin_route() {
        const r = frappe.get_route();
        return (
            r[0] === "Form" &&
            r[1] === "Employee Checkin" &&
            (r[2] === "new" || r[2] === undefined)
        );
    }

    // ------------------------------------------------------------------
    // Form hooks (Employee Checkin) — ONLY block the NEW (create) flow.
    // Opening an existing record is allowed so users can inspect past logs.
    // ------------------------------------------------------------------
    frappe.ui.form.on("Employee Checkin", {
        onload(frm) {
            if (!frm.is_new()) return;
            check_user_restricted().then((restricted) => {
                if (restricted) show_msg_and_redirect_to_list();
            });
        },
        refresh(frm) {
            if (!frm.is_new()) return;
            check_user_restricted().then((restricted) => {
                if (restricted) show_msg_and_redirect_to_list();
            });
        },
    });

    // ------------------------------------------------------------------
    // List view: disable "Add Employee Checkin" + intercept the click.
    // ------------------------------------------------------------------
    frappe.listview_settings["Employee Checkin"] = {
        onload(listview) {
            check_user_restricted().then((restricted) => {
                if (!restricted) return;

                // Replace the primary "Add Employee Checkin" button.
                listview.page.clear_primary_action();
                listview.page.set_primary_action(
                    __("Add Employee Checkin (disabled)"),
                    () => show_msg_and_redirect_to_list()
                );

                // Visually disable the in-list "+ Add" buttons.
                listview.$page
                    .find(".btn-primary.list-add, .btn-new-doc, .list-add-btn")
                    .attr("disabled", "disabled")
                    .css({ "pointer-events": "none", opacity: 0.5 });
            });
        },
    };

    // ------------------------------------------------------------------
    // Route interceptor — only catch the NEW doc route (Form/.../new).
    // ------------------------------------------------------------------
    const _orig_set_route = frappe.set_route;
    frappe.set_route = function (...args) {
        const is_new_checkin =
            args[0] === "Form" &&
            args[1] === "Employee Checkin" &&
            (args[2] === "new" || args[2] === undefined);

        if (is_new_checkin) {
            // Kick off the check; if the user is restricted, push them
            // to the list. We still call the original set_route first so
            // the URL/router state stays consistent, then immediately
            // redirect away.
            return check_user_restricted().then((restricted) => {
                if (restricted) {
                    show_msg_and_redirect_to_list();
                    return;
                }
                _orig_set_route.apply(frappe, args);
            });
        }
        return _orig_set_route.apply(frappe, args);
    };

    // ------------------------------------------------------------------
    // Hash-based router fallback — if the user pastes /app/employee-checkin/new
    // into the address bar or hits it via a bookmark.
    // ------------------------------------------------------------------
    $(window).on("hashchange", () => {
        if (is_new_checkin_route()) {
            check_user_restricted().then((restricted) => {
                if (restricted) show_msg_and_redirect_to_list();
            });
        }
    });
})();
