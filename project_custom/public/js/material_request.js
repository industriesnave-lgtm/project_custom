frappe.ui.form.on("Material Request", {
    refresh(frm) {
        set_approved_qty_access(frm);
    },

    workflow_state(frm) {
        set_approved_qty_access(frm);
    }
});

function set_approved_qty_access(frm) {
    const can_edit =
        frm.doc.workflow_state === "Pending PM Approval" &&
        frappe.user.has_role("NAVE Material Request Approver");

    frm.fields_dict.items.grid.update_docfield_property(
        "custom_approved_qty",
        "read_only",
        can_edit ? 0 : 1
    );

    frm.refresh_field("items");
}
