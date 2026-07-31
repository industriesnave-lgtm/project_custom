"""Batch 8A — NAVE Task Dashboard backend foundation tests."""

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
	LIST_EXPOSED_FIELDS,
	MAX_LIST_LIMIT,
	build_dashboard_cards,
	build_dashboard_completion,
	clamp_list_limit,
	get_dashboard_list,
	get_dashboard_metadata,
	get_dashboard_summary,
	normalize_dashboard_filters,
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


class TestAccessGuards(unittest.TestCase):
	def test_guest_and_unauthorized_role(self):
		self.assertFalse(user_has_nave_task_app_access("Guest", ["Employee"]))
		self.assertFalse(
			user_has_nave_task_app_access("sales@example.com", ["Sales User"])
		)
		self.assertTrue(user_has_nave_task_app_access("emp@example.com", ["Employee"]))
		self.assertTrue(user_has_nave_task_app_access("Administrator", []))

	def test_api_requires_access(self):
		import frappe
		from project_custom.api import nave_task_dashboard as api

		frappe.session.user = "Guest"
		frappe.get_roles = lambda user=None: []
		with self.assertRaises(Exception):
			api.get_task_dashboard_summary()

		frappe.session.user = "sales@example.com"
		frappe.get_roles = lambda user=None: ["Sales User"]
		with self.assertRaises(Exception):
			api.get_task_dashboard_metadata()

		frappe.session.user = "emp@example.com"
		frappe.get_roles = lambda user=None: ["Employee"]
		with patch(
			"project_custom.api.nave_task_dashboard.get_dashboard_summary",
			return_value={"ok": True},
		) as summary_fn:
			result = api.get_task_dashboard_summary({"priority": "High"})
		self.assertEqual(result, {"ok": True})
		summary_fn.assert_called_once()


class TestFilterValidation(unittest.TestCase):
	def test_invalid_status_and_priority_rejected(self):
		with self.assertRaises(Exception) as ctx:
			normalize_dashboard_filters({"status": "Nope"})
		self.assertIn("Invalid status", str(ctx.exception))
		with self.assertRaises(Exception) as ctx:
			normalize_dashboard_filters({"priority": "Critical"})
		self.assertIn("Invalid priority", str(ctx.exception))

	def test_invalid_date_ranges_rejected(self):
		with self.assertRaises(Exception) as ctx:
			normalize_dashboard_filters(
				{"from_date": "2026-07-29", "to_date": "2026-07-01"}
			)
		self.assertIn("From Date", str(ctx.exception))
		with self.assertRaises(Exception) as ctx:
			normalize_dashboard_filters(
				{"due_date_from": "2026-08-01", "due_date_to": "2026-07-01"}
			)
		self.assertIn("Due From", str(ctx.exception))

	def test_valid_filters_normalized(self):
		result = normalize_dashboard_filters(
			{
				"assigned_to": " emp@example.com ",
				"status": "Working",
				"priority": "High",
				"from_date": "2026-07-01",
				"to_date": "2026-07-29",
				"due_date_from": "2026-07-20",
				"due_date_to": "2026-07-30",
				"unknown": "ignore",
			}
		)
		self.assertEqual(result["assigned_to"], "emp@example.com")
		self.assertEqual(result["status"], "Working")
		self.assertNotIn("unknown", result)


