"""Batch 7B NAVE Task Script Report tests."""

from __future__ import annotations

import json
import sys
import types
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

WORKSPACE = Path(__file__).resolve().parents[2]
if str(WORKSPACE) not in sys.path:
	sys.path.insert(0, str(WORKSPACE))


def _install_fake_frappe():
	if "frappe" in sys.modules and hasattr(sys.modules["frappe"], "_nave_tasks_stub"):
		return sys.modules["frappe"]

	frappe = types.ModuleType("frappe")
	frappe._nave_tasks_stub = True
	frappe.session = types.SimpleNamespace(user="emp@example.com")
	frappe.PermissionError = type("PermissionError", (Exception,), {})
	frappe.ValidationError = type("ValidationError", (Exception,), {})
	frappe.throw = lambda msg, exc=None: (_ for _ in ()).throw((exc or Exception)(msg))
	frappe.get_roles = lambda user=None: ["Employee"]
	frappe.db = types.SimpleNamespace(escape=lambda value: f"'{value}'")
	frappe.get_list = lambda *a, **k: []
	frappe.get_all = lambda *a, **k: []
	frappe.set_user = lambda u: None
	frappe.whitelist = lambda *a, **k: (lambda fn: fn)
	frappe.flags = types.SimpleNamespace()
	frappe.local = types.SimpleNamespace()

	utils = types.ModuleType("frappe.utils")
	utils.nowdate = lambda: "2026-07-29"
	utils.getdate = lambda d: d if hasattr(d, "year") else date.fromisoformat(str(d)[:10])
	frappe.utils = utils

	sys.modules["frappe"] = frappe
	sys.modules["frappe.utils"] = utils
	sys.modules["frappe.model"] = types.ModuleType("frappe.model")
	doc = types.ModuleType("frappe.model.document")
	doc.Document = type("Document", (), {})
	sys.modules["frappe.model.document"] = doc
	return frappe


_install_fake_frappe()

from project_custom.nave_task_script_reports import (  # noqa: E402
	OVERDUE_AGING_BUCKETS,
	PENDING_AGING_BUCKETS,
	days_overdue,
	execute_my_tasks,
	execute_overdue_tasks,
	execute_pending_aging,
	execute_team_tasks,
	my_tasks_columns,
	overdue_aging_bucket,
	overdue_tasks_columns,
	pending_age_days,
	pending_aging_bucket,
	pending_aging_columns,
	team_tasks_columns,
)
from project_custom.nave_task_utils import user_can_access_task  # noqa: E402


TODAY = date(2026, 7, 29)
REPORT_ROOT = (
	WORKSPACE / "project_custom" / "project_custom" / "report"
)


def _row(**kwargs):
	defaults = {
		"name": "NT-1",
		"subject": "Task",
		"status": "Working",
		"priority": "High",
		"assigned_to": "emp@example.com",
		"assigned_by": "creator@example.com",
		"owner": "creator@example.com",
		"department": "Sales",
		"project": "PROJ-1",
		"due_date": (TODAY - timedelta(days=2)).isoformat(),
		"is_overdue": 1,
		"creation": (TODAY - timedelta(days=10)).isoformat() + " 09:00:00",
		"modified": TODAY.isoformat() + " 10:00:00",
	}
	defaults.update(kwargs)
	return defaults


class TestAgingHelpers(unittest.TestCase):
	def test_days_overdue(self):
		self.assertEqual(days_overdue("2026-07-28", "Working", TODAY), 1)
		self.assertEqual(days_overdue("2026-07-29", "Working", TODAY), 0)
		self.assertEqual(days_overdue("2026-07-01", "Completed", TODAY), 0)
		self.assertEqual(days_overdue("2026-07-01", "Closed", TODAY), 0)
		self.assertEqual(days_overdue("2026-07-01", "Cancelled", TODAY), 0)

	def test_overdue_buckets(self):
		self.assertEqual(overdue_aging_bucket(1), "1-3 Days")
		self.assertEqual(overdue_aging_bucket(3), "1-3 Days")
		self.assertEqual(overdue_aging_bucket(4), "4-7 Days")
		self.assertEqual(overdue_aging_bucket(7), "4-7 Days")
		self.assertEqual(overdue_aging_bucket(8), "8-15 Days")
		self.assertEqual(overdue_aging_bucket(15), "8-15 Days")
		self.assertEqual(overdue_aging_bucket(16), "16-30 Days")
		self.assertEqual(overdue_aging_bucket(30), "16-30 Days")
		self.assertEqual(overdue_aging_bucket(31), "30+ Days")
		self.assertIsNone(overdue_aging_bucket(0))
		self.assertEqual(set(OVERDUE_AGING_BUCKETS), {
			"1-3 Days", "4-7 Days", "8-15 Days", "16-30 Days", "30+ Days"
		})

	def test_pending_buckets(self):
		self.assertEqual(pending_aging_bucket(0), "0-3 Days")
		self.assertEqual(pending_aging_bucket(3), "0-3 Days")
		self.assertEqual(pending_aging_bucket(4), "4-7 Days")
		self.assertEqual(pending_aging_bucket(8), "8-15 Days")
		self.assertEqual(pending_aging_bucket(16), "16-30 Days")
		self.assertEqual(pending_aging_bucket(40), "30+ Days")
		self.assertEqual(pending_age_days("2026-07-19 09:00:00", TODAY), 10)
		self.assertEqual(set(PENDING_AGING_BUCKETS), {
			"0-3 Days", "4-7 Days", "8-15 Days", "16-30 Days", "30+ Days"
		})


