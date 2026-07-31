"""Batch 8C — Dashboard charts & trends backend tests."""

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
		if not hasattr(frappe, "PermissionError"):
			frappe.PermissionError = type("PermissionError", (Exception,), {})
		if not hasattr(frappe, "parse_json"):
			import json as _json

			frappe.parse_json = lambda v: _json.loads(v) if isinstance(v, str) else v
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
	import json as _json

	frappe.parse_json = lambda v: _json.loads(v) if isinstance(v, str) else (v or {})

	utils = types.ModuleType("frappe.utils")
	utils.nowdate = lambda: "2026-07-29"
	utils.now_datetime = lambda: "2026-07-29 12:00:00"
	utils.getdate = lambda d: d if hasattr(d, "year") else date.fromisoformat(str(d)[:10])
	utils.add_days = lambda d, n: (
		date.fromisoformat(str(d)[:10]) + timedelta(days=n)
		if not hasattr(d, "year")
		else d + timedelta(days=n)
	)
	frappe.utils = utils

	sys.modules["frappe"] = frappe
	sys.modules["frappe.utils"] = utils
	sys.modules["frappe.model"] = types.ModuleType("frappe.model")
	doc = types.ModuleType("frappe.model.document")
	doc.Document = type("Document", (), {})
	sys.modules["frappe.model.document"] = doc
	return frappe


_install_fake_frappe()

from project_custom.nave_task_dashboard import (  # noqa: E402
	ALLOWED_PRIORITIES,
	MAX_CHART_GROUPS,
	MAX_WEEKLY_CHART_DAYS,
	STATUS_DISTRIBUTION_LABELS,
	SUPPORTED_CHART_TYPES,
	get_dashboard_chart,
)
from project_custom.nave_task_utils import (  # noqa: E402
	user_can_access_task,
	user_has_nave_task_app_access,
)


TODAY = date(2026, 7, 29)


