function add_submitted_invoice_edit_button(frm) {
	const roles = frappe.user_roles || [];
	const is_super_user =
		frappe.session.user === "Administrator" ||
		roles.includes("System Manager");

	if (!is_super_user || frm.doc.docstatus !== 1) return;

	frm.add_custom_button(__("Edit Submitted Invoice"), () => {
		frappe.call({
			method: "project_custom.api.submitted_invoice_edit.get_editable_invoice_fields",
			args: { doctype: frm.doctype, name: frm.doc.name },
			callback: ({ message }) => {
				if (!message) return;

				const fields = message.fields.map((field) => ({
					fieldname: field.fieldname,
					label: field.label,
					fieldtype:
						field.fieldname === "due_date"
							? "Date"
							: field.fieldname === "remarks"
								? "Small Text"
								: "Data",
					default: field.value,
				}));

				const dialog = new frappe.ui.Dialog({
					title: __("Edit Submitted Invoice"),
					fields,
					primary_action_label: __("Save"),
					primary_action(values) {
						frappe.call({
							method: "project_custom.api.submitted_invoice_edit.update_submitted_invoice",
							args: {
								doctype: frm.doctype,
								name: frm.doc.name,
								values,
							},
							freeze: true,
							freeze_message: __("Updating invoice..."),
							callback() {
								dialog.hide();
								frm.reload_doc();
							},
						});
					},
				});

				dialog.show();
			},
		});
	}, __("Actions"));
}

frappe.ui.form.on("Sales Invoice", {
	refresh: add_submitted_invoice_edit_button,
});

frappe.ui.form.on("Purchase Invoice", {
	refresh: add_submitted_invoice_edit_button,
});