class TestMyTasksReport(unittest.TestCase):
	def test_forces_current_user_assignee(self):
		captured = {}

		def fake_rows(filters, **kwargs):
			captured["filters"] = dict(filters or {})
			captured["user"] = kwargs.get("user")
			return [_row(assigned_to="emp@example.com")]

		with patch(
			"project_custom.nave_task_script_reports.get_task_rows",
			side_effect=fake_rows,
		):
			columns, data, *_rest = execute_my_tasks(
				{"assigned_to": "other@example.com", "status": "Working"},
				user="emp@example.com",
				today=TODAY,
			)
		self.assertEqual(captured["filters"]["assigned_to"], "emp@example.com")
		self.assertEqual(captured["user"], "emp@example.com")
		self.assertEqual(data[0]["assigned_to"] if "assigned_to" in data[0] else None, None)
		# My Tasks columns do not expose assigned_to override; created_by present
		self.assertEqual(data[0]["created_by"], "creator@example.com")
		self.assertTrue(any(c["fieldname"] == "name" and c["options"] == "NAVE Task" for c in columns))

	def test_cannot_view_another_user_via_filter(self):
		with patch(
			"project_custom.nave_task_script_reports.get_task_rows",
			return_value=[],
		) as rows_fn:
			execute_my_tasks({"assigned_to": "victim@example.com"}, user="emp@example.com", today=TODAY)
		self.assertEqual(rows_fn.call_args.args[0]["assigned_to"], "emp@example.com")


class TestTeamTasksPermissions(unittest.TestCase):
	def test_employee_access_matrix_unrelated_false(self):
		self.assertFalse(
			user_can_access_task(
				user="emp@example.com",
				assigned_to="other@example.com",
				owner="boss@example.com",
				assigned_by="boss@example.com",
				department="Sales",
				is_admin=False,
				is_manager=False,
				user_department="Purchase",
			)
		)

	def test_manager_department_access(self):
		self.assertTrue(
			user_can_access_task(
				user="mgr@example.com",
				assigned_to="emp@example.com",
				owner="boss@example.com",
				assigned_by="boss@example.com",
				department="Sales",
				is_admin=False,
				is_manager=True,
				user_department="Sales",
			)
		)

	def test_director_and_admin(self):
		self.assertTrue(
			user_can_access_task(
				user="dir@example.com",
				assigned_to="emp@example.com",
				owner="x",
				assigned_by="x",
				department="Sales",
				is_admin=False,
				is_director=True,
				is_manager=False,
				user_department=None,
			)
		)
		self.assertTrue(
			user_can_access_task(
				user="Administrator",
				assigned_to="emp@example.com",
				owner="x",
				assigned_by="x",
				department="Sales",
				is_admin=True,
				is_manager=False,
				user_department=None,
			)
		)

	def test_team_tasks_passes_filters_to_service(self):
		with patch(
			"project_custom.nave_task_script_reports.get_task_rows",
			return_value=[_row()],
		) as rows_fn:
			columns, data, *rest = execute_team_tasks(
				{"department": "Sales", "assigned_to": "emp@example.com"},
				user="mgr@example.com",
				today=TODAY,
			)
		self.assertEqual(rows_fn.call_args.kwargs["user"], "mgr@example.com")
		self.assertEqual(rows_fn.call_args.args[0]["department"], "Sales")
		self.assertEqual(data[0]["days_overdue"], 2)
		self.assertTrue(any(c["fieldname"] == "assigned_to" for c in columns))


