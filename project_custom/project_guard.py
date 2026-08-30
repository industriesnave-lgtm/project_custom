import frappe


ALLOWED_PROJECT_CLOSERS = {
    "Administrator",
    "erp@naveindustries.com",
}


def validate_project_status(doc, method=None):
    if doc.is_new():
        return

    old_status = frappe.db.get_value("Project", doc.name, "status")

    if old_status == doc.status:
        return

    if doc.status not in {"Completed", "Cancelled"}:
        return

    if frappe.session.user in ALLOWED_PROJECT_CLOSERS:
        return

    frappe.throw(
        "Only Administrator or erp@naveindustries.com can close or cancel a Project.",
        frappe.PermissionError,
    )


def prevent_unauthorized_project_delete(doc, method=None):
    if frappe.session.user in ALLOWED_PROJECT_CLOSERS:
        return

    frappe.throw(
        "Only Administrator or erp@naveindustries.com can delete a Project.",
        frappe.PermissionError,
    )
