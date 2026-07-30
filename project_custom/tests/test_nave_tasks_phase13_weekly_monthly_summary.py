"""Batch 7D — Weekly & Monthly Task Summary report tests."""

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
		frappe = sys.modules["frappe"]
		if not hasattr(frappe, "ValidationError"):
			frappe.ValidationError = type("ValidationError", (Exception,), {})
		return frappe

	frappe = types.ModuleType("frappe")
	frappe._nave_tasks_stub = True
	frappe.session = types.SimpleNamespace(user="emp@example.com")
	frappe.PermissionError = type("PermissionError", (Exception,), {})
	frappe.ValidationError = type("ValidationError", (Exception,), {})

	def throw(msg, exc=None):
		raise (exc or Exception)(msg)

	frappe.throw = throw
	frappe.get_roles = lambda user=None: ["Employee"]
	frappe.db = types.SimpleNamespace(escape=lambda value: f"'{value}'")
	frappe.get_list = lambda *a, **k: []
	frappe.get_all = lambda *a, **k: []
	frappe.set_user = lambda u: None
	frappe.whitelist = lambda *a, **k: (lambda fn: fn)
	frappe.flags = types.SimpleNamespace(mute_emails=True)
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
	MAX_SUMMARY_RANGE_DAYS,
	execute_monthly_task_summary_report,
	execute_weekly_task_summary_report,
	generate_month_periods,
	generate_week_periods,
	monthly_task_summary_columns,
	validate_summary_date_range,
	week_start_monday,
	weekly_task_summary_columns,
)
from project_custom.nave_task_utils import user_can_access_task  # noqa: E402


TODAY = date(2026, 7, 29)
REPORT_ROOT = WORKSPACE / "project_custom" / "project_custom" / "report"


def _row(**kwargs):
	defaults = {
		"name": "NT-1",
		"status": "Working",
		"priority": "High",
		"assigned_to": "emp@example.com",
		"department": "Sales",
		"project": "PROJ-1",
		"due_date": "2026-07-20",
		"is_overdue": 1,
		"creation": "2026-07-01 09:00:00",
		"completed_on": None,
		"modified": "2026-07-28 10:00:00",
	}
	defaults.update(kwargs)
	return defaults


class TestPeriodGeneration(unittest.TestCase):
	def test_week_start_monday(self):
		# 2026-07-29 is Wednesday → week starts 2026-07-27
		self.assertEqual(week_start_monday(date(2026, 7, 29)), date(2026, 7, 27))
		self.assertEqual(week_start_monday(date(2026, 7, 27)), date(2026, 7, 27))

	def test_weekly_period_generation_and_partial(self):
		# Wednesday to next Tuesday → two partial weeks
		periods = generate_week_periods(date(2026, 7, 1), date(2026, 7, 14))
		self.assertEqual(periods[0]["start"], date(2026, 6, 29))  # Mon before Jul 1
		self.assertEqual(periods[0]["end"], date(2026, 7, 5))
		self.assertEqual(periods[-1]["start"], date(2026, 7, 13))
		self.assertEqual(periods[-1]["end"], date(2026, 7, 19))
		self.assertIn("–", periods[0]["label"])

	def test_monthly_period_generation_and_partial(self):
		periods = generate_month_periods(date(2026, 6, 15), date(2026, 8, 10))
		self.assertEqual([p["label"] for p in periods], ["June 2026", "July 2026", "August 2026"])
		self.assertEqual(periods[0]["start"], date(2026, 6, 1))
		self.assertEqual(periods[0]["end"], date(2026, 6, 30))
		self.assertEqual(periods[2]["end"], date(2026, 8, 31))

	def test_empty_weekly_periods_have_zeros(self):
		with patch(
			"project_custom.nave_task_script_reports.get_task_rows",
			return_value=[],
		):
			_columns, data, *_rest = execute_weekly_task_summary_report(
				{"from_date": "2026-07-01", "to_date": "2026-07-14"},
				user="mgr@example.com",
				today=TODAY,
			)
		self.assertGreaterEqual(len(data), 2)
		for row in data:
			self.assertEqual(row["tasks_created"], 0)
			self.assertEqual(row["completed_closed_total"], 0)
			self.assertEqual(row["completion_pct"], 0.0)

	def test_empty_monthly_periods_have_zeros(self):
		with patch(
			"project_custom.nave_task_script_reports.get_task_rows",
			return_value=[],
		):
			_columns, data, *_rest = execute_monthly_task_summary_report(
				{"from_date": "2026-06-01", "to_date": "2026-07-31"},
				user="mgr@example.com",
				today=TODAY,
			)
		self.assertEqual(len(data), 2)
		self.assertEqual(data[0]["month"], "June 2026")
		self.assertEqual(data[1]["month"], "July 2026")
		self.assertEqual(data[0]["tasks_created"], 0)


