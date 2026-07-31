"""Batch 8B — Dashboard KPI cards & task widget tests."""

from __future__ import annotations

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
			import json

			frappe.parse_json = lambda v: json.loads(v) if isinstance(v, str) else v
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
	import json

	frappe.parse_json = lambda v: json.loads(v) if isinstance(v, str) else (v or {})

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
	KPI_CARD_KEYS,
	MAX_WIDGET_LIMIT,
	SUPPORTED_WIDGET_TYPES,
	WIDGET_ITEM_FIELDS,
	clamp_widget_limit,
	get_dashboard_kpi_cards,
	get_dashboard_list,
	get_dashboard_summary,
	get_dashboard_widget,
)
from project_custom.nave_task_utils import user_has_nave_task_app_access  # noqa: E402


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


class TestKpiCards(unittest.TestCase):
	def test_kpi_card_values_reuse_summary(self):
		rows = [
			_row(name="O", status="Open", due_date="2026-07-29", is_overdue=0, priority="Low"),
			_row(name="W", status="Working", due_date="2026-07-30", is_overdue=0, priority="High"),
			_row(name="P", status="Pending", due_date="2026-07-01", is_overdue=1, priority="Medium"),
			_row(
				name="C",
				status="Completed",
				due_date="2026-07-30",
				completed_on="2026-07-29 11:00:00",
				priority="High",
				is_overdue=0,
			),
			_row(name="Z", status="Closed", due_date="2026-07-20", completed_on="2026-07-28", is_overdue=0, priority="Low"),
		]
		with patch(
			"project_custom.nave_task_dashboard.get_task_rows",
			return_value=rows,
		):
			summary = get_dashboard_summary({}, user="mgr@example.com", today=TODAY)
			kpi = get_dashboard_kpi_cards({}, user="mgr@example.com", today=TODAY)

		for key in KPI_CARD_KEYS:
			self.assertEqual(kpi["cards"][key], summary["cards"][key])
		self.assertEqual(kpi["cards"]["total"], 5)
		self.assertEqual(kpi["cards"]["active"], 3)
		self.assertEqual(kpi["cards"]["completed_today"], 1)
		self.assertEqual([c["key"] for c in kpi["card_list"]], list(KPI_CARD_KEYS))
		self.assertEqual(kpi["card_list"][0]["label"], "Total")

	def test_kpi_reuses_summary_helper_not_second_query_path(self):
		with patch(
			"project_custom.nave_task_dashboard.get_dashboard_summary",
			return_value={
				"filters": {"department": "Sales"},
				"generated_at": "2026-07-29 12:00:00",
				"cards": {k: 0 for k in KPI_CARD_KEYS} | {"total": 2, "active": 1},
				"meta": {"row_count": 2},
			},
		) as summary_fn:
			kpi = get_dashboard_kpi_cards({"department": "Sales"}, user="mgr@example.com")
		summary_fn.assert_called_once()
		self.assertEqual(kpi["cards"]["total"], 2)
		self.assertEqual(kpi["filters"]["department"], "Sales")


