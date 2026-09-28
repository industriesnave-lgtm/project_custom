frappe.ui.form.on("Quotation", {
    refresh(frm) {
        if (frm.doc.docstatus !== 0) {
            return;
        }

        frm.add_custom_button(
            __("New / Unregistered Customer"),
            function () {
                open_new_customer_dialog(frm);
            },
            __("Customer")
        );
    }
});

function open_new_customer_dialog(frm) {
    const dialog = new frappe.ui.Dialog({
        title: __("New / Unregistered Customer"),

        fields: [
            {
                fieldname: "customer_name",
                fieldtype: "Data",
                label: __("Customer Name"),
                reqd: 1
            },
            {
                fieldname: "contact_person",
                fieldtype: "Data",
                label: __("Contact Person")
            },
            {
                fieldname: "mobile_no",
                fieldtype: "Data",
                label: __("Mobile No")
            },
            {
                fieldname: "email_id",
                fieldtype: "Data",
                label: __("Email")
            },
            {
                fieldname: "gstin",
                fieldtype: "Data",
                label: __("GSTIN")
            }
        ],

        primary_action_label: __("Use in Quotation"),

        primary_action(values) {
            frappe.call({
                method: "project_custom.quotation.create_prospect_for_quotation",

                args: {
                    customer_name: values.customer_name,
                    contact_person: values.contact_person || "",
                    mobile_no: values.mobile_no || "",
                    email_id: values.email_id || "",
                    gstin: values.gstin || ""
                },

                freeze: true,
                freeze_message: __("Preparing customer..."),

                callback(r) {
                    if (!r.message || !r.message.prospect) {
                        return;
                    }

                    frm.set_value("quotation_to", "Prospect")
                        .then(function () {
                            return frm.set_value(
                                "party_name",
                                r.message.prospect
                            );
                        })
                        .then(function () {
                            dialog.hide();

                            frappe.show_alert({
                                message: __("New party added to quotation"),
                                indicator: "green"
                            });
                        });
                }
            });
        }
    });

    dialog.show();
}