class TestDateValidation(unittest.TestCase):
	def test_invalid_date_range_rejected(self):
		with self.assertRaises(Exception) as ctx:
			validate_summary_date_range(date(2026, 7, 29), date(2026, 7, 1))
		self.assertIn("From Date cannot be after To Date", str(ctx.exception))

	def test_more_than_five_years_rejected(self):
		start = date(2020, 1, 1)
		end = start + timedelta(days=MAX_SUMMARY_RANGE_DAYS + 1)
		with self.assertRaises(Exception) as ctx:
			validate_summary_date_range(start, end)
		self.assertIn("5 years", str(ctx.exception))


class TestWeeklyMetrics(unittest.TestCase):
	def setUp(self):
		import frappe

		frappe.get_roles = lambda user=None: ["NAVE Task Manager"]

	def test_weekly_created_completed_closed_on_time_late_pct_avgs(self):
		# Week of 2026-07-27 (Mon) – 2026-08-02 (Sun); TODAY mid-week
		rows = [
			_row(
				name="C1",
				status="Completed",
				creation="2026-07-28 09:00:00",
				completed_on="2026-07-28 18:00:00",
				due_date="2026-07-30",
			),
			_row(
				name="Z1",
				status="Closed",
				creation="2026-07-27 09:00:00",
				completed_on="2026-07-29 12:00:00",
				due_date="2026-07-28",
			),
			_row(
				name="A1",
				status="Working",
				creation="2026-07-27 09:00:00",
				completed_on=None,
				due_date="2026-07-20",
				is_overdue=1,
			),
			# Outside range — created earlier July, should not count as created in this week
			_row(
				name="OLD",
				status="Open",
				creation="2026-07-01 09:00:00",
				due_date="2026-08-01",
				is_overdue=0,
			),
			# Outside activity window (after to_date)
			_row(
				name="FUTURE",
				status="Open",
				creation="2026-08-01 09:00:00",
				due_date="2026-08-10",
				is_overdue=0,
			),
		]
		with patch(
			"project_custom.nave_task_script_reports.get_task_rows",
			return_value=rows,
		) as rows_fn:
			columns, data, _c, _m, summary = execute_weekly_task_summary_report(
				{"from_date": "2026-07-27", "to_date": "2026-07-29"},
				user="mgr@example.com",
				today=TODAY,
			)

		# Fetch drops from_date, keeps to_date
		self.assertNotIn("from_date", rows_fn.call_args.args[0])
		self.assertEqual(rows_fn.call_args.args[0].get("to_date"), "2026-07-29")

		# One week overlapping
		self.assertEqual(len(data), 1)
		row = data[0]
		self.assertEqual(row["tasks_created"], 3)  # C1, Z1, A1 — not OLD (outside week activity? OLD is Jul 1, outside from_date)
		# from_date is Jul 27, so OLD created Jul 1 not in activity window
		self.assertEqual(row["completed"], 1)
		self.assertEqual(row["closed"], 1)
		self.assertEqual(row["completed_closed_total"], 2)
		self.assertEqual(row["on_time_completed"], 1)  # C1
		self.assertEqual(row["late_completed"], 1)  # Z1
		self.assertEqual(row["completion_pct"], 66.7)  # 2/3
		# C1: 0 completion days; Z1: 2 days → avg 1.0
		self.assertEqual(row["avg_completion_days"], 1.0)
		# C1 delay 0; Z1 delay 1 → avg 0.5
		self.assertEqual(row["avg_delay_days"], 0.5)

		# Active at end (current status): A1 + OLD (created before end), not FUTURE (creation after to_date still in mock rows)
		# FUTURE created Aug 1 > effective_end Jul 29 → excluded
		# C1/Z1 completed — not active
		self.assertEqual(row["active_at_end"], 2)  # A1 + OLD
		self.assertEqual(row["overdue_at_end"], 1)  # A1 due Jul 20 < Jul 29

		by_label = {s["label"]: s for s in summary}
		self.assertEqual(by_label["Total Created"]["value"], 3)
		self.assertEqual(by_label["Total Completed/Closed"]["value"], 2)
		self.assertEqual(by_label["Active"]["value"], 2)
		self.assertEqual(by_label["Overdue"]["value"], 1)
		self.assertEqual(by_label["On-Time"]["value"], 1)
		self.assertEqual(by_label["Late"]["value"], 1)
		self.assertEqual(by_label["Overall Completion %"]["value"], 66.7)

		self.assertTrue(any(c["fieldname"] == "week" for c in columns))
		self.assertTrue(any(c["fieldname"] == "avg_delay_days" for c in columns))


