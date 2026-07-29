import frappe
from frappe.model.document import Document
from frappe.utils import flt, now_datetime

from project_custom.nave_task_utils import (
	CONVERSATION_UPDATE_TYPES,
	INTERNAL_NOTE_TYPE,
	can_access_internal_notes,
)
from project_custom.permissions.nave_task import (
	_is_admin,
	_is_director,
	_is_manager,
)


class NAVETaskUpdate(Document):
	def before_insert(self):
		self.update_by = frappe.session.user
		self.updated_on = now_datetime()

		if not self.update_type:
			self.update_type = "Progress Update"

		if not self.employee:
			self.employee = frappe.db.get_value(
				"Employee",
				{"user_id": frappe.session.user},
				"name",
			)

		self.validate_internal_note_permission()

	def validate(self):
		self.validate_progress()
		self.validate_pending_reason()
		self.prevent_existing_update_edit()
		if self.is_new():
			self.validate_internal_note_permission()

	def validate_internal_note_permission(self):
		if self.update_type != INTERNAL_NOTE_TYPE:
			return

		user = frappe.session.user
		if not can_access_internal_notes(
			is_admin=_is_admin(user),
			is_director=_is_director(user),
			is_manager=_is_manager(user),
		):
			frappe.throw(
				"Only NAVE Task Directors, Managers, and System Managers can create Internal Notes.",
				frappe.PermissionError,
			)

	def validate_progress(self):
		progress = flt(self.progress)

		if progress < 0 or progress > 100:
			frappe.throw("Progress must be between 0 and 100.")

		if self.status == "Completed":
			self.progress = 100

	def validate_pending_reason(self):
		if (
			self.update_type in (None, "", "Progress Update")
			and self.status == "Pending"
			and not self.pending_reason
		):
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
