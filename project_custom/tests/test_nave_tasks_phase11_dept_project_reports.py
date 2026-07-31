"""Batch 7C Part 1 — Department & Project Task report tests."""

from __future__ import annotations

import json
import sys
import types
import unittest
from datetime import date
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
	frappe.session = types.SimpleNamespace(user="mgr@example.com")
	frappe.PermissionError = type("PermissionError", (Exception,), {})
	frappe.throw = lambda msg, exc=None: (_ for _ in ()).throw((exc or Exception)(msg))
	frappe.get_roles = lambda user=None: ["NAVE Task Manager"]
	frappe.db = types.SimpleNamespace(escape=lambda value: f"'{value}'")
	frappe.get_list = lambda *a, **k: []
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
	_completion_pct,
	aggregate_by_key,
	execute_department_task_report,
	execute_project_task_report,
)
from project_custom.nave_task_utils import user_can_access_task  # noqa: E402


TODAY = date(2026, 7, 29)
REPORT_ROOT = WORKSPACE / "project_custom" / "project_custom" / "report"


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
		"due_date": "2026-07-20",
		"is_overdue": 1,
		"creation": "2026-07-01 09:00:00",
		"modified": "2026-07-28 10:00:00",
	}
	defaults.update(kwargs)
	return defaults


class TestCompletionPct(unittest.TestCase):
	def test_completion_pct(self):
		self.assertEqual(_completion_pct(0, 0), 0.0)
		self.assertEqual(_completion_pct(1, 4), 25.0)
		self.assertEqual(_completion_pct(2, 3), 66.7)


class TestDepartmentReport(unittest.TestCase):
	def test_department_totals_and_completion(self):
		rows = [
			_row(name="A", department="Sales", status="Completed", is_overdue=0, due_date="2026-07-29"),
			_row(name="B", department="Sales", status="Open", is_overdue=0, due_date="2026-07-29"),
			_row(name="C", department="Sales", status="Working", is_overdue=1, due_date="2026-07-01"),
			_row(name="D", department="HR", status="Pending", is_overdue=0, due_date="2026-08-01", priority="Low"),
			_row(name="E", department="", status="Closed", is_overdue=0, due_date="2026-07-01"),
		]
		with patch(
			"project_custom.nave_task_script_reports.get_task_rows",
			return_value=rows,
		) as rows_fn:
			columns, data, *rest = execute_department_task_report(
				{"department": "Sales"},
				user="mgr@example.com",
				today=TODAY,
			)
		self.assertEqual(rows_fn.call_args.kwargs["user"], "mgr@example.com")
		self.assertEqual(rows_fn.call_args.args[0].get("department"), "Sales")
		by_dept = {r["department"]: r for r in data}
		self.assertEqual(by_dept["Sales"]["total"], 3)
		self.assertEqual(by_dept["Sales"]["completed"], 1)
		self.assertEqual(by_dept["Sales"]["open"], 1)
		self.assertEqual(by_dept["Sales"]["working"], 1)
		self.assertEqual(by_dept["Sales"]["overdue"], 1)
		self.assertEqual(by_dept["Sales"]["due_today"], 1)
		self.assertEqual(by_dept["Sales"]["high_priority"], 3)
		self.assertEqual(by_dept["Sales"]["completion_pct"], 33.3)
		self.assertEqual(by_dept["HR"]["total"], 1)
		self.assertEqual(by_dept["(No Department)"]["total"], 1)
		self.assertEqual(by_dept["(No Department)"]["closed"], 1)
		self.assertTrue(any(c["fieldname"] == "completion_pct" for c in columns))

	def test_department_permissions_matrix(self):
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

	def test_empty_department_handling(self):
		groups = aggregate_by_key(
			[_row(department=None), _row(department="")],
			group_field="department",
			empty_label="(No Department)",
			today=TODAY,
		)
		self.assertEqual(list(groups.keys()), ["(No Department)"])
		self.assertEqual(groups["(No Department)"]["total"], 2)


class TestProjectReport(unittest.TestCase):
	def test_project_totals_completion_and_last_activity(self):
		rows = [
			_row(
				name="A",
				project="PROJ-1",
				status="Completed",
				is_overdue=0,
				modified="2026-07-20 10:00:00",
			),
			_row(
				name="B",
				project="PROJ-1",
				status="Open",
				is_overdue=1,
				modified="2026-07-28 12:00:00",
			),
			_row(
				name="C",
				project="PROJ-2",
				status="Working",
				is_overdue=0,
				modified="2026-07-15 09:00:00",
				due_date="2026-08-01",
			),
			_row(name="D", project="", status="Pending", is_overdue=0, modified="2026-07-10 09:00:00"),
		]
		with patch(
			"project_custom.nave_task_script_reports.get_task_rows",
			return_value=rows,
		) as rows_fn:
			columns, data, *rest = execute_project_task_report(
				{"project": "PROJ-1"},
				user="dir@example.com",
				today=TODAY,
			)
		self.assertEqual(rows_fn.call_args.kwargs["user"], "dir@example.com")
		self.assertEqual(rows_fn.call_args.args[0].get("project"), "PROJ-1")
		by_project = {(r["project"] or "(No Project)"): r for r in data}
		self.assertEqual(by_project["PROJ-1"]["total"], 2)
		self.assertEqual(by_project["PROJ-1"]["completed"], 1)
		self.assertEqual(by_project["PROJ-1"]["completion_pct"], 50.0)
		self.assertEqual(by_project["PROJ-1"]["overdue"], 1)
		self.assertEqual(by_project["PROJ-1"]["last_activity"], "2026-07-28 12:00:00")
		self.assertEqual(by_project["PROJ-2"]["total"], 1)
		self.assertTrue(by_project["(No Project)"]["_empty_project"])
		self.assertIsNone(by_project["(No Project)"]["project"])
		self.assertTrue(any(c["options"] == "Project" for c in columns if c["fieldname"] == "project"))

	def test_project_permissions_matrix(self):
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
		self.assertFalse(
			user_can_access_task(
				user="outsider@example.com",
				assigned_to="emp@example.com",
				owner="creator@example.com",
				assigned_by="creator@example.com",
				department="Sales",
				is_admin=False,
				is_manager=False,
				user_department="Finance",
			)
		)

	def test_empty_project_handling(self):
		groups = aggregate_by_key(
			[_row(project=None), _row(project="")],
			group_field="project",
			empty_label="(No Project)",
			today=TODAY,
		)
		self.assertEqual(list(groups.keys()), ["(No Project)"])
		self.assertEqual(groups["(No Project)"]["total"], 2)

	def test_report_json_exists(self):
		for folder, name in (
			("nave_department_task_report", "NAVE Department Task Report"),
			("nave_project_task_report", "NAVE Project Task Report"),
		):
			path = REPORT_ROOT / folder / f"{folder}.json"
			payload = json.loads(path.read_text())
			self.assertEqual(payload["name"], name)
			self.assertEqual(payload["report_type"], "Script Report")
			self.assertEqual(payload["ref_doctype"], "NAVE Task")


if __name__ == "__main__":
	unittest.main()
