"""Batch 7C Part 2 — Employee Performance & Completed Task report tests."""

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
	frappe.session = types.SimpleNamespace(user="emp@example.com")
	frappe.PermissionError = type("PermissionError", (Exception,), {})
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

from project_custom.nave_task_reporting import (  # noqa: E402
	build_frappe_filters,
	normalize_filters,
)
from project_custom.nave_task_script_reports import (  # noqa: E402
	classify_completion_result,
	completion_days,
	delay_days,
	execute_completed_task_report,
	execute_employee_performance_report,
	get_reopen_counts_by_task,
	parse_status_change_text,
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
		"completed_on": None,
		"completion_remarks": None,
		"completion_attachment": None,
	}
	defaults.update(kwargs)
	return defaults


class TestCompletionHelpers(unittest.TestCase):
	def test_completion_and_delay_days(self):
		self.assertEqual(completion_days("2026-07-01 09:00:00", "2026-07-11 18:00:00"), 10)
		self.assertIsNone(completion_days("2026-07-01", None))
		self.assertEqual(delay_days("2026-07-25", "2026-07-20"), 5)
		self.assertEqual(delay_days("2026-07-18", "2026-07-20"), 0)
		self.assertIsNone(delay_days("2026-07-25", None))

	def test_completion_result_classification(self):
		self.assertEqual(classify_completion_result("2026-07-20", "2026-07-20"), "On Time")
		self.assertEqual(classify_completion_result("2026-07-19", "2026-07-20"), "On Time")
		self.assertEqual(classify_completion_result("2026-07-21", "2026-07-20"), "Late")
		self.assertEqual(classify_completion_result("2026-07-21", None), "No Due Date")