def _row(**kwargs):
	defaults = {
		"name": "NT-1",
		"subject": "Task",
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


def _by_name(datasets):
	return {d["name"]: d["values"] for d in datasets}


class TestChartAccess(unittest.TestCase):
	def test_guest_and_unauthorized(self):
		self.assertFalse(user_has_nave_task_app_access("Guest", ["Employee"]))
		import frappe
		from project_custom.api import nave_task_dashboard as api

		frappe.session.user = "Guest"
		frappe.get_roles = lambda user=None: []
		with self.assertRaises(Exception):
			api.get_task_dashboard_chart("monthly_trend")

		frappe.session.user = "sales@example.com"
		frappe.get_roles = lambda user=None: ["Sales User"]
		with self.assertRaises(Exception):
			api.get_task_dashboard_chart("status_distribution")

	def test_unsupported_chart_type(self):
		with self.assertRaises(Exception) as ctx:
			get_dashboard_chart("pie_of_secrets", user="emp@example.com", today=TODAY)
		self.assertIn("Unsupported chart type", str(ctx.exception))

	def test_assigned_to_cannot_bypass(self):
		captured = {}

		def fake_rows(filters, **kwargs):
			captured["filters"] = dict(filters or {})
			captured["user"] = kwargs.get("user")
			return []

		with patch(
			"project_custom.nave_task_dashboard.get_task_rows",
			side_effect=fake_rows,
		):
			payload = get_dashboard_chart(
				"status_distribution",
				{"assigned_to": "victim@example.com"},
				user="emp@example.com",
				today=TODAY,
			)
		self.assertEqual(captured["user"], "emp@example.com")
		self.assertEqual(captured["filters"].get("assigned_to"), "victim@example.com")
		self.assertEqual(sum(_by_name(payload["datasets"])["Count"]), 0)

	def test_manager_department_matrix(self):
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


class TestMonthlyWeeklyTrends(unittest.TestCase):
	def test_monthly_continuous_empty_and_values(self):
		rows = [
			_row(
				name="C1",
				status="Completed",
				creation="2026-06-10 09:00:00",
				completed_on="2026-06-15 09:00:00",
				due_date="2026-06-20",
				is_overdue=0,
			),
			_row(
				name="A1",
				status="Working",
				creation="2026-07-05 09:00:00",
				due_date="2026-07-01",
				is_overdue=1,
			),
			_row(
				name="OLD",
				status="Open",
				creation="2026-05-01 09:00:00",
				due_date="2026-08-01",
				is_overdue=0,
			),
		]
		with patch(
			"project_custom.nave_task_dashboard._fetch_period_report_rows",
			return_value=rows,
		):
			payload = get_dashboard_chart(
				"monthly_trend",
				{"from_date": "2026-06-01", "to_date": "2026-07-29"},
				user="mgr@example.com",
				today=TODAY,
			)
		self.assertEqual(payload["labels"], ["June 2026", "July 2026"])
		values = _by_name(payload["datasets"])
		self.assertEqual(values["Created"], [1, 1])  # C1 June, A1 July
		self.assertEqual(values["Completed/Closed"], [1, 0])
		# Active: OLD in both months; A1 only from July
		self.assertEqual(values["Active"], [1, 2])
		self.assertEqual(values["Overdue"], [0, 1])  # A1 in July
		self.assertIn("historical_status", payload["meta"])
		json.dumps(payload)  # serializable

	def test_weekly_continuous_and_empty(self):
		with patch(
			"project_custom.nave_task_dashboard._fetch_period_report_rows",
			return_value=[],
		):
			payload = get_dashboard_chart(
				"weekly_trend",
				{"from_date": "2026-07-01", "to_date": "2026-07-14"},
				user="mgr@example.com",
				today=TODAY,
			)
		self.assertGreaterEqual(len(payload["labels"]), 2)
		for ds in payload["datasets"]:
			self.assertEqual(ds["values"], [0] * len(payload["labels"]))
		self.assertEqual(
			[d["name"] for d in payload["datasets"]],
			["Created", "Completed/Closed", "Overdue", "Active"],
		)

	def test_weekly_over_two_years_rejected(self):
		start = date(2024, 1, 1)
		end = start + timedelta(days=MAX_WEEKLY_CHART_DAYS + 1)
		with self.assertRaises(Exception) as ctx:
			get_dashboard_chart(
				"weekly_trend",
				{"from_date": start.isoformat(), "to_date": end.isoformat()},
				user="mgr@example.com",
				today=TODAY,
			)
		self.assertIn("2 years", str(ctx.exception))

	def test_monthly_over_five_years_rejected(self):
		with self.assertRaises(Exception) as ctx:
			get_dashboard_chart(
				"monthly_trend",
				{"from_date": "2020-01-01", "to_date": "2026-07-29"},
				user="mgr@example.com",
				today=TODAY,
			)
		self.assertIn("5 years", str(ctx.exception))


class TestDistributions(unittest.TestCase):
	def test_status_distribution_counts_and_zeros(self):
		rows = [
			_row(status="Open"),
			_row(status="Open"),
			_row(status="Working"),
			_row(status="Cancelled"),
		]
		with patch(
			"project_custom.nave_task_dashboard.get_task_rows",
			return_value=rows,
		):
			payload = get_dashboard_chart(
				"status_distribution", user="mgr@example.com", today=TODAY
			)
		self.assertEqual(payload["labels"], list(STATUS_DISTRIBUTION_LABELS))
		counts = _by_name(payload["datasets"])["Count"]
		self.assertEqual(counts[0], 2)  # Open
		self.assertEqual(counts[1], 1)  # Working
		self.assertEqual(counts[2], 0)  # Pending
		self.assertEqual(counts[3], 0)  # Completed
		self.assertEqual(counts[4], 0)  # Closed

	def test_priority_order_and_high_excludes_urgent(self):
		rows = [
			_row(priority="Urgent"),
			_row(priority="High"),
			_row(priority="High"),
			_row(priority="Low"),
		]
		with patch(
			"project_custom.nave_task_dashboard.get_task_rows",
			return_value=rows,
		):
			payload = get_dashboard_chart(
				"priority_distribution", user="mgr@example.com", today=TODAY
			)
		self.assertEqual(payload["labels"], list(ALLOWED_PRIORITIES))
		counts = dict(zip(payload["labels"], _by_name(payload["datasets"])["Count"]))
		self.assertEqual(counts["High"], 2)
		self.assertEqual(counts["Urgent"], 1)
		self.assertEqual(counts["Medium"], 0)


class TestPerformanceCharts(unittest.TestCase):
	def test_department_performance_sort_and_values(self):
		dept_data = [
			{
				"department": "Alpha",
				"total": 4,
				"open": 1,
				"working": 0,
				"pending": 0,
				"completed": 2,
				"closed": 1,
				"overdue": 1,
			},
			{
				"department": "Beta",
				"total": 3,
				"open": 2,
				"working": 1,
				"pending": 0,
				"completed": 0,
				"closed": 0,
				"overdue": 2,
			},
			{
				"department": "(No Department)",
				"total": 1,
				"open": 0,
				"working": 0,
				"pending": 1,
				"completed": 0,
				"closed": 0,
				"overdue": 0,
			},
		]
		with patch(
			"project_custom.nave_task_dashboard.execute_department_task_report",
			return_value=([], dept_data, None, None, []),
		):
			payload = get_dashboard_chart(
				"department_performance",
				{"department": "Sales"},
				user="mgr@example.com",
				today=TODAY,
			)
		# Overdue desc: Beta(2), Alpha(1), No Dept(0)
		self.assertEqual(payload["labels"][0], "Beta")
		self.assertEqual(payload["labels"][1], "Alpha")
		values = _by_name(payload["datasets"])
		self.assertEqual(values["Overdue"][0], 2)
		self.assertEqual(values["Active"][0], 3)
		self.assertEqual(values["Completed/Closed"][1], 3)
		self.assertEqual(values["Completion %"][1], 75.0)
		self.assertEqual(
			[d["name"] for d in payload["datasets"]],
			["Total", "Active", "Completed/Closed", "Overdue", "Completion %"],
		)

	def test_department_truncation_metadata(self):
		dept_data = [
			{
				"department": f"D{i:02d}",
				"total": 1,
				"open": 1,
				"working": 0,
				"pending": 0,
				"completed": 0,
				"closed": 0,
				"overdue": i % 5,
			}
			for i in range(30)
		]
		with patch(
			"project_custom.nave_task_dashboard.execute_department_task_report",
			return_value=([], dept_data, None, None, []),
		):
			payload = get_dashboard_chart(
				"department_performance", user="mgr@example.com", today=TODAY
			)
		self.assertTrue(payload["meta"]["truncated"])
		self.assertEqual(payload["meta"]["total_groups"], 30)
		self.assertEqual(payload["meta"]["returned_groups"], MAX_CHART_GROUPS)
		self.assertEqual(len(payload["labels"]), 25)

	def test_project_performance_and_no_project(self):
		proj_data = [
			{
				"project": "PROJ-1",
				"total": 2,
				"open": 1,
				"working": 0,
				"pending": 0,
				"completed": 1,
				"closed": 0,
				"overdue": 1,
				"_empty_project": False,
			},
			{
				"project": None,
				"total": 1,
				"open": 0,
				"working": 1,
				"pending": 0,
				"completed": 0,
				"closed": 0,
				"overdue": 0,
				"_empty_project": True,
			},
		]
		with patch(
			"project_custom.nave_task_dashboard.execute_project_task_report",
			return_value=([], proj_data, None, None, []),
		):
			payload = get_dashboard_chart(
				"project_performance", user="mgr@example.com", today=TODAY
			)
		self.assertEqual(payload["labels"][0], "PROJ-1")
		self.assertIn("(No Project)", payload["labels"])


class TestOverdueTrend(unittest.TestCase):
	def test_overdue_trend_only_current_status_metric(self):
		with patch(
			"project_custom.nave_task_dashboard._fetch_period_report_rows",
			return_value=[
				_row(status="Working", creation="2026-07-01", due_date="2026-07-01", is_overdue=1),
			],
		):
			payload = get_dashboard_chart(
				"overdue_trend",
				{"from_date": "2026-07-01", "to_date": "2026-07-29"},
				user="mgr@example.com",
				today=TODAY,
			)
		self.assertEqual([d["name"] for d in payload["datasets"]], ["Overdue"])
		self.assertNotIn("Newly Overdue", [d["name"] for d in payload["datasets"]])
		self.assertIn("limitation", payload["meta"])
		self.assertEqual(payload["meta"]["interval"], "monthly")

	def test_overdue_trend_weekly_interval(self):
		with patch(
			"project_custom.nave_task_dashboard._fetch_period_report_rows",
			return_value=[],
		):
			payload = get_dashboard_chart(
				"overdue_trend",
				{
					"from_date": "2026-07-01",
					"to_date": "2026-07-14",
					"interval": "weekly",
				},
				user="mgr@example.com",
				today=TODAY,
			)
		self.assertEqual(payload["meta"]["interval"], "weekly")
		self.assertGreaterEqual(len(payload["labels"]), 2)


class TestStructure(unittest.TestCase):
	def test_supported_types_and_serialization(self):
		self.assertEqual(len(SUPPORTED_CHART_TYPES), 7)
		with patch(
			"project_custom.nave_task_dashboard.get_task_rows",
			return_value=[],
		):
			payload = get_dashboard_chart(
				"priority_distribution", user="emp@example.com", today=TODAY
			)
		encoded = json.dumps(payload)
		self.assertIn("chart_type", encoded)
		self.assertIn("datasets", encoded)


if __name__ == "__main__":
	unittest.main()