class TestOverdueReport(unittest.TestCase):
	def test_excludes_terminal_and_calculates_days(self):
		rows = [
			_row(name="NT-O", status="Open", due_date=(TODAY - timedelta(days=5)).isoformat()),
			_row(name="NT-C", status="Completed", due_date=(TODAY - timedelta(days=5)).isoformat()),
			_row(name="NT-CL", status="Closed", due_date=(TODAY - timedelta(days=5)).isoformat()),
			_row(name="NT-X", status="Cancelled", due_date=(TODAY - timedelta(days=5)).isoformat()),
			_row(name="NT-W", status="Working", due_date=TODAY.isoformat(), is_overdue=0),
		]
		with patch(
			"project_custom.nave_task_script_reports.get_task_rows",
			return_value=rows,
		) as rows_fn:
			_columns, data, *_ = execute_overdue_tasks({}, user="mgr@example.com", today=TODAY)
		# Forced active status + due_date_to yesterday
		filt = rows_fn.call_args.args[0]
		self.assertEqual(set(filt["status"]), {"Open", "Working", "Pending"})
		self.assertEqual(filt["due_date_to"], "2026-07-28")
		names = [r["name"] for r in data]
		self.assertEqual(names, ["NT-O"])
		self.assertEqual(data[0]["days_overdue"], 5)
		self.assertEqual(data[0]["aging_bucket"], "4-7 Days")

	def test_every_overdue_bucket(self):
		cases = [
			(1, "1-3 Days"),
			(3, "1-3 Days"),
			(4, "4-7 Days"),
			(7, "4-7 Days"),
			(8, "8-15 Days"),
			(15, "8-15 Days"),
			(16, "16-30 Days"),
			(30, "16-30 Days"),
			(45, "30+ Days"),
		]
		for days, bucket in cases:
			rows = [
				_row(
					name=f"NT-{days}",
					status="Pending",
					due_date=(TODAY - timedelta(days=days)).isoformat(),
					priority="High" if days >= 8 else "Low",
				)
			]
			with patch(
				"project_custom.nave_task_script_reports.get_task_rows",
				return_value=rows,
			):
				_c, data, *_rest = execute_overdue_tasks(
					{"aging_bucket": bucket},
					user="mgr@example.com",
					today=TODAY,
				)
			self.assertEqual(len(data), 1, msg=days)
			self.assertEqual(data[0]["aging_bucket"], bucket)


class TestPendingAgingReport(unittest.TestCase):
	def test_only_active_and_age(self):
		rows = [
			_row(
				name="NT-A",
				status="Open",
				creation=(TODAY - timedelta(days=2)).isoformat() + " 08:00:00",
				due_date=(TODAY + timedelta(days=1)).isoformat(),
				is_overdue=0,
			),
			_row(name="NT-C", status="Completed", creation=(TODAY - timedelta(days=20)).isoformat()),
		]
		with patch(
			"project_custom.nave_task_script_reports.get_task_rows",
			return_value=rows,
		) as rows_fn:
			_c, data, *_ = execute_pending_aging({}, user="mgr@example.com", today=TODAY)
		self.assertEqual(set(rows_fn.call_args.args[0]["status"]), {"Open", "Working", "Pending"})
		self.assertEqual([r["name"] for r in data], ["NT-A"])
		self.assertEqual(data[0]["pending_age_days"], 2)
		self.assertEqual(data[0]["pending_aging_bucket"], "0-3 Days")

	def test_every_pending_bucket(self):
		cases = [
			(0, "0-3 Days"),
			(3, "0-3 Days"),
			(4, "4-7 Days"),
			(8, "8-15 Days"),
			(16, "16-30 Days"),
			(40, "30+ Days"),
		]
		for days, bucket in cases:
			rows = [
				_row(
					name=f"NT-P{days}",
					status="Working",
					creation=(TODAY - timedelta(days=days)).isoformat() + " 08:00:00",
					due_date=(TODAY + timedelta(days=5)).isoformat(),
					is_overdue=0,
				)
			]
			with patch(
				"project_custom.nave_task_script_reports.get_task_rows",
				return_value=rows,
			):
				_c, data, *_ = execute_pending_aging(
					{"pending_aging_bucket": bucket},
					user="mgr@example.com",
					today=TODAY,
				)
			self.assertEqual(len(data), 1, msg=days)
			self.assertEqual(data[0]["pending_aging_bucket"], bucket)


class TestColumnsAndLinks(unittest.TestCase):
	def test_column_fieldtypes_and_task_links(self):
		for columns_fn in (
			my_tasks_columns,
			team_tasks_columns,
			overdue_tasks_columns,
			pending_aging_columns,
		):
			columns = columns_fn()
			by_name = {c["fieldname"]: c for c in columns}
			self.assertEqual(by_name["name"]["fieldtype"], "Link")
			self.assertEqual(by_name["name"]["options"], "NAVE Task")
			if "project" in by_name:
				self.assertEqual(by_name["project"]["fieldtype"], "Link")
				self.assertEqual(by_name["project"]["options"], "Project")
			if "days_overdue" in by_name:
				self.assertEqual(by_name["days_overdue"]["fieldtype"], "Int")
			if "pending_age_days" in by_name:
				self.assertEqual(by_name["pending_age_days"]["fieldtype"], "Int")
			if "due_date" in by_name:
				self.assertEqual(by_name["due_date"]["fieldtype"], "Date")

	def test_report_json_files_exist(self):
		for folder, report_name in (
			("nave_my_tasks", "NAVE My Tasks"),
			("nave_team_tasks", "NAVE Team Tasks"),
			("nave_overdue_tasks", "NAVE Overdue Tasks"),
			("nave_pending_aging", "NAVE Pending Aging"),
		):
			path = REPORT_ROOT / folder / f"{folder}.json"
			self.assertTrue(path.exists(), msg=path)
			payload = json.loads(path.read_text())
			self.assertEqual(payload["report_type"], "Script Report")
			self.assertEqual(payload["ref_doctype"], "NAVE Task")
			self.assertEqual(payload["name"], report_name)
			self.assertEqual(payload["is_standard"], "Yes")


if __name__ == "__main__":
	unittest.main()