class TestWidgets(unittest.TestCase):
	def test_widget_limits(self):
		self.assertEqual(clamp_widget_limit(None), 10)
		self.assertEqual(clamp_widget_limit(100), MAX_WIDGET_LIMIT)
		self.assertEqual(clamp_widget_limit(0), 10)
		self.assertEqual(clamp_widget_limit("x"), 10)

	def test_widget_ordering_and_fields(self):
		rows = [
			_row(name="A", modified="2026-07-27 10:00:00", due_date="2026-07-10", status="Working"),
			_row(name="B", modified="2026-07-29 18:00:00", due_date="2026-07-15", status="Working"),
			_row(name="C", modified="2026-07-28 10:00:00", due_date="2026-07-12", status="Open"),
		]
		with patch(
			"project_custom.nave_task_dashboard.get_task_rows",
			return_value=list(rows),
		):
			recent = get_dashboard_widget(
				"recently_updated",
				limit=10,
				user="mgr@example.com",
				today=TODAY,
			)
			overdue = get_dashboard_widget(
				"overdue",
				limit=10,
				user="mgr@example.com",
				today=TODAY,
			)

		self.assertEqual([i["name"] for i in recent["items"]], ["B", "C", "A"])
		self.assertNotIn("overdue_days", recent["items"][0])
		self.assertEqual([i["name"] for i in overdue["items"]], ["A", "C", "B"])
		item = overdue["items"][0]
		self.assertEqual(set(item.keys()), set(WIDGET_ITEM_FIELDS))
		self.assertNotIn("description", item)
		self.assertNotIn("completed_on", item)
		self.assertNotIn("subject", item)
		self.assertEqual(item["title"], "Task")
		self.assertIsInstance(item["overdue_days"], int)

	def test_empty_widget(self):
		with patch(
			"project_custom.nave_task_dashboard.get_task_rows",
			return_value=[],
		):
			payload = get_dashboard_widget(
				"due_today",
				user="emp@example.com",
				today=TODAY,
			)
		self.assertEqual(payload["items"], [])
		self.assertEqual(payload["count"], 0)
		self.assertEqual(payload["widget"], "due_today")

	def test_unsupported_widget_rejected(self):
		with self.assertRaises(Exception):
			get_dashboard_widget("charts", user="emp@example.com", today=TODAY)

	def test_widget_reuses_list_with_capped_limit(self):
		with patch(
			"project_custom.nave_task_dashboard.get_dashboard_list",
			return_value={
				"list_type": "high_priority",
				"filters": {},
				"limit": 25,
				"generated_at": "t",
				"data": [
					{
						"name": "NT-1",
						"title": "T",
						"subject": "T",
						"assigned_to": "emp@example.com",
						"status": "Working",
						"priority": "High",
						"due_date": "2026-07-20",
						"completed_on": None,
						"project": "P",
						"department": "Sales",
						"modified": "2026-07-28",
						"overdue_days": 9,
					}
				],
			},
		) as list_fn:
			payload = get_dashboard_widget(
				"high_priority",
				limit=100,
				user="mgr@example.com",
				today=TODAY,
			)
		self.assertEqual(list_fn.call_args.kwargs["limit"], MAX_WIDGET_LIMIT)
		self.assertEqual(payload["limit"], MAX_WIDGET_LIMIT)
		self.assertEqual(payload["items"][0]["overdue_days"], 9)

	def test_all_supported_widget_types(self):
		self.assertEqual(
			set(SUPPORTED_WIDGET_TYPES),
			{"due_today", "due_tomorrow", "overdue", "high_priority", "recently_updated"},
		)


class TestPermissionsAndApiStability(unittest.TestCase):
	def test_permission_gate(self):
		self.assertFalse(user_has_nave_task_app_access("Guest", ["Employee"]))
		import frappe
		from project_custom.api import nave_task_dashboard as api

		frappe.session.user = "Guest"
		frappe.get_roles = lambda user=None: []
		with self.assertRaises(Exception):
			api.get_task_dashboard_kpi_cards()
		with self.assertRaises(Exception):
			api.get_task_dashboard_widget("overdue")

		frappe.session.user = "emp@example.com"
		frappe.get_roles = lambda user=None: ["Employee"]
		with patch(
			"project_custom.api.nave_task_dashboard.get_dashboard_kpi_cards",
			return_value={"ok": 1},
		):
			self.assertEqual(api.get_task_dashboard_kpi_cards(), {"ok": 1})

	def test_existing_summary_and_list_apis_unchanged_shape(self):
		rows = [_row(status="Open", due_date="2026-08-01", is_overdue=0, priority="Low")]
		with patch(
			"project_custom.nave_task_dashboard.get_task_rows",
			return_value=rows,
		):
			summary = get_dashboard_summary({}, user="emp@example.com", today=TODAY)
			listing = get_dashboard_list(
				"recently_updated", limit=10, user="emp@example.com", today=TODAY
			)
		self.assertIn("cards", summary)
		self.assertIn("completion", summary)
		self.assertIn("meta", summary)
		self.assertIn("data", listing)
		self.assertEqual(listing["list_type"], "recently_updated")
		# Generic list API still allows up to 50 (8A); widget layer caps at 25.
		self.assertEqual(listing["limit"], 10)


if __name__ == "__main__":
	unittest.main()
