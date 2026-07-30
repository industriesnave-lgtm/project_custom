"""Batch 7A NAVE Task reporting service foundation tests."""

from __future__ import annotations

import sys
import types
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

WORKSPACE = Path(__file__).resolve().parents[2]
if str(WORKSPACE) not in sys.path:
	sys.path.insert(0, str(WORKSPACE))


def _install_fake_frappe():
	if "frappe" in sys.modules and hasattr(sys.modules["frappe"], "_nave_tasks_stub"):
		frappe = sys.modules["frappe"]
		if not hasattr(frappe, "get_list"):
			frappe.get_list = MagicMock(return_value=[])
		if not hasattr(frappe, "set_user"):
			frappe.set_user = MagicMock()
		return frappe

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
		exists=MagicMock(return_value=False),
		set_value=MagicMock(),
		count=MagicMock(return_value=0),
		sql=MagicMock(),
		commit=MagicMock(),
		has_column=MagicMock(return_value=True),
	)
	frappe.get_doc = MagicMock()
	frappe.get_all = MagicMock(return_value=[])
	frappe.get_list = MagicMock(return_value=[])
	frappe.set_user = MagicMock()
	frappe.whitelist = lambda *a, **k: (lambda fn: fn)
	frappe.flags = types.SimpleNamespace(
		in_migrate=False, in_install=False, in_patch=False, mute_emails=False
	)
	frappe.local = types.SimpleNamespace()

	utils = types.ModuleType("frappe.utils")
	utils.cint = lambda v: int(float(v or 0))
	utils.flt = lambda v: float(v or 0)
	utils.nowdate = lambda: "2026-07-29"
	utils.now_datetime = lambda: "2026-07-29 12:00:00"
	utils.add_days = lambda d, n: d
	utils.getdate = lambda d: d if hasattr(d, "year") else date.fromisoformat(str(d)[:10])
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

from project_custom.nave_task_reporting import (  # noqa: E402
	build_frappe_filters,
	build_summary_from_rows,
	get_permission_conditions,
	get_summary,
	get_task_rows,
	normalize_filters,
)
from project_custom.nave_task_utils import (  # noqa: E402
	build_task_permission_condition,
	user_can_access_task,
)


TODAY = date(2026, 7, 29)


class TestNormalizeFilters(unittest.TestCase):
	def test_strips_and_keeps_supported_keys(self):
		result = normalize_filters(
			{
				"assigned_to": " emp@example.com ",
				"department": "Sales",
				"project": "PROJ-1",
				"status": "Working",
				"priority": "High",
				"from_date": "2026-07-01",
				"to_date": "2026-07-29",
				"due_date_from": "2026-07-20",
				"due_date_to": "2026-07-30",
				"created_by": "creator@example.com",
				"unknown": "ignore-me",
				"empty": "",
			}
		)
		self.assertEqual(result["assigned_to"], "emp@example.com")
		self.assertEqual(result["department"], "Sales")
		self.assertEqual(result["project"], "PROJ-1")
		self.assertEqual(result["status"], "Working")
		self.assertEqual(result["priority"], "High")
		self.assertEqual(result["created_by"], "creator@example.com")
		self.assertEqual(result["from_date"], "2026-07-01")
		self.assertEqual(result["due_date_to"], "2026-07-30")
		self.assertNotIn("unknown", result)

	def test_status_and_priority_lists(self):
		result = normalize_filters({"status": ["Open", "Working"], "priority": "High, Medium"})
		self.assertEqual(result["status"], ["Open", "Working"])
		self.assertEqual(result["priority"], ["High", "Medium"])

	def test_drops_inverted_ranges(self):
		result = normalize_filters(
			{"from_date": "2026-07-29", "to_date": "2026-07-01", "due_date_from": "2026-08-01", "due_date_to": "2026-07-01"}
		)
		self.assertNotIn("from_date", result)
		self.assertNotIn("to_date", result)
		self.assertNotIn("due_date_from", result)
		self.assertNotIn("due_date_to", result)


