"""Phase 1 NAVE Tasks tests.

These tests run without a Frappe bench by exercising pure helpers and
mocked permission/API decision logic. Full IntegrationTestCase coverage
can be added later when a bench site is available.
"""

from __future__ import annotations

import sys
import types
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch


# Ensure /workspace (app root parent) is importable as project_custom package root.
WORKSPACE = Path(__file__).resolve().parents[2]
if str(WORKSPACE) not in sys.path:
	sys.path.insert(0, str(WORKSPACE))


def _install_fake_frappe():
	"""Minimal frappe stub so project_custom modules can import."""
	if "frappe" in sys.modules and hasattr(sys.modules["frappe"], "_nave_tasks_stub"):
		return sys.modules["frappe"]

	frappe = types.ModuleType("frappe")
	frappe._nave_tasks_stub = True
	frappe.session = types.SimpleNamespace(user="Guest")
	frappe.PermissionError = type("PermissionError", (Exception,), {})
	frappe.ValidationError = type("ValidationError", (Exception,), {})
	frappe.WhitelistUnknownError = Exception

	def throw(msg, exc=None):
		exc_type = exc or Exception
		raise exc_type(msg)

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

	utils = types.ModuleType("frappe.utils")
	utils.cint = lambda v: int(float(v or 0))
	utils.flt = lambda v: float(v or 0)
	utils.nowdate = lambda: "2026-07-29"
	utils.now_datetime = lambda: "2026-07-29 12:00:00"
	utils.add_days = lambda d, n: d  # not used heavily in unit tests
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
	build_task_permission_condition,
	compute_is_overdue,
	normalize_progress,
	to_plain_text,
	user_can_access_task,
	user_can_manage_task,
	user_can_submit_progress_update,
)


class TestPlainText(unittest.TestCase):
	def test_strips_html(self):
		self.assertEqual(
			to_plain_text("<p>Hello <b>world</b></p>"),
			"Hello world",
		)

	def test_empty(self):
		self.assertEqual(to_plain_text(None), "")


class TestOverdueCalculation(unittest.TestCase):
	def test_past_due_open_is_overdue(self):
		self.assertEqual(
			compute_is_overdue("2026-07-01", "Open", "2026-07-29"),
			1,
		)

	def test_completed_not_overdue(self):
		self.assertEqual(
			compute_is_overdue("2026-07-01", "Completed", "2026-07-29"),
			0,
		)

	def test_closed_not_overdue(self):
		self.assertEqual(
			compute_is_overdue("2026-07-01", "Closed", date(2026, 7, 29)),
			0,
		)

	def test_cancelled_not_overdue(self):
		self.assertEqual(
			compute_is_overdue("2026-07-01", "Cancelled", "2026-07-29"),
			0,
		)

	def test_future_due_not_overdue(self):
		self.assertEqual(
			compute_is_overdue("2026-08-01", "Working", "2026-07-29"),
			0,
		)

	def test_preserves_status_concept(self):
		# Overdue is independent of status string for active statuses.
		self.assertEqual(compute_is_overdue("2026-07-01", "Pending", "2026-07-29"), 1)
		self.assertEqual(compute_is_overdue("2026-07-01", "Working", "2026-07-29"), 1)


class TestProgressNormalization(unittest.TestCase):
	def test_completed_forces_100(self):
		self.assertEqual(normalize_progress("Completed", 40), 100.0)

	def test_rejects_out_of_range(self):
		with self.assertRaises(ValueError):
			normalize_progress("Working", 120)