class TestSummaryMetrics(unittest.TestCase):
	def test_cards_and_completion_counts(self):
		rows = [
			_row(name="O", status="Open", priority="Low", due_date="2026-07-29", is_overdue=0),
			_row(name="W", status="Working", priority="High", due_date="2026-07-30", is_overdue=0),
			_row(name="P", status="Pending", priority="Medium", due_date="2026-07-01", is_overdue=1),
			_row(
				name="C",
				status="Completed",
				priority="High",
				due_date="2026-07-30",
				completed_on="2026-07-29 11:00:00",
				creation="2026-07-19 09:00:00",
				is_overdue=0,
			),
			_row(
				name="Z",
				status="Closed",
				priority="Low",
				due_date="2026-07-25",
				completed_on="2026-07-28 11:00:00",
				creation="2026-07-20 09:00:00",
				is_overdue=0,
			),
			_row(
				name="L",
				status="Completed",
				priority="High",
				due_date="2026-07-10",
				completed_on="2026-07-29 08:00:00",
				creation="2026-07-01 09:00:00",
				is_overdue=0,
			),
		]
		cards = build_dashboard_cards(rows, today=TODAY)
		self.assertEqual(cards["total"], 6)
		self.assertEqual(cards["open"], 1)
		self.assertEqual(cards["working"], 1)
		self.assertEqual(cards["pending"], 1)
		self.assertEqual(cards["completed"], 2)
		self.assertEqual(cards["closed"], 1)
		self.assertEqual(cards["active"], 3)
		self.assertEqual(cards["overdue"], 1)
		self.assertEqual(cards["due_today"], 1)
		self.assertEqual(cards["due_tomorrow"], 1)
		self.assertEqual(cards["high_priority"], 3)
		self.assertEqual(cards["completed_today"], 2)  # C and L

		completion = build_dashboard_completion(rows, today=TODAY)
		self.assertEqual(completion["completed_closed"], 3)
		self.assertEqual(completion["completion_percentage"], 50.0)
		self.assertEqual(completion["on_time"], 1)  # C
		self.assertEqual(completion["late"], 2)  # Z, L
		# C:10, Z:8, L:28 → 15.3
		self.assertEqual(completion["average_completion_days"], 15.3)
		# C:0, Z:3, L:19 → 7.3
		self.assertEqual(completion["average_delay_days"], 7.3)

	def test_summary_uses_one_fetch_and_passes_user(self):
		rows = [_row(status="Open", due_date="2026-08-01", is_overdue=0, priority="Low")]
		with patch(
			"project_custom.nave_task_dashboard.get_task_rows",
			return_value=rows,
		) as rows_fn:
			payload = get_dashboard_summary(
				{"department": "Sales"},
				user="mgr@example.com",
				today=TODAY,
			)
		self.assertEqual(rows_fn.call_args.kwargs["user"], "mgr@example.com")
		self.assertEqual(rows_fn.call_args.args[0].get("department"), "Sales")
		self.assertEqual(payload["cards"]["total"], 1)
		self.assertIn("completion", payload)
		self.assertIn("generated_at", payload)


class TestPermissions(unittest.TestCase):
	def test_employee_and_manager_matrix(self):
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

	def test_assigned_to_filter_cannot_bypass(self):
		captured = {}

		def fake_rows(filters, **kwargs):
			captured["filters"] = dict(filters or {})
			captured["user"] = kwargs.get("user")
			# Permission-aware service returns empty for inaccessible assignee.
			return []

		with patch(
			"project_custom.nave_task_dashboard.get_task_rows",
			side_effect=fake_rows,
		):
			payload = get_dashboard_summary(
				{"assigned_to": "victim@example.com"},
				user="emp@example.com",
				today=TODAY,
			)
		self.assertEqual(captured["user"], "emp@example.com")
		self.assertEqual(captured["filters"].get("assigned_to"), "victim@example.com")
		self.assertEqual(payload["cards"]["total"], 0)