class TestBuildFrappeFilters(unittest.TestCase):
	def test_assigned_department_project_status_priority(self):
		filters, or_filters = build_frappe_filters(
			normalize_filters(
				{
					"assigned_to": "emp@example.com",
					"department": "Sales",
					"project": "PROJ-1",
					"status": "Working",
					"priority": "High",
				}
			)
		)
		as_map = {f[0]: f for f in filters}
		self.assertEqual(as_map["assigned_to"], ["assigned_to", "=", "emp@example.com"])
		self.assertEqual(as_map["department"], ["department", "=", "Sales"])
		self.assertEqual(as_map["project"], ["project", "=", "PROJ-1"])
		self.assertEqual(as_map["status"], ["status", "=", "Working"])
		self.assertEqual(as_map["priority"], ["priority", "=", "High"])
		self.assertEqual(or_filters, [])

	def test_created_by_uses_or_filters(self):
		filters, or_filters = build_frappe_filters(
			normalize_filters({"created_by": "creator@example.com"})
		)
		self.assertEqual(filters, [])
		self.assertIn(["owner", "=", "creator@example.com"], or_filters)
		self.assertIn(["assigned_by", "=", "creator@example.com"], or_filters)

	def test_creation_and_due_date_ranges(self):
		filters, _ = build_frappe_filters(
			normalize_filters(
				{
					"from_date": "2026-07-01",
					"to_date": "2026-07-29",
					"due_date_from": "2026-07-20",
					"due_date_to": "2026-07-30",
				}
			)
		)
		as_map = {}
		for f in filters:
			as_map.setdefault(f[0], []).append(f)
		self.assertEqual(as_map["creation"][0][1:], [">=", "2026-07-01 00:00:00"])
		self.assertEqual(as_map["creation"][1][1:], ["<=", "2026-07-29 23:59:59"])
		self.assertEqual(as_map["due_date"][0][1:], [">=", "2026-07-20"])
		self.assertEqual(as_map["due_date"][1][1:], ["<=", "2026-07-30"])


class TestPermissionConditions(unittest.TestCase):
	def setUp(self):
		self.frappe = _install_fake_frappe()

	def test_guest_and_unauthorized_see_nothing(self):
		self.frappe.session.user = "Guest"
		self.assertEqual(get_permission_conditions("Guest"), "1=0")
		self.assertEqual(get_permission_conditions(None), "1=0")

	def test_employee_condition_assignee_or_creator(self):
		sql = build_task_permission_condition(
			"emp@example.com",
			is_admin=False,
			is_director=False,
			is_manager=False,
			department="Sales",
			escape=lambda v: f"'{v}'",
		)
		self.assertIn("assigned_to", sql)
		self.assertIn("owner", sql)
		self.assertNotIn("`tabNAVE Task`.`department`", sql)

	def test_manager_sees_department(self):
		sql = build_task_permission_condition(
			"mgr@example.com",
			is_admin=False,
			is_director=False,
			is_manager=True,
			department="Sales",
			escape=lambda v: f"'{v}'",
		)
		self.assertIn("department", sql)
		self.assertIn("'Sales'", sql)

	def test_director_and_admin_unrestricted(self):
		for kwargs in (
			dict(is_admin=True, is_director=False, is_manager=False),
			dict(is_admin=False, is_director=True, is_manager=False),
		):
			sql = build_task_permission_condition(
				"elevated@example.com",
				department="Sales",
				escape=lambda v: f"'{v}'",
				**kwargs,
			)
			self.assertEqual(sql, "")

	def test_get_permission_conditions_uses_existing_helper(self):
		with patch(
			"project_custom.nave_task_reporting.get_task_query_conditions",
			return_value="(`tabNAVE Task`.`assigned_to` = 'emp@example.com')",
		):
			self.assertIn("assigned_to", get_permission_conditions("emp@example.com"))

	def test_user_can_access_matrix(self):
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
		self.assertTrue(
			user_can_access_task(
				user="dir@example.com",
				assigned_to="emp@example.com",
				owner="creator@example.com",
				assigned_by="creator@example.com",
				department="Sales",
				is_admin=False,
				is_director=True,
				is_manager=False,
				user_department="HR",
			)
		)
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
		self.assertTrue(
			user_can_access_task(
				user="Administrator",
				assigned_to="emp@example.com",
				owner="creator@example.com",
				assigned_by="creator@example.com",
				department="Sales",
				is_admin=True,
				is_manager=False,
				user_department=None,
			)
		)


