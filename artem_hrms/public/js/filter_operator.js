(() => {
	if (!frappe.ui.Filter) {
		console.error("frappe.ui.Filter is not available");
		return;
	}

	// Prevent patching multiple times
	if (frappe.ui.Filter.prototype._artem_operator_patch) {
		return;
	}

	frappe.ui.Filter.prototype._artem_operator_patch = true;

	const original_hide_invalid_conditions =
		frappe.ui.Filter.prototype.hide_invalid_conditions;

	frappe.ui.Filter.prototype.hide_invalid_conditions = function (
		fieldtype,
		original_type
	) {
		// Let Frappe execute its normal logic first
		original_hide_invalid_conditions.call(
			this,
			fieldtype,
			original_type
		);

		// -----------------------------------------
		// Get DocType
		// -----------------------------------------

		const doctype =
			this.parent_doctype ||
			this._parent_doctype;

		if (doctype !== "Employee Checkin") {
			return;
		}

		// -----------------------------------------
		// Get selected field
		// -----------------------------------------

		const fieldname =
			this.fieldselect?.selected_fieldname;

		console.log(
			"[ARTEM Filter]",
			"doctype:",
			doctype,
			"field:",
			fieldname
		);

		// -----------------------------------------
		// Allowed operators
		// -----------------------------------------

		const operator_config = {
			employee: ["=", "!="],
			employee_name: ["=", "!="],
			custom_branch: ["=", "!="],
		};

		const allowed_operators =
			operator_config[fieldname];

		// No restriction for other fields
		if (!allowed_operators) {
			return;
		}

		// -----------------------------------------
		// Hide unwanted operators
		// -----------------------------------------

		const $condition =
			this.filter_edit_area.find(".condition");

		$condition.find("option").each(function () {
			const operator = this.value;

			$(this).toggle(
				allowed_operators.includes(operator)
			);
		});

		// -----------------------------------------
		// Make sure selected operator is valid
		// -----------------------------------------

		const current_operator =
			$condition.val();

		if (!allowed_operators.includes(current_operator)) {
			$condition.val("=");
			$condition.trigger("change");
		}
	};
})();