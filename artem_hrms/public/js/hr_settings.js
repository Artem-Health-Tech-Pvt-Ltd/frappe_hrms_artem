frappe.ui.form.on("HR Settings", {
	refresh: function (frm) {
		// 1. Sync button
		frm.add_custom_button(__("Sync Custom Attendance"), function () {
			frappe.call({
				method: "artem_hrms.tasks.get_sync_status",
				callback: function (r) {
					if (r.message) {
						let status = r.message;
						
						let d = new frappe.ui.Dialog({
							title: __("Sync Custom Attendance"),
							fields: [
								{
									label: __("Start Date"),
									fieldname: "start_date",
									fieldtype: "Date",
									default: status.default_start_date,
									reqd: 1
								},
								{
									label: __("End Date"),
									fieldname: "end_date",
									fieldtype: "Date",
									default: frappe.datetime.get_today(),
									reqd: 1
								}
							],
							primary_action_label: __("Sync"),
							primary_action(values) {
								frappe.call({
									method: "artem_hrms.tasks.trigger_historical_attendance_sync",
									args: {
										start_date: values.start_date,
										end_date: values.end_date
									},
									callback: function (res) {
										if (!res.exc) {
											frappe.show_alert({
												message: __("Historical Attendance Sync has been successfully enqueued in the background."),
												indicator: "green"
											});
										}
									}
								});
								d.hide();
							}
						});
						d.show();
					}
				}
			});
		}, __("Actions"));

		// 2. Stop button
		frm.add_custom_button(__("Stop Custom Attendance Sync"), function () {
			frappe.confirm(
				__("Are you sure you want to stop the background historical attendance sync process?"),
				function () {
					frappe.call({
						method: "artem_hrms.tasks.stop_attendance_sync",
						callback: function (r) {
							if (!r.exc) {
								frappe.show_alert({
									message: __("Stop signal has been sent to the sync job. It will stop after the current day is completed."),
									indicator: "orange"
								});
							}
						}
					});
				}
			);
		}, __("Actions"));
	}
});
