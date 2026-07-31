"""Batch 3 NAVE Tasks status workflow and completion consistency tests."""

from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

WORKSPACE = Path(__file__).resolve().parents[2]
if str(WORKSPACE) not in sys.path:
	sys.path.insert(0, str(WORKSPACE))


def _install_fake_frappe():
	if "frappe" in sys.modules and hasattr(sys.modules["frappe"], "_nave_tasks_stub"):
		return sys.modules["frappe"]

	frappe = types.ModuleType("frappe")
	frappe._nave_tasks_stub = True
	frappe.session = types.SimpleNamespace(user="Guest")
	frappe.PermissionError = type("PermissionError", (Exception,), {})
	frappe.ValidationError = type("ValidationError", (Exception,), {})

	def throw(msg, exc=None):
		raise (exc or Exception)(msg)

	frappe.throw = throw
	frappe.get_roles = lambda user=None: []
	frappe.db = types.SimpleNamespace(
		escape=lambda value: f"'{value}'",
		get_value=MagicMock(return_value=None),
		exists=MagicMock(return_value=True),
		set_value=MagicMock(),
		count=MagicMock(return_value=0),
		sql=MagicMock(),
		commit=MagicMock(),
		has_column=MagicMock(return_value=True),
	)
	frappe.get_doc = MagicMock()
	frappe.get_list = MagicMock(return_value=[])
	frappe.get_all = MagicMock(return_value=[])
	frappe.whitelist = lambda *args, **kwargs: (lambda fn: fn)
	frappe.flags = types.SimpleNamespace(in_migrate=False, in_install=False, in_patch=False)

	utils = types.ModuleType("frappe.utils")
	utils.cint = lambda v: int(float(v or 0))
	utils.flt = lambda v: float(v or 0)
	utils.nowdate = lambda: "2026-07-29"
	utils.now_datetime = lambda: "2026-07-29 12:00:00"
	utils.add_days = lambda d, n: d
	utils.getdate = lambda d: d
	frappe.utils = utils

	model = types.ModuleType("frappe.model")
	document = types.ModuleType("frappe.model.document")

	class Document:
		pass

	document.Document = Document
	sys.modules["frappe"] = frappe
	sys.modules["frappe.utils"] = utils
	sys.modules["frappe.model"] = model
	sys.modules["frappe.model.document"] = document
	return frappe


_install_fake_frappe()

from project_custom.nave_task_utils import (  # noqa: E402
	build_completion_field_updates,
	build_reopen_field_updates,
	get_allowed_next_statuses,
	is_status_transition_allowed,
	validate_status_transition,
)


class TestStatusTransitionMatrix(unittest.TestCase):
	ALLOWED = [
		("Open", "Working", False),
		("Working", "Pending", False),
		("Working", "Completed", False),
		("Pending", "Working", False),
		("Pending", "Completed", False),
		("Completed", "Closed", False),
		("Completed", "Working", True),
		("Closed", "Working", True),
	]
	INVALID = [
		("Open", "Pending"),
		("Open", "Completed"),
		("Working", "Open"),
		("Pending", "Open"),
		("Completed", "Pending"),
		("Closed", "Open"),
		("Closed", "Pending"),
		("Closed", "Completed"),
		("Open", "Closed"),
		("Working", "Closed"),
		("Pending", "Closed"),
	]

	def test_every_allowed_transition(self):
		for old, new, manager_only in self.ALLOWED:
			self.assertTrue(
				is_status_transition_allowed(
					old,
					new,
					is_manager_level=manager_only or True,
				),
				msg=f"{old} -> {new}",
			)
			if manager_only:
				self.assertFalse(
					is_status_transition_allowed(old, new, is_manager_level=False),
					msg=f"employee blocked {old} -> {new}",
				)

	def test_every_invalid_transition(self):
		for old, new in self.INVALID:
			self.assertFalse(
				is_status_transition_allowed(old, new, is_manager_level=True),
				msg=f"should block {old} -> {new}",
			)

	def test_same_status_allowed(self):
		for status in ("Open", "Working", "Pending", "Completed", "Closed"):
			self.assertTrue(
				is_status_transition_allowed(status, status, is_manager_level=False)
			)

	def test_validate_raises_on_invalid(self):
		with self.assertRaises(ValueError):
			validate_status_transition("Open", "Completed", is_manager_level=True)

	def test_allowed_next_statuses_employee_completed(self):
		self.assertEqual(
			get_allowed_next_statuses("Completed", is_manager_level=False),
			["Completed"],
		)

	def test_allowed_next_statuses_manager_completed(self):
		self.assertEqual(
			get_allowed_next_statuses(
				"Completed",
				is_manager_level=True,
				can_close=True,
			),
			["Completed", "Working", "Closed"],
		)