class TestMonthlyMetrics(unittest.TestCase):
	def setUp(self):
		import frappe

		frappe.get_roles = lambda user=None: ["NAVE Task Manager"]

	def test_monthly_created_done_pct_avgs(self):
		rows = [
			_row(
				name="J1",
				status="Completed",
				creation="2026-07-05 09:00:00",
				completed_on="2026-07-15 09:00:00",
				due_date="2026-07-20",
			),
			_row(
				name="J2",
				status="Closed",
				creation="2026-07-10 09:00:00",
				completed_on="2026-07-25 09:00:00",
				due_date="2026-07-20",
			),
			_row(
				name="A1",
				status="Pending",
				creation="2026-07-12 09:00:00",
				due_date="2026-07-01",
				is_overdue=1,
			),
			_row(
				name="JUN",
				status="Open",
				creation="2026-06-10 09:00:00",
				due_date="2026-08-01",
				is_overdue=0,
			),
		]
		with patch(
			"project_custom.nave_task_script_reports.get_task_rows",
			return_value=rows,
		):
			columns, data, _c, _m, summary = execute_monthly_task_summary_report(
				{"from_date": "2026-07-01", "to_date": "2026-07-29"},
				user="mgr@example.com",
				today=TODAY,
			)

		self.assertEqual(len(data), 1)
		row = data[0]
		self.assertEqual(row["month"], "July 2026")
		self.assertEqual(row["tasks_created"], 3)
		self.assertEqual(row["completed_closed_total"], 2)
		self.assertEqual(row["completion_pct"], 66.7)
		# completion days: 10 and 15 → avg 12.5
		self.assertEqual(row["avg_completion_days"], 12.5)
		# delay: 0 and 5 → avg 2.5
		self.assertEqual(row["avg_delay_days"], 2.5)
		# Active: A1 + JUN (current), effective end Jul 29
		self.assertEqual(row["active_at_end"], 2)
		self.assertEqual(row["overdue_at_end"], 1)

		by_label = {s["label"]: s for s in summary}
		self.assertEqual(by_label["Total Created"]["value"], 3)
		self.assertEqual(by_label["Average Completion Days"]["value"], 12.5)
		self.assertTrue(any(c["fieldname"] == "month" for c in columns))


class TestPermissionsAndFilters(unittest.TestCase):
	def test_assigned_to_cannot_bypass_permission(self):
		"""Filter is forwarded; get_task_rows remains the permission authority."""
		captured = {}

		def fake_rows(filters, **kwargs):
			captured["filters"] = dict(filters or {})
			captured["user"] = kwargs.get("user")
			# Simulate permission: employee cannot see victim's tasks
			return []

		import frappe

		frappe.get_roles = lambda user=None: ["Employee"]
		with patch(
			"project_custom.nave_task_script_reports.get_task_rows",
			side_effect=fake_rows,
		):
			_columns, data, *_rest = execute_weekly_task_summary_report(
				{
					"from_date": "2026-07-01",
					"to_date": "2026-07-29",
					"assigned_to": "victim@example.com",
				},
				user="emp@example.com",
				today=TODAY,
			)
		self.assertEqual(captured["user"], "emp@example.com")
		self.assertEqual(captured["filters"].get("assigned_to"), "victim@example.com")
		self.assertTrue(all(r["tasks_created"] == 0 for r in data))

	def test_employee_and_manager_access_matrix(self):
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

	def test_date_filters_exclude_outside_activity(self):
		rows = [
			_row(
				name="IN",
				status="Completed",
				creation="2026-07-10 09:00:00",
				completed_on="2026-07-12 09:00:00",
				due_date="2026-07-15",
			),
			_row(
				name="OUT",
				status="Completed",
				creation="2026-06-10 09:00:00",
				completed_on="2026-06-12 09:00:00",
				due_date="2026-06-15",
			),
		]
		with patch(
			"project_custom.nave_task_script_reports.get_task_rows",
			return_value=rows,
		):
			_columns, data, *_rest = execute_monthly_task_summary_report(
				{"from_date": "2026-07-01", "to_date": "2026-07-29"},
				user="mgr@example.com",
				today=TODAY,
			)
		self.assertEqual(data[0]["tasks_created"], 1)
		self.assertEqual(data[0]["completed"], 1)


class TestColumnDefinitions(unittest.TestCase):
	def test_weekly_and_monthly_columns(self):
		weekly = {c["fieldname"] for c in weekly_task_summary_columns()}
		monthly = {c["fieldname"] for c in monthly_task_summary_columns()}
		required = {
			"tasks_created",
			"completed",
			"closed",
			"completed_closed_total",
			"active_at_end",
			"overdue_at_end",
			"on_time_completed",
			"late_completed",
			"completion_pct",
			"avg_completion_days",
			"avg_delay_days",
			"period_start",
			"period_end",
		}
		self.assertTrue(required.issubset(weekly))
		self.assertTrue(required.issubset(monthly))
		self.assertIn("week", weekly)
		self.assertIn("month", monthly)

	def test_report_json_exists(self):
		for folder, name in (
			("nave_weekly_task_summary", "NAVE Weekly Task Summary"),
			("nave_monthly_task_summary", "NAVE Monthly Task Summary"),
		):
			path = REPORT_ROOT / folder / f"{folder}.json"
			payload = json.loads(path.read_text())
			self.assertEqual(payload["name"], name)
			self.assertEqual(payload["report_type"], "Script Report")


if __name__ == "__main__":
	unittest.main()
