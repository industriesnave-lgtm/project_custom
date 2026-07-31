import frappe
from frappe.model.document import Document
from frappe.utils import flt, now_datetime

from project_custom.nave_task_utils import (
	CONVERSATION_UPDATE_TYPES,
	INTERNAL_NOTE_TYPE,
	PRIVILEGED_SYSTEM_UPDATE_TYPES,
	can_access_internal_notes,
	user_can_access_task,
	user_can_manage_task,
	user_can_submit_progress_update,
)
from project_custom.permissions.nave_task import (
	_employee_department,
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

		self.validate_update_type_permission()

	def validate(self):
		self.validate_progress()
		self.validate_pending_reason()
		self.prevent_existing_update_edit()
		if self.is_new():
			self.validate_update_type_permission()

	def validate_update_type_permission(self):
		"""
		Restrict privileged / role-gated update types on direct inserts.

		Trusted server paths (history helpers, hooks, scheduler) call
		insert(ignore_permissions=True) and are allowed to write system types.
		"""
		update_type = self.update_type or "Progress Update"

		if getattr(self.flags, "ignore_permissions", False) or getattr(
			self.flags, "allow_privileged_nave_update_type", False
		):
			return

		if update_type in PRIVILEGED_SYSTEM_UPDATE_TYPES:
			frappe.throw(
				f"Update type '{update_type}' can only be created by the system.",
				frappe.PermissionError,
			)

		if update_type not in CONVERSATION_UPDATE_TYPES:
			frappe.throw(f"Invalid update type: {update_type}.", frappe.ValidationError)

		user = frappe.session.user
		is_admin = _is_admin(user)
		is_director = _is_director(user)
		is_manager = _is_manager(user)

		if update_type == INTERNAL_NOTE_TYPE:
			if not can_access_internal_notes(
				is_admin=is_admin,
				is_director=is_director,
				is_manager=is_manager,
			):
				frappe.throw(
					"Only NAVE Task Directors, Managers, and System Managers can create Internal Notes.",
					frappe.PermissionError,
				)
			return

		if update_type == "Manager Instruction" and not (
			is_admin or is_director or is_manager
		):
			frappe.throw(
				"Only managers, directors, and admins can post Manager Instructions.",
				frappe.PermissionError,
			)

		if not self.task:
			frappe.throw("Task is required.", frappe.ValidationError)

		task = frappe.db.get_value(
			"NAVE Task",
			self.task,
			["assigned_to", "owner", "assigned_by", "department"],
			as_dict=True,
		)
		if not task:
			frappe.throw("Task not found.", frappe.ValidationError)

		user_department = _employee_department(user)

		if not user_can_access_task(
			user=user,
			assigned_to=task.assigned_to,
			owner=task.owner,
			assigned_by=task.assigned_by,
			department=task.department,
			is_admin=is_admin,
			is_director=is_director,
			is_manager=is_manager,
			user_department=user_department,
		):
			frappe.throw(
				"You are not permitted to access this task.",
				frappe.PermissionError,
			)

		if update_type == "Progress Update" and not user_can_submit_progress_update(
			user=user,
			assigned_to=task.assigned_to,
			is_admin=is_admin,
			is_director=is_director,
			is_manager=is_manager,
			department=task.department,
			user_department=user_department,
		):
			frappe.throw(
				"Only the assigned employee or an authorized manager can submit progress updates.",
				frappe.PermissionError,
			)

		if update_type == "Completion Update":
			can_progress = user_can_submit_progress_update(
				user=user,
				assigned_to=task.assigned_to,
				is_admin=is_admin,
				is_director=is_director,
				is_manager=is_manager,
				department=task.department,
				user_department=user_department,
			)
			can_manage = user_can_manage_task(
				user=user,
				owner=task.owner,
				assigned_by=task.assigned_by,
				department=task.department,
				is_admin=is_admin,
				is_director=is_director,
				is_manager=is_manager,
				user_department=user_department,
			)
			if not can_progress and not can_manage:
				frappe.throw(
					"You are not permitted to post a Completion Update on this task.",
					frappe.PermissionError,
				)

	# Backwards-compatible alias used by older tests / call sites.
	def validate_internal_note_permission(self):
		self.validate_update_type_permission()

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