class TestCompletionHelpers(unittest.TestCase):
	def test_build_completion_sets_fields(self):
		updates = build_completion_field_updates(
			existing_completed_on=None,
			remarks="Done",
			attachment="/files/a.pdf",
			now="2026-07-29 12:00:00",
		)
		self.assertEqual(updates["status"], "Completed")
		self.assertEqual(updates["progress"], 100)
		self.assertEqual(updates["completed_on"], "2026-07-29 12:00:00")
		self.assertEqual(updates["completion_remarks"], "Done")
		self.assertEqual(updates["completion_attachment"], "/files/a.pdf")

	def test_build_completion_keeps_existing_completed_on(self):
		updates = build_completion_field_updates(
			existing_completed_on="2026-07-01 09:00:00",
			remarks="note",
			now="2026-07-29 12:00:00",
		)
		self.assertNotIn("completed_on", updates)

	def test_reopen_clears_completed_on_only(self):
		updates = build_reopen_field_updates()
		self.assertEqual(updates["status"], "Working")
		self.assertIsNone(updates["completed_on"])
		self.assertNotIn("completion_remarks", updates)
		self.assertNotIn("completion_attachment", updates)


class TestWorkflowApi(unittest.TestCase):
	def setUp(self):
		self.frappe = _install_fake_frappe()
		self.frappe.session.user = "emp@example.com"
		self.frappe.get_roles = lambda user=None: ["Employee"]
		self.frappe.db.get_value = MagicMock(return_value=None)
		import importlib

		import project_custom.api.nave_task as api

		importlib.reload(api)
		self.api = api

	def _task(self, **kwargs):
		defaults = {
			"name": "NT-2026-00001",
			"assigned_to": "emp@example.com",
			"owner": "creator@example.com",
			"assigned_by": "creator@example.com",
			"department": "Sales",
			"status": "Working",
			"progress": 10,
			"due_date": "2026-07-20",
			"support_required": "",
			"subject": "Test",
			"description": "Desc",
			"completed_on": None,
			"completion_remarks": "Earlier done",
			"completion_attachment": "/files/old.pdf",
			"db_set": MagicMock(),
			"reload": MagicMock(),
			"create_assignment_todo": MagicMock(),
			"sync_assignment_todos": MagicMock(),
			"flags": types.SimpleNamespace(skip_field_change_log=False),
			"as_dict": MagicMock(return_value={}),
			"get": MagicMock(return_value=None),
		}
		defaults.update(kwargs)
		return types.SimpleNamespace(**defaults)

	def test_employee_cannot_reopen_completed(self):
		self.frappe.session.user = "emp@example.com"
		self.frappe.get_roles = lambda user=None: ["Employee"]
		task = self._task(status="Completed", progress=100)

		with patch.object(self.api, "get_task_for_user", return_value=task):
			with self.assertRaises(self.frappe.ValidationError):
				self.api.submit_update(
					"NT-2026-00001",
					"Working",
					20,
					"Reopening",
				)

	def test_employee_cannot_reopen_closed(self):
		self.frappe.session.user = "emp@example.com"
		self.frappe.get_roles = lambda user=None: ["Employee"]
		task = self._task(status="Closed")

		with patch.object(self.api, "get_task_for_user", return_value=task):
			with self.assertRaises(self.frappe.ValidationError):
				self.api.submit_update(
					"NT-2026-00001",
					"Working",
					20,
					"Reopening",
				)

	def test_manager_can_reopen_completed(self):
		self.frappe.session.user = "mgr@example.com"
		self.frappe.get_roles = lambda user=None: ["NAVE Task Manager"]
		task = self._task(status="Completed", progress=100, completed_on="2026-07-01 10:00:00")
		history = types.SimpleNamespace(name="NTU-1")

		with (
			patch.object(self.api, "get_task_for_user", return_value=task),
			patch.object(self.api, "get_user_department", return_value="Sales"),
			patch.object(self.api, "get_employee", return_value=None),
			patch.object(self.api, "_create_history_entry", return_value=history) as create,
		):
			result = self.api.submit_update(
				"NT-2026-00001",
				"Working",
				40,
				"Reopened for rework",
			)

		self.assertTrue(result["ok"])
		self.assertEqual(result["status"], "Working")
		db_fields = [c.args[0] for c in task.db_set.call_args_list]
		self.assertIn("completed_on", db_fields)
		# remarks/attachment preserved (not cleared via db_set)
		self.assertNotIn("completion_remarks", db_fields)
		self.assertNotIn("completion_attachment", db_fields)
		types_created = [c.kwargs.get("update_type") for c in create.call_args_list]
		self.assertIn("Status Change", types_created)

	def test_manager_can_reopen_closed(self):
		self.frappe.session.user = "mgr@example.com"
		self.frappe.get_roles = lambda user=None: ["NAVE Task Manager"]
		task = self._task(status="Closed", progress=100)
		history = types.SimpleNamespace(name="NTU-2")

		with (
			patch.object(self.api, "get_task_for_user", return_value=task),
			patch.object(self.api, "get_user_department", return_value="Sales"),
			patch.object(self.api, "get_employee", return_value=None),
			patch.object(self.api, "_create_history_entry", return_value=history),
		):
			result = self.api.submit_update(
				"NT-2026-00001",
				"Working",
				10,
				"Reopened from closed",
			)
		self.assertTrue(result["ok"])
		self.assertEqual(result["status"], "Working")

	def test_close_from_completed_succeeds(self):
		self.frappe.session.user = "mgr@example.com"
		self.frappe.get_roles = lambda user=None: ["NAVE Task Manager"]
		task = self._task(status="Completed", progress=100)
		history = types.SimpleNamespace(name="NTU-3")

		with (
			patch.object(self.api, "get_task_for_user", return_value=task),
			patch.object(self.api, "get_user_department", return_value="Sales"),
			patch.object(self.api, "_create_history_entry", return_value=history),
		):
			result = self.api.close_task("NT-2026-00001", "Closing")
		self.assertEqual(result["status"], "Closed")

	def test_close_from_open_working_pending_fails(self):
		self.frappe.session.user = "mgr@example.com"
		self.frappe.get_roles = lambda user=None: ["NAVE Task Manager"]
		for status in ("Open", "Working", "Pending"):
			task = self._task(status=status)
			with patch.object(self.api, "get_task_for_user", return_value=task):
				with patch.object(self.api, "get_user_department", return_value="Sales"):
					with self.assertRaises(self.frappe.ValidationError):
						self.api.close_task("NT-2026-00001", "nope")

	def test_submit_update_completion_sets_all_fields(self):
		self.frappe.session.user = "emp@example.com"
		self.frappe.get_roles = lambda user=None: ["Employee"]
		task = self._task(status="Working", completed_on=None)
		history = types.SimpleNamespace(name="NTU-4")

		with (
			patch.object(self.api, "get_task_for_user", return_value=task),
			patch.object(self.api, "get_employee", return_value=None),
			patch.object(self.api, "_create_history_entry", return_value=history),
		):
			result = self.api.submit_update(
				"NT-2026-00001",
				"Completed",
				80,
				"Finished work",
				attachment="/files/done.pdf",
			)

		self.assertEqual(result["status"], "Completed")
		self.assertEqual(result["progress"], 100)
		calls = {c.args[0]: c.args[1] for c in task.db_set.call_args_list}
		self.assertEqual(calls.get("completed_on"), "2026-07-29 12:00:00")
		self.assertEqual(calls.get("completion_remarks"), "Finished work")
		self.assertEqual(calls.get("completion_attachment"), "/files/done.pdf")

	def test_completion_update_message_sets_all_fields(self):
		self.frappe.session.user = "emp@example.com"
		self.frappe.get_roles = lambda user=None: ["Employee"]
		task = self._task(status="Pending", completed_on=None)
		history = types.SimpleNamespace(
			name="NTU-5",
			update_by="emp@example.com",
			employee=None,
			updated_on="2026-07-29 12:00:00",
			update_type="Completion Update",
			status="Completed",
			progress=100,
			update_text="All done",
			pending_reason=None,
			support_required="",
			attachment="/files/x.png",
			creation="2026-07-29 12:00:00",
		)

		with (
			patch.object(self.api, "get_task_for_user", return_value=task),
			patch.object(self.api, "get_employee", return_value=None),
			patch.object(self.api, "_create_history_entry", return_value=history),
		):
			result = self.api.post_task_message(
				"NT-2026-00001",
				"All done",
				update_type="Completion Update",
				attachment="/files/x.png",
			)

		self.assertTrue(result["ok"])
		calls = {c.args[0]: c.args[1] for c in task.db_set.call_args_list}
		self.assertEqual(calls.get("status"), "Completed")
		self.assertEqual(calls.get("progress"), 100)
		self.assertEqual(calls.get("completed_on"), "2026-07-29 12:00:00")
		self.assertEqual(calls.get("completion_remarks"), "All done")
		self.assertEqual(calls.get("completion_attachment"), "/files/x.png")

	def test_recomplete_sets_new_completed_on(self):
		self.frappe.session.user = "mgr@example.com"
		self.frappe.get_roles = lambda user=None: ["NAVE Task Manager"]
		task = self._task(
			status="Working",
			completed_on=None,
			completion_remarks="Earlier done",
			completion_attachment="/files/old.pdf",
		)
		history = types.SimpleNamespace(name="NTU-6")

		with (
			patch.object(self.api, "get_task_for_user", return_value=task),
			patch.object(self.api, "get_user_department", return_value="Sales"),
			patch.object(self.api, "get_employee", return_value=None),
			patch.object(self.api, "_create_history_entry", return_value=history),
		):
			self.api.submit_update(
				"NT-2026-00001",
				"Completed",
				100,
				"Done again",
			)
		calls = {c.args[0]: c.args[1] for c in task.db_set.call_args_list}
		self.assertEqual(calls.get("completed_on"), "2026-07-29 12:00:00")

	def test_same_status_update_allowed(self):
		self.frappe.session.user = "emp@example.com"
		self.frappe.get_roles = lambda user=None: ["Employee"]
		task = self._task(status="Working", progress=20)
		history = types.SimpleNamespace(name="NTU-7")

		with (
			patch.object(self.api, "get_task_for_user", return_value=task),
			patch.object(self.api, "get_employee", return_value=None),
			patch.object(self.api, "_create_history_entry", return_value=history) as create,
		):
			result = self.api.submit_update(
				"NT-2026-00001",
				"Working",
				35,
				"Still working",
			)
		self.assertTrue(result["ok"])
		types_created = [c.kwargs.get("update_type") for c in create.call_args_list]
		self.assertEqual(types_created, ["Progress Update"])

	def test_open_to_completed_blocked(self):
		self.frappe.session.user = "emp@example.com"
		self.frappe.get_roles = lambda user=None: ["Employee"]
		task = self._task(status="Open")

		with patch.object(self.api, "get_task_for_user", return_value=task):
			with self.assertRaises(self.frappe.ValidationError):
				self.api.submit_update(
					"NT-2026-00001",
					"Completed",
					100,
					"Skip ahead",
				)


