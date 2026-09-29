frappe.ui.form.on("Sales Order", {
    refresh(frm) {
        if (frm.doc.docstatus !== 1) {
            return;
        }

        frm.add_custom_button(__("Revise Quantity"), () => {
            const item_options = (frm.doc.items || []).map(row => ({
                label: `${row.idx}. ${row.item_code} — Current Qty: ${row.qty}`,
                value: row.name
            }));

            if (!item_options.length) {
                frappe.msgprint(__("No Sales Order items found."));
                return;
            }

            const dialog = new frappe.ui.Dialog({
                title: __("Revise Sales Order Quantity"),
                fields: [
                    {
                        fieldname: "item_row",
                        fieldtype: "Select",
                        label: __("Item"),
                        options: item_options,
                        reqd: 1,
                        onchange() {
                            const row = (frm.doc.items || []).find(
                                d => d.name === dialog.get_value("item_row")
                            );

                            if (row) {
                                dialog.set_value("current_qty", row.qty);
                                dialog.set_value("new_qty", row.qty);
                            }
                        }
                    },
                    {
                        fieldname: "current_qty",
                        fieldtype: "Float",
                        label: __("Current Qty"),
                        read_only: 1
                    },
                    {
                        fieldname: "new_qty",
                        fieldtype: "Float",
                        label: __("New Qty"),
                        reqd: 1
                    },
                    {
                        fieldname: "revised_po_reference",
                        fieldtype: "Data",
                        label: __("Revised PO / Reference")
                    },
                    {
                        fieldname: "reason",
                        fieldtype: "Small Text",
                        label: __("Reason for Revision"),
                        reqd: 1
                    }
                ],
                primary_action_label: __("Update Quantity"),
                primary_action(values) {
                    const row = (frm.doc.items || []).find(
                        d => d.name === values.item_row
                    );

                    if (!row) {
                        frappe.msgprint(__("Please select an item."));
                        return;
                    }

                    if (flt(values.new_qty) <= flt(row.qty)) {
                        frappe.msgprint(
                            __("New Qty must be greater than Current Qty.")
                        );
                        return;
                    }

                    dialog.disable_primary_action();

                    frappe.call({
                        method: "project_custom.sales_order_revision.revise_sales_order_quantity",
                        args: {
                            sales_order: frm.doc.name,
                            item_row: values.item_row,
                            new_qty: values.new_qty,
                            revised_po_reference: values.revised_po_reference,
                            reason: values.reason
                        },
                        freeze: true,
                        freeze_message: __("Updating Sales Order quantity..."),
                        callback(r) {
                            if (!r.exc) {
                                dialog.hide();

                                frappe.show_alert({
                                    message: __("Sales Order quantity revised successfully."),
                                    indicator: "green"
                                });

                                frm.reload_doc();
                            }
                        },
                        always() {
                            dialog.enable_primary_action();
                        }
                    });
                }
            });

            dialog.show();

            if (frm.doc.items && frm.doc.items.length) {
                dialog.set_value("item_row", frm.doc.items[0].name);
                dialog.set_value("current_qty", frm.doc.items[0].qty);
                dialog.set_value("new_qty", frm.doc.items[0].qty);
            }
        });
    }
});