class TestPermissionLogic(unittest.TestCase):
	def test_assigned_employee_can_read(self):
		self.assertTrue(
			user_can_access_task(
				user="emp@example.com",
				assigned_to="emp@example.com",
				owner="manager@example.com",
				assigned_by="manager@example.com",
				department="Sales",
				is_admin=False,
				is_manager=False,
				user_department="Sales",
			)
		)

	def test_creator_can_read(self):
		self.assertTrue(
			user_can_access_task(
				user="creator@example.com",
				assigned_to="emp@example.com",
				owner="creator@example.com",
				assigned_by="creator@example.com",
				department="Sales",
				is_admin=False,
				is_manager=False,
				user_department="HR",
			)
		)

	def test_unrelated_employee_cannot_read(self):
		self.assertFalse(
			user_can_access_task(
				user="other@example.com",
				assigned_to="emp@example.com",
				owner="creator@example.com",
				assigned_by="creator@example.com",
				department="Sales",
				is_admin=False,
				is_manager=False,
				user_department="Purchase",
			)
		)

	def test_authorized_manager_department_access(self):
		self.assertTrue(
			user_can_access_task(
				user="mgr@example.com",
				assigned_to="emp@example.com",
				owner="creator@example.com",
				assigned_by="creator@example.com",
				department="Sales",
				is_admin=False,
				is_manager=True,
				user_department="Sales",
			)
		)

	def test_manager_other_department_denied_unless_creator_or_assignee(self):
		self.assertFalse(
			user_can_access_task(
				user="mgr@example.com",
				assigned_to="emp@example.com",
				owner="creator@example.com",
				assigned_by="creator@example.com",
				department="Sales",
				is_admin=False,
				is_manager=True,
				user_department="Accounts",
			)
		)

	def test_system_manager_access(self):
		self.assertTrue(
			user_can_access_task(
				user="admin@example.com",
				assigned_to="emp@example.com",
				owner="creator@example.com",
				assigned_by="creator@example.com",
				department="Sales",
				is_admin=True,
				is_manager=False,
				user_department=None,
			)
		)

	def test_query_condition_includes_creator(self):
		sql = build_task_permission_condition(
			"creator@example.com",
			is_admin=False,
			is_manager=False,
			department=None,
			escape=lambda v: f"'{v}'",
		)
		self.assertIn("assigned_to", sql)
		self.assertIn("owner", sql)
		self.assertIn("assigned_by", sql)

	def test_employee_can_submit_only_when_assigned(self):
		self.assertTrue(
			user_can_submit_progress_update(
				user="emp@example.com",
				assigned_to="emp@example.com",
				is_admin=False,
				is_manager=False,
				department="Sales",
				user_department="Sales",
			)
		)
		self.assertFalse(
			user_can_submit_progress_update(
				user="creator@example.com",
				assigned_to="emp@example.com",
				is_admin=False,
				is_manager=False,
				department="Sales",
				user_department="Sales",
			)
		)

	def test_reassign_close_permission_creator(self):
		self.assertTrue(
			user_can_manage_task(
				user="creator@example.com",
				owner="creator@example.com",
				assigned_by="creator@example.com",
				department="Sales",
				is_admin=False,
				is_manager=False,
				user_department="Sales",
			)
		)

	def test_reassign_close_denied_for_ordinary_assignee(self):
		self.assertFalse(
			user_can_manage_task(
				user="emp@example.com",
				owner="creator@example.com",
				assigned_by="creator@example.com",
				department="Sales",
				is_admin=False,
				is_manager=False,
				user_department="Sales",
			)
		)


