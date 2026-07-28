import frappe
from frappe.model.document import Document
from frappe.utils import flt, now_datetime


class NAVETaskUpdate(Document):
    def before_insert(self):
        self.update_by = frappe.session.user
        self.updated_on = now_datetime()

        if not self.employee:
            self.employee = frappe.db.get_value(
                "Employee",
                {"user_id": frappe.session.user},
                "name",
            )

    def validate(self):
        self.validate_progress()
        self.validate_pending_reason()
        self.prevent_existing_update_edit()

    def validate_progress(self):
        progress = flt(self.progress)

        if progress < 0 or progress > 100:
            frappe.throw("Progress must be between 0 and 100.")

        if self.status == "Completed":
            self.progress = 100

    def validate_pending_reason(self):
        if self.status == "Pending" and not self.pending_reason:
            frappe.throw("Pending Reason is required when status is Pending.")

    def prevent_existing_update_edit(self):
        if self.is_new():
            return

        old_doc = self.get_doc_before_save()
        if not old_doc:
            return

        roles = frappe.get_roles(frappe.session.user)
        is_admin = (
            frappe.session.user == "Administrator"
            or "System Manager" in roles
        )

        if not is_admin:
            frappe.throw(
                "Submitted progress updates cannot be edited.",
                frappe.PermissionError,
            )

    def on_trash(self):
        roles = frappe.get_roles(frappe.session.user)
        is_admin = (
            frappe.session.user == "Administrator"
            or "System Manager" in roles
        )

        if not is_admin:
            frappe.throw(
                "Only System Manager can delete a task update.",
                frappe.PermissionError,
            )