class TestDashboardLists(unittest.TestCase):
	def test_unsupported_list_type_and_limits(self):
		self.assertEqual(clamp_list_limit(None), 10)
		self.assertEqual(clamp_list_limit(100), MAX_LIST_LIMIT)
		self.assertEqual(clamp_list_limit(0), 10)
		self.assertEqual(clamp_list_limit("abc"), 10)
		with self.assertRaises(Exception):
			get_dashboard_list("nope", user="emp@example.com", today=TODAY)

	def test_list_types_pass_filters_and_expose_fields(self):
		cases = {
			"overdue": {"status"},
			"due_today": {"status", "due_date_from", "due_date_to"},
			"due_tomorrow": {"status", "due_date_from", "due_date_to"},
			"high_priority": {"priority"},
			"recently_updated": set(),
			"completed_today": {"status", "completed_from", "completed_to"},
		}
		for list_type, expected_keys in cases.items():
			captured = {}

			def fake_rows(filters, **kwargs):
				captured["filters"] = dict(filters or {})
				captured["limit"] = kwargs.get("limit_page_length")
				captured["user"] = kwargs.get("user")
				return [
					_row(
						name=f"NT-{list_type}",
						status="Working" if list_type != "completed_today" else "Completed",
						completed_on="2026-07-29 12:00:00",
						modified="2026-07-29 15:00:00",
						due_date="2026-07-20",
					)
				]

			with patch(
				"project_custom.nave_task_dashboard.get_task_rows",
				side_effect=fake_rows,
			):
				payload = get_dashboard_list(
					list_type,
					{"department": "Sales"},
					limit=5,
					user="mgr@example.com",
					today=TODAY,
				)
			self.assertEqual(payload["limit"], 5)
			self.assertEqual(captured["user"], "mgr@example.com")
			self.assertEqual(captured["limit"], 5)
			for key in expected_keys:
				self.assertIn(key, captured["filters"])
			row = payload["data"][0]
			self.assertEqual(set(row.keys()), set(LIST_EXPOSED_FIELDS))
			self.assertNotIn("description", row)
			self.assertNotIn("completion_attachment", row)

	def test_recently_updated_and_completed_today_ordering(self):
		rows = [
			_row(name="A", modified="2026-07-27 10:00:00", completed_on="2026-07-29 09:00:00", status="Completed"),
			_row(name="B", modified="2026-07-29 18:00:00", completed_on="2026-07-29 18:00:00", status="Completed"),
			_row(name="C", modified="2026-07-28 10:00:00", completed_on="2026-07-29 12:00:00", status="Closed"),
		]
		with patch(
			"project_custom.nave_task_dashboard.get_task_rows",
			return_value=list(rows),
		):
			recent = get_dashboard_list(
				"recently_updated", limit=10, user="mgr@example.com", today=TODAY
			)
			done = get_dashboard_list(
				"completed_today", limit=10, user="mgr@example.com", today=TODAY
			)
		self.assertEqual([r["name"] for r in recent["data"]], ["B", "C", "A"])
		self.assertEqual([r["name"] for r in done["data"]], ["B", "C", "A"])


class TestMetadataAndConsistency(unittest.TestCase):
	def test_metadata_safe_surface(self):
		import frappe

		frappe.get_roles = lambda user=None: ["NAVE Task Manager"]
		meta = get_dashboard_metadata(user="mgr@example.com", today=TODAY)
		self.assertEqual(meta["current_user"], "mgr@example.com")
		self.assertTrue(meta["manager_level_access"])
		self.assertEqual(meta["max_list_limit"], 50)
		self.assertNotIn("employees", meta)
		self.assertNotIn("departments", meta)
		self.assertNotIn("permission_sql", meta)
		self.assertIn("Open", meta["statuses"])
		self.assertIn("High", meta["priorities"])

	def test_dashboard_matches_report_summary_helpers(self):
		from project_custom.nave_task_reporting import build_summary_from_rows

		rows = [
			_row(status="Open", due_date="2026-07-29", is_overdue=0, priority="High"),
			_row(status="Working", due_date="2026-07-01", is_overdue=1, priority="Low"),
			_row(status="Completed", due_date="2026-07-20", is_overdue=0, priority="High", completed_on="2026-07-18"),
		]
		report = build_summary_from_rows(rows, today=TODAY)
		cards = build_dashboard_cards(rows, today=TODAY)
		self.assertEqual(cards["total"], report["total"])
		self.assertEqual(cards["open"], report["open"])
		self.assertEqual(cards["working"], report["working"])
		self.assertEqual(cards["overdue"], report["overdue"])
		self.assertEqual(cards["due_today"], report["due_today"])
		self.assertEqual(cards["high_priority"], report["high_priority"])


if __name__ == "__main__":
	unittest.main()