class TestGetTaskRows(unittest.TestCase):
	def setUp(self):
		self.frappe = _install_fake_frappe()
		self.frappe.session.user = "emp@example.com"
		self.frappe.get_list = MagicMock(return_value=[{"name": "NT-1"}])
		self.frappe.set_user = MagicMock()

	def test_guest_returns_empty(self):
		self.assertEqual(get_task_rows({}, user="Guest"), [])
		self.frappe.get_list.assert_not_called()

	def test_blocked_permission_returns_empty(self):
		with patch(
			"project_custom.nave_task_reporting.get_permission_conditions",
			return_value="1=0",
		):
			self.assertEqual(get_task_rows({}, user="nobody@example.com"), [])

	def test_uses_get_list_without_ignoring_permissions(self):
		with patch(
			"project_custom.nave_task_reporting.get_permission_conditions",
			return_value="",
		):
			rows = get_task_rows(
				{"assigned_to": "emp@example.com", "department": "Sales"},
				user="emp@example.com",
			)
		self.assertEqual(rows, [{"name": "NT-1"}])
		kwargs = self.frappe.get_list.call_args.kwargs
		self.assertEqual(kwargs["ignore_permissions"], False)
		filters = kwargs["filters"]
		self.assertIn(["assigned_to", "=", "emp@example.com"], filters)
		self.assertIn(["department", "=", "Sales"], filters)


class TestSummary(unittest.TestCase):
	def test_summary_counts(self):
		rows = [
			{"status": "Open", "priority": "Low", "due_date": "2026-08-01", "is_overdue": 0},
			{"status": "Working", "priority": "High", "due_date": "2026-07-29", "is_overdue": 0},
			{"status": "Pending", "priority": "Medium", "due_date": "2026-07-30", "is_overdue": 0},
			{"status": "Completed", "priority": "High", "due_date": "2026-07-01", "is_overdue": 1},
			{"status": "Closed", "priority": "Low", "due_date": "2026-07-01", "is_overdue": 1},
			{"status": "Working", "priority": "High", "due_date": "2026-07-01", "is_overdue": 1},
			{"status": "Cancelled", "priority": "High", "due_date": "2026-07-01", "is_overdue": 1},
		]
		summary = build_summary_from_rows(rows, today=TODAY)
		self.assertEqual(summary["total"], 7)
		self.assertEqual(summary["open"], 1)
		self.assertEqual(summary["working"], 2)
		self.assertEqual(summary["pending"], 1)
		self.assertEqual(summary["completed"], 1)
		self.assertEqual(summary["closed"], 1)
		self.assertEqual(summary["high_priority"], 4)
		# Overdue excludes Completed/Closed/Cancelled → only one Working overdue
		self.assertEqual(summary["overdue"], 1)
		self.assertEqual(summary["due_today"], 1)
		self.assertEqual(summary["due_tomorrow"], 1)

	def test_due_today_and_tomorrow_ignore_terminal(self):
		rows = [
			{"status": "Completed", "priority": "High", "due_date": TODAY.isoformat(), "is_overdue": 0},
			{"status": "Closed", "priority": "High", "due_date": (TODAY + timedelta(days=1)).isoformat(), "is_overdue": 0},
			{"status": "Open", "priority": "Low", "due_date": TODAY.isoformat(), "is_overdue": 0},
		]
		summary = build_summary_from_rows(rows, today=TODAY)
		self.assertEqual(summary["due_today"], 1)
		self.assertEqual(summary["due_tomorrow"], 0)

	def test_get_summary_uses_permission_aware_rows(self):
		with patch(
			"project_custom.nave_task_reporting.get_task_rows",
			return_value=[
				{"status": "Open", "priority": "High", "due_date": TODAY.isoformat(), "is_overdue": 0}
			],
		) as rows_fn:
			summary = get_summary({"department": "Sales"}, user="mgr@example.com", today=TODAY)
		rows_fn.assert_called_once()
		self.assertEqual(summary["total"], 1)
		self.assertEqual(summary["open"], 1)
		self.assertEqual(summary["high_priority"], 1)
		self.assertEqual(summary["due_today"], 1)


if __name__ == "__main__":
	unittest.main()