class TestFormCompletionPath(unittest.TestCase):
	def setUp(self):
		self.frappe = _install_fake_frappe()
		self.frappe.session.user = "emp@example.com"
		self.frappe.get_roles = lambda user=None: ["Employee"]
		import importlib

		import project_custom.project_custom.doctype.nave_task.nave_task as nave_task_mod

		importlib.reload(nave_task_mod)
		self.NAVETask = nave_task_mod.NAVETask

	def test_form_complete_sets_progress_and_completed_on(self):
		doc = self.NAVETask.__new__(self.NAVETask)
		doc.flags = types.SimpleNamespace()
		doc.is_new = lambda: False
		doc.status = "Completed"
		doc.progress = 40
		doc.completed_on = None
		doc.completion_remarks = ""
		doc.completion_attachment = None
		doc.start_date = None
		doc.due_date = "2026-08-01"
		doc.is_recurring = 0
		doc.generated_from = None
		doc.support_required = ""
		doc.assigned_to = "emp@example.com"
		doc._previous_status = lambda: "Working"
		doc._session_is_manager_level = lambda: False
		doc.set_employee_details = lambda: None
		doc.validate_recurrence = lambda: None
		doc.normalize_support_required_value = lambda: None
		doc.set_overdue_status = lambda: None
		doc.validate_dates = lambda: None

		doc.validate_progress()
		doc.validate_status_workflow("Working")
		doc.apply_completion_and_reopen_fields("Working")

		self.assertEqual(doc.status, "Completed")
		self.assertEqual(doc.progress, 100)
		self.assertEqual(doc.completed_on, "2026-07-29 12:00:00")

	def test_form_reopen_clears_completed_on_preserves_remarks(self):
		doc = self.NAVETask.__new__(self.NAVETask)
		doc.flags = types.SimpleNamespace()
		doc.is_new = lambda: False
		doc.status = "Working"
		doc.progress = 50
		doc.completed_on = "2026-07-01 10:00:00"
		doc.completion_remarks = "Was done"
		doc.completion_attachment = "/files/old.pdf"
		doc._session_is_manager_level = lambda: True

		doc.validate_status_workflow("Completed")
		doc.apply_completion_and_reopen_fields("Completed")

		self.assertEqual(doc.status, "Working")
		self.assertIsNone(doc.completed_on)
		self.assertEqual(doc.completion_remarks, "Was done")
		self.assertEqual(doc.completion_attachment, "/files/old.pdf")

	def test_form_blocks_invalid_transition(self):
		doc = self.NAVETask.__new__(self.NAVETask)
		doc.is_new = lambda: False
		doc.status = "Completed"
		doc._session_is_manager_level = lambda: False
		with self.assertRaises(Exception):
			doc.validate_status_workflow("Open")


if __name__ == "__main__":
	unittest.main()
