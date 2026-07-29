import frappe
from frappe.model.document import Document
from frappe.utils import flt, getdate, now_datetime, nowdate

from project_custom.nave_task_recurrence import (
	initial_next_creation_date,
	normalize_support_required,
	validate_recurrence_config,
)
from project_custom.nave_task_utils import compute_is_overdue


class NAVETask(Document):
	def before_insert(self):
		if not self.assigned_by:
			self.assigned_by = frappe.session.user
		self.set_employee_details()
		self.ensure_recurrence_defaults()

	def validate(self):
		self.validate_dates()
		self.validate_progress()
		self.set_employee_details()
		self.set_completion_details()
		self.set_overdue_status()
		self.validate_recurrence()
		self.normalize_support_required_value()

	def ensure_recurrence_defaults(self):
		if self.is_recurring is None:
			self.is_recurring = 0
		if not self.is_recurring:
			return
		if self.recurrence_active is None:
			self.recurrence_active = 1
		if self.recurrence_due_after_days is None:
			self.recurrence_due_after_days = 0

	def normalize_support_required_value(self):
		# Keep Small Text storage; normalize Check-like values safely.
		self.support_required = normalize_support_required(self.support_required)

	def validate_recurrence(self):
		# Generated instances must never act as templates.
		if self.generated_from:
			self.is_recurring = 0
			self.recurrence_active = 0

		errors = validate_recurrence_config(self.as_dict())
		if errors:
			frappe.throw(errors[0])

		if self.is_recurring:
			if not self.next_creation_date:
				self.next_creation_date = initial_next_creation_date(
					self.as_dict(),
					getdate(nowdate()),
				)
			if self.recurrence_active is None:
				self.recurrence_active = 1
		else:
			# Leave historical recurrence metadata intact on disabled templates.
			pass

	def set_employee_details(self):
		if not self.assigned_to:
			return

		employee = frappe.db.get_value(
			"Employee",
			{
				"user_id": self.assigned_to,
				"status": "Active",
			},
			["name", "department", "company"],
			as_dict=True,
		)

		if not employee:
			return

		self.assigned_employee = employee.name

		if not self.department:
			self.department = employee.department

		if not self.company:
			self.company = employee.company

	def validate_dates(self):
		if (
			self.start_date
			and self.due_date
			and getdate(self.due_date) < getdate(self.start_date)
		):
			frappe.throw("Due Date cannot be earlier than Start Date.")

	def validate_progress(self):
		progress = flt(self.progress)

		if progress < 0 or progress > 100:
			frappe.throw("Progress must be between 0 and 100.")

		if self.status == "Completed":
			self.progress = 100

		if self.status == "Open" and progress > 0:
			self.status = "Working"

	def set_completion_details(self):
		if self.status == "Completed":
			if not self.completed_on:
				self.completed_on = now_datetime()
		elif self.status not in ("Closed",):
			self.completed_on = None

	def set_overdue_status(self):
		self.is_overdue = compute_is_overdue(
			self.due_date,
			self.status,
			nowdate(),
		)

	def after_insert(self):
		self.create_assignment_todo()

	def create_assignment_todo(self):
		if not self.assigned_to:
			return

		existing_todo = frappe.db.exists(
			"ToDo",
			{
				"reference_type": self.doctype,
				"reference_name": self.name,
				"allocated_to": self.assigned_to,
				"status": "Open",
			},
		)

		if existing_todo:
			return

		todo = frappe.get_doc(
			{
				"doctype": "ToDo",
				"allocated_to": self.assigned_to,
				"assigned_by": self.assigned_by,
				"description": self.subject,
				"reference_type": self.doctype,
				"reference_name": self.name,
				"date": self.due_date,
				"priority": self.priority,
				"status": "Open",
			}
		)
		todo.insert(ignore_permissions=True)