class TestActionRulesWithMocks(unittest.TestCase):
	def setUp(self):
		self.frappe = _install_fake_frappe()
		# Reload API against current stub
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
			"status": "Open",
			"progress": 10,
			"due_date": "2026-07-20",
			"support_required": "",
			"subject": "Test",
			"description": "<p>Desc</p>",
			"db_set": MagicMock(),
			"reload": MagicMock(),
			"create_assignment_todo": MagicMock(),
			"as_dict": MagicMock(
				return_value={
					"name": "NT-2026-00001",
					"subject": "Test",
					"description": "<p>Desc</p>",
					"assigned_to": "emp@example.com",
					"owner": "creator@example.com",
					"assigned_by": "creator@example.com",
					"status": "Open",
					"progress": 10,
					"is_overdue": 1,
				}
			),
			"get": MagicMock(return_value=None),
		}
		defaults.update(kwargs)
		return types.SimpleNamespace(**defaults)

	def test_employee_update_creation_allowed(self):
		self.frappe.session.user = "emp@example.com"
		self.frappe.get_roles = lambda user=None: ["Employee"]
		task = self._task()
		history = types.SimpleNamespace(name="NTU-2026-00001")

		with (
			patch.object(self.api, "get_task_for_user", return_value=task),
			patch.object(self.api, "get_employee", return_value=None),
			patch.object(self.api, "_create_history_entry", return_value=history) as create,
		):
			result = self.api.submit_update(
				"NT-2026-00001",
				"Working",
				25,
				"Made progress",
			)

		self.assertTrue(result["ok"])
		self.assertEqual(create.call_args_list[0].kwargs["update_type"], "Progress Update")
		# Open -> Working also records a permanent status-change history entry.
		self.assertEqual(create.call_args_list[1].kwargs["update_type"], "Status Change")

	def test_permanent_history_on_reply(self):
		self.frappe.session.user = "creator@example.com"
		self.frappe.get_roles = lambda user=None: ["Employee"]
		task = self._task()
		history = types.SimpleNamespace(name="NTU-2026-00002")

		with (
			patch.object(self.api, "get_task_for_user", return_value=task),
			patch.object(self.api, "_create_history_entry", return_value=history) as create,
		):
			result = self.api.reply_to_task("NT-2026-00001", "Please prioritize this.")

		self.assertTrue(result["ok"])
		self.assertEqual(create.call_args.kwargs["update_type"], "Reply")

	def test_manager_reply_visibility_access(self):
		# Manager in same department can access task (hence timeline/replies).
		self.assertTrue(
			user_can_access_task(
				user="mgr@example.com",
				assigned_to="emp@example.com",
				owner="creator@example.com",
				assigned_by="creator@example.com",
				department="Sales",
				is_admin=False,
				is_manager=True,
				user_department="Sales",
			)
		)

	def test_employee_reply_visibility_access(self):
		self.assertTrue(
			user_can_access_task(
				user="emp@example.com",
				assigned_to="emp@example.com",
				owner="creator@example.com",
				assigned_by="creator@example.com",
				department="Sales",
				is_admin=False,
				is_manager=False,
				user_department="Sales",
			)
		)

	def test_reassign_permission_denied_for_assignee(self):
		self.frappe.session.user = "emp@example.com"
		self.frappe.get_roles = lambda user=None: ["Employee"]
		task = self._task()

		with patch.object(self.api, "get_task_for_user", return_value=task):
			with self.assertRaises(self.frappe.PermissionError):
				self.api.reassign_task("NT-2026-00001", "other@example.com")

	def test_reassign_permission_allowed_for_creator(self):
		self.frappe.session.user = "creator@example.com"
		self.frappe.get_roles = lambda user=None: ["Employee"]
		task = self._task()
		history = types.SimpleNamespace(name="NTU-2026-00003")

		with (
			patch.object(self.api, "get_task_for_user", return_value=task),
			patch.object(self.api, "_create_history_entry", return_value=history),
			patch.object(self.frappe.db, "exists", return_value=True),
			patch.object(self.frappe.db, "get_value", return_value=None),
		):
			result = self.api.reassign_task("NT-2026-00001", "other@example.com", "handover")

		self.assertTrue(result["ok"])
		self.assertEqual(result["assigned_to"], "other@example.com")

	def test_close_permission_denied_for_assignee(self):
		self.frappe.session.user = "emp@example.com"
		self.frappe.get_roles = lambda user=None: ["Employee"]
		task = self._task()

		with patch.object(self.api, "get_task_for_user", return_value=task):
			with self.assertRaises(self.frappe.PermissionError):
				self.api.close_task("NT-2026-00001", "done")

	def test_close_permission_allowed_for_manager(self):
		self.frappe.session.user = "mgr@example.com"
		self.frappe.get_roles = lambda user=None: ["NAVE Task Manager"]
		task = self._task()
		history = types.SimpleNamespace(name="NTU-2026-00004")

		with (
			patch.object(self.api, "get_task_for_user", return_value=task),
			patch.object(self.api, "get_user_department", return_value="Sales"),
			patch.object(self.api, "_create_history_entry", return_value=history),
		):
			result = self.api.close_task("NT-2026-00001", "Closing now")

		self.assertTrue(result["ok"])
		self.assertEqual(result["status"], "Closed")

	def test_closed_task_rejects_employee_update(self):
		self.frappe.session.user = "emp@example.com"
		self.frappe.get_roles = lambda user=None: ["Employee"]
		task = self._task(status="Closed")

		with patch.object(self.api, "get_task_for_user", return_value=task):
			with self.assertRaises(self.frappe.ValidationError):
				self.api.submit_update(
					"NT-2026-00001",
					"Working",
					50,
					"Still working",
				)

	def test_dashboard_counter_accuracy(self):
		self.frappe.session.user = "emp@example.com"
		self.frappe.get_roles = lambda user=None: ["Employee"]

		counts = {
			"Open": 2,
			"Working": 1,
			"Pending": 1,
			"overdue": 3,
			"Completed": 4,
		}

		def fake_count(doctype, filters=None, or_filters=None, **kwargs):
			filters = filters or {}
			if isinstance(filters, dict):
				status = filters.get("status")
				if isinstance(status, str) and status in counts:
					return [{"name": f"T{i}"} for i in range(counts[status])]
				if filters.get("is_overdue") == 1:
					return [{"name": f"O{i}"} for i in range(counts["overdue"])]
			return [{"name": "X0"}]

		with patch.object(self.frappe, "get_list", side_effect=fake_count):
			result = self.api.get_dashboard_counts()

		self.assertEqual(result["open"], 2)
		self.assertEqual(result["working"], 1)
		self.assertEqual(result["pending"], 1)
		self.assertEqual(result["overdue"], 3)
		self.assertEqual(result["completed"], 4)


class TestSchedulerRegistration(unittest.TestCase):
	def test_hooks_registers_daily_overdue_job(self):
		import importlib

		# hooks imports frappe-free; load source by path exec of scheduler block
		hooks_path = WORKSPACE / "project_custom" / "hooks.py"
		text = hooks_path.read_text()
		self.assertIn("scheduler_events", text)
		self.assertIn(
			"project_custom.api.nave_task.run_daily_nave_task_jobs",
			text,
		)


if __name__ == "__main__":
	unittest.main()