class TestEmployeePerformancePermissions(unittest.TestCase):
	def test_employee_sees_only_own_row_and_cannot_bypass_filter(self):
		import frappe

		frappe.get_roles = lambda user=None: ["Employee"]
		rows = [
			_row(name="A", assigned_to="emp@example.com", status="Completed", completed_on="2026-07-18", due_date="2026-07-20", is_overdue=0),
			_row(name="B", assigned_to="other@example.com", status="Open", is_overdue=0),
		]

		captured = {}

		def fake_rows(filters, **kwargs):
			captured["filters"] = dict(filters or {})
			captured["user"] = kwargs.get("user")
			# Simulate permission-aware fetch: only return current user's tasks when forced.
			assignee = (filters or {}).get("assigned_to")
			return [r for r in rows if r["assigned_to"] == assignee]

		with patch(
			"project_custom.nave_task_script_reports.get_task_rows",
			side_effect=fake_rows,
		), patch(
			"project_custom.nave_task_script_reports.get_reopen_counts_by_task",
			return_value={},
		):
			_columns, data, *_rest = execute_employee_performance_report(
				{"assigned_to": "victim@example.com"},
				user="emp@example.com",
				today=TODAY,
			)

		self.assertEqual(captured["filters"]["assigned_to"], "emp@example.com")
		self.assertEqual(captured["user"], "emp@example.com")
		self.assertEqual(len(data), 1)
		self.assertEqual(data[0]["assigned_to"], "emp@example.com")

	def test_manager_sees_permitted_employees_only(self):
		import frappe

		frappe.get_roles = lambda user=None: ["NAVE Task Manager"]
		rows = [
			_row(name="A", assigned_to="emp@example.com", department="Sales", status="Working", is_overdue=0, due_date="2026-08-01"),
			_row(name="B", assigned_to="peer@example.com", department="Sales", status="Pending", is_overdue=0, due_date="2026-08-01"),
		]
		with patch(
			"project_custom.nave_task_script_reports.get_task_rows",
			return_value=rows,
		) as rows_fn, patch(
			"project_custom.nave_task_script_reports.get_reopen_counts_by_task",
			return_value={},
		):
			_columns, data, *_rest = execute_employee_performance_report(
				{"department": "Sales"},
				user="mgr@example.com",
				today=TODAY,
			)
		self.assertEqual(rows_fn.call_args.kwargs["user"], "mgr@example.com")
		self.assertEqual(rows_fn.call_args.args[0].get("department"), "Sales")
		# Manager filter assigned_to is not forced to self.
		self.assertNotEqual(rows_fn.call_args.args[0].get("assigned_to"), "mgr@example.com")
		by_user = {r["assigned_to"]: r for r in data}
		self.assertEqual(set(by_user), {"emp@example.com", "peer@example.com"})

	def test_unrelated_department_matrix(self):
		self.assertFalse(
			user_can_access_task(
				user="mgr@example.com",
				assigned_to="emp@example.com",
				owner="boss@example.com",
				assigned_by="boss@example.com",
				department="Finance",
				is_admin=False,
				is_manager=True,
				user_department="Sales",
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


class TestEmployeePerformanceMetrics(unittest.TestCase):
	def setUp(self):
		import frappe

		frappe.get_roles = lambda user=None: ["NAVE Task Manager"]

	def _run(self, rows, reopen_map=None):
		with patch(
			"project_custom.nave_task_script_reports.get_task_rows",
			return_value=rows,
		), patch(
			"project_custom.nave_task_script_reports.get_reopen_counts_by_task",
			return_value=reopen_map or {},
		):
			return execute_employee_performance_report(
				{},
				user="mgr@example.com",
				today=TODAY,
			)

	def test_counts_pct_on_time_late_averages(self):
		rows = [
			# On-time completed (creation 7/1 → complete 7/10 = 9 days; due 7/20)
			_row(
				name="C1",
				assigned_to="emp@example.com",
				status="Completed",
				completed_on="2026-07-10 12:00:00",
				due_date="2026-07-20",
				is_overdue=0,
				creation="2026-07-01 09:00:00",
			),
			# Late closed (complete 7/25 vs due 7/20 = delay 5; days 24)
			_row(
				name="C2",
				assigned_to="emp@example.com",
				status="Closed",
				completed_on="2026-07-25 12:00:00",
				due_date="2026-07-20",
				is_overdue=0,
				creation="2026-07-01 09:00:00",
			),
			# Active pending
			_row(
				name="A1",
				assigned_to="emp@example.com",
				status="Pending",
				is_overdue=0,
				due_date="2026-08-01",
			),
			# Active overdue (today 7/29 - due 7/20 = delay 9)
			_row(
				name="A2",
				assigned_to="emp@example.com",
				status="Working",
				is_overdue=1,
				due_date="2026-07-20",
			),
			# Open (active)
			_row(
				name="A3",
				assigned_to="emp@example.com",
				status="Open",
				is_overdue=0,
				due_date="2026-08-01",
			),
		]
		columns, data, _chart, _msg, summary = self._run(
			rows,
			reopen_map={"C1": 2, "A2": 1},
		)
		row = data[0]
		self.assertEqual(row["total_assigned"], 5)
		self.assertEqual(row["completed"], 1)
		self.assertEqual(row["closed"], 1)
		self.assertEqual(row["active"], 3)
		self.assertEqual(row["pending"], 1)
		self.assertEqual(row["overdue"], 1)
		self.assertEqual(row["completion_pct"], 40.0)  # (1+1)/5
		self.assertEqual(row["on_time_completed"], 1)
		self.assertEqual(row["late_completed"], 1)
		self.assertEqual(row["avg_completion_days"], 16.5)  # (9+24)/2
		# delay: completed 0 + closed 5 + overdue active 9 → avg 14/3? wait 0+5+9=14 / 3 = 4.7
		# On-time completed still contributes delay 0
		self.assertEqual(row["avg_delay_days"], 4.7)
		self.assertEqual(row["reopened"], 3)
		self.assertEqual(row["last_activity"], "2026-07-28 10:00:00")

		by_label = {s["label"]: s for s in summary}
		self.assertEqual(by_label["Employees"]["value"], 1)
		self.assertEqual(by_label["Total Assigned"]["value"], 5)
		self.assertEqual(by_label["Completed/Closed"]["value"], 2)
		self.assertEqual(by_label["Active"]["value"], 3)
		self.assertEqual(by_label["Overdue"]["value"], 1)
		self.assertEqual(by_label["Overall Completion %"]["value"], 40.0)

	def test_reopened_uses_history_or_zero_fallback(self):
		self.assertEqual(
			parse_status_change_text("Status changed from Completed to Working."),
			("Completed", "Working"),
		)
		self.assertTrue(
			parse_status_change_text("Status changed from Closed to Working.")[0] == "Closed"
		)
		with patch("frappe.get_all", return_value=[
			{"task": "NT-1", "update_text": "Status changed from Completed to Working."},
			{"task": "NT-1", "update_text": "Status changed from Open to Working."},
			{"task": "NT-2", "update_text": "Status changed from Closed to Working."},
		]):
			counts = get_reopen_counts_by_task(["NT-1", "NT-2"])
		self.assertEqual(counts["NT-1"], 1)
		self.assertEqual(counts["NT-2"], 1)

		with patch("frappe.get_all", side_effect=RuntimeError("no db")):
			self.assertEqual(get_reopen_counts_by_task(["NT-1"]), {})


class TestCompletedTaskReport(unittest.TestCase):
	def setUp(self):
		import frappe

		frappe.get_roles = lambda user=None: ["NAVE Task Manager"]

	def test_includes_completed_and_closed_excludes_active(self):
		rows = [
			_row(
				name="NT-C",
				status="Completed",
				completed_on="2026-07-18 10:00:00",
				due_date="2026-07-20",
				completion_remarks="Done",
				completion_attachment="/files/a.pdf",
			),
			_row(
				name="NT-Z",
				status="Closed",
				completed_on="2026-07-22 10:00:00",
				due_date="2026-07-20",
			),
			_row(name="NT-W", status="Working", completed_on=None),
			_row(name="NT-O", status="Open", completed_on=None),
		]
		captured = {}

		def fake_rows(filters, **kwargs):
			captured["filters"] = dict(filters or {})
			wanted = set(filters.get("status") or [])
			return [r for r in rows if r["status"] in wanted]

		with patch(
			"project_custom.nave_task_script_reports.get_task_rows",
			side_effect=fake_rows,
		):
			columns, data, *_rest = execute_completed_task_report(
				{"status": "Working"},
				user="mgr@example.com",
				today=TODAY,
			)

		self.assertEqual(set(captured["filters"]["status"]), {"Completed", "Closed"})
		names = {r["name"] for r in data}
		self.assertEqual(names, {"NT-C", "NT-Z"})
		self.assertTrue(any(c["fieldname"] == "name" and c["options"] == "NAVE Task" for c in columns))
		self.assertTrue(
			any(c["fieldname"] == "completion_attachment" and c["fieldtype"] == "Attach" for c in columns)
		)

	def test_completed_date_filters_and_results(self):
		rows = [
			_row(
				name="ON",
				status="Completed",
				completed_on="2026-07-18 10:00:00",
				due_date="2026-07-20",
				creation="2026-07-10 09:00:00",
			),
			_row(
				name="LATE",
				status="Closed",
				completed_on="2026-07-25 10:00:00",
				due_date="2026-07-20",
				creation="2026-07-10 09:00:00",
			),
			_row(
				name="NODUE",
				status="Completed",
				completed_on="2026-07-15 10:00:00",
				due_date=None,
				creation="2026-07-10 09:00:00",
			),
		]
		with patch(
			"project_custom.nave_task_script_reports.get_task_rows",
			return_value=rows,
		) as rows_fn:
			_columns, data, _c, _m, summary = execute_completed_task_report(
				{
					"completed_from": "2026-07-01",
					"completed_to": "2026-07-31",
					"completion_result": "Late",
				},
				user="mgr@example.com",
				today=TODAY,
			)

		self.assertEqual(rows_fn.call_args.args[0].get("completed_from"), "2026-07-01")
		self.assertEqual(rows_fn.call_args.args[0].get("completed_to"), "2026-07-31")
		self.assertEqual(len(data), 1)
		self.assertEqual(data[0]["name"], "LATE")
		self.assertEqual(data[0]["completion_result"], "Late")
		self.assertEqual(data[0]["completion_days"], 15)
		self.assertEqual(data[0]["delay_days"], 5)

		# Full unfiltered summary path
		with patch(
			"project_custom.nave_task_script_reports.get_task_rows",
			return_value=rows,
		):
			_columns, data, _c, _m, summary = execute_completed_task_report(
				{},
				user="mgr@example.com",
				today=TODAY,
			)
		by_name = {r["name"]: r for r in data}
		self.assertEqual(by_name["ON"]["completion_result"], "On Time")
		self.assertEqual(by_name["ON"]["completion_days"], 8)
		self.assertEqual(by_name["ON"]["delay_days"], 0)
		self.assertEqual(by_name["NODUE"]["completion_result"], "No Due Date")
		self.assertIsNone(by_name["NODUE"]["delay_days"])
		by_label = {s["label"]: s for s in summary}
		self.assertEqual(by_label["Total Completed"]["value"], 3)
		self.assertEqual(by_label["On Time"]["value"], 1)
		self.assertEqual(by_label["Late"]["value"], 1)
		self.assertEqual(by_label["No Due Date"]["value"], 1)

	def test_completed_filter_normalization(self):
		result = normalize_filters(
			{"completed_from": "2026-07-01", "completed_to": "2026-07-31", "completion_result": "On Time"}
		)
		self.assertEqual(result["completed_from"], "2026-07-01")
		self.assertEqual(result["completion_result"], "On Time")
		filters, _ = build_frappe_filters(result)
		completed_filters = [f for f in filters if f[0] == "completed_on"]
		self.assertEqual(len(completed_filters), 2)
		ops = {f[1] for f in completed_filters}
		self.assertEqual(ops, {">=", "<="})
		self.assertTrue(any("2026-07-01" in str(f[2]) for f in completed_filters if f[1] == ">="))
		self.assertTrue(any("2026-07-31" in str(f[2]) for f in completed_filters if f[1] == "<="))

	def test_report_json_exists(self):
		for folder, name in (
			("nave_employee_performance_report", "NAVE Employee Performance Report"),
			("nave_completed_task_report", "NAVE Completed Task Report"),
		):
			path = REPORT_ROOT / folder / f"{folder}.json"
			payload = json.loads(path.read_text())
			self.assertEqual(payload["name"], name)
			self.assertEqual(payload["report_type"], "Script Report")
			self.assertEqual(payload["ref_doctype"], "NAVE Task")


if __name__ == "__main__":
	unittest.main()
