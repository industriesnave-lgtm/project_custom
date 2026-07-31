"""Batch 8D — NAVE Task Dashboard UI page contract tests.

Static/unit checks for Desk page config and JS contracts. Does not run a browser.
"""

from __future__ import annotations

import json
import re
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

PAGE_DIR = (
	WORKSPACE
	/ "project_custom"
	/ "project_custom"
	/ "page"
	/ "nave_task_dashboard"
)
PAGE_JSON = PAGE_DIR / "nave_task_dashboard.json"
PAGE_JS = PAGE_DIR / "nave_task_dashboard.js"

EXPECTED_API_METHODS = (
	"project_custom.api.nave_task_dashboard.get_task_dashboard_metadata",
	"project_custom.api.nave_task_dashboard.get_task_dashboard_kpi_cards",
	"project_custom.api.nave_task_dashboard.get_task_dashboard_widget",
	"project_custom.api.nave_task_dashboard.get_task_dashboard_chart",
)

FILTER_KEYS = (
	"from_date",
	"to_date",
	"assigned_to",
	"department",
	"project",
	"priority",
	"status",
)


class TestPageRouteAndConfig(unittest.TestCase):
	def test_page_route_exists(self):
		self.assertTrue(PAGE_JSON.exists(), "Page JSON missing")
		self.assertTrue(PAGE_JS.exists(), "Page JS missing")
		page = json.loads(PAGE_JSON.read_text(encoding="utf-8"))
		self.assertEqual(page["name"], "nave-task-dashboard")
		self.assertEqual(page["page_name"], "nave-task-dashboard")
		self.assertEqual(page["title"], "NAVE Task Dashboard")
		self.assertEqual(page["module"], "Project Custom")
		self.assertEqual(page["standard"], "Yes")

	def test_page_roles_registered(self):
		page = json.loads(PAGE_JSON.read_text(encoding="utf-8"))
		roles = {row["role"] for row in page.get("roles") or []}
		self.assertEqual(
			roles,
			{
				"Employee",
				"NAVE Task Manager",
				"NAVE Task Director",
				"System Manager",
			},
		)

	def test_page_js_registers_route_handler(self):
		js = PAGE_JS.read_text(encoding="utf-8")
		self.assertIn('frappe.pages["nave-task-dashboard"].on_page_load', js)
		self.assertIn("frappe.ui.make_app_page", js)


class TestApiMethodContracts(unittest.TestCase):
	def test_dashboard_api_method_names_referenced(self):
		js = PAGE_JS.read_text(encoding="utf-8")
		for method in EXPECTED_API_METHODS:
			self.assertIn(method, js)

	def test_api_methods_exist_on_module(self):
		from project_custom.api import nave_task_dashboard as api

		for short in (
			"get_task_dashboard_metadata",
			"get_task_dashboard_kpi_cards",
			"get_task_dashboard_widget",
			"get_task_dashboard_chart",
		):
			self.assertTrue(callable(getattr(api, short, None)), short)

	def test_no_direct_db_or_permission_bypass_in_ui(self):
		js = PAGE_JS.read_text(encoding="utf-8")
		self.assertNotIn("frappe.db.", js)
		self.assertNotIn("frappe.get_list(", js)
		self.assertNotIn("frappe.get_all(", js)
		self.assertNotIn("ignore_permissions", js)
		self.assertIn("frappe.call", js)


class TestFilterPayloadAndDates(unittest.TestCase):
	def test_filter_keys_present(self):
		js = PAGE_JS.read_text(encoding="utf-8")
		for key in FILTER_KEYS:
			self.assertIn(f'data-key="{key}"', js) if key in (
				"from_date",
				"to_date",
				"priority",
				"status",
			) else self.assertIn(key, js)

	def test_filter_payload_mapping_contract(self):
		js = PAGE_JS.read_text(encoding="utf-8")
		# Apply/Clear/Refresh controls
		self.assertIn("ntd-apply", js)
		self.assertIn("ntd-clear", js)
		self.assertIn("ntd-refresh", js)
		self.assertIn("read_filters", js)
		self.assertIn("default_filters", js)
		# Metadata drives selects — not hardcoded department/project lists
		self.assertIn("get_task_dashboard_metadata", js)
		self.assertIn("meta.priorities", js)
		self.assertIn("meta.statuses", js)
		self.assertNotIn('"Sales"', js)
		self.assertNotIn('"Engineering"', js)

	def test_invalid_date_range_handling(self):
		js = PAGE_JS.read_text(encoding="utf-8")
		self.assertIn("From Date cannot be after To Date.", js)
		self.assertIn("validate_dates", js)
		self.assertIn("ntd-filter-error", js)

	def test_widget_filters_omit_creation_date_range(self):
		js = PAGE_JS.read_text(encoding="utf-8")
		self.assertIn("widget_filters", js)
		self.assertIn("delete widget_filters.from_date", js)
		self.assertIn("delete widget_filters.to_date", js)


class TestUiStateContracts(unittest.TestCase):
	def test_kpi_zero_values_render_safely(self):
		js = PAGE_JS.read_text(encoding="utf-8")
		self.assertIn("card.value == null ? 0 : card.value", js)
		self.assertIn("get_task_dashboard_kpi_cards", js)
		# No client-side KPI aggregation from task rows / DB
		kpi_section = js.split("render_kpis")[1].split("task_link")[0]
		self.assertNotIn("get_task_rows", kpi_section)
		self.assertNotIn("frappe.db", kpi_section)
		self.assertNotIn("completed_today++", kpi_section)

	def test_empty_widget_and_chart_states(self):
		js = PAGE_JS.read_text(encoding="utf-8")
		self.assertIn("No tasks found", js)
		self.assertIn("No data available", js)

	def test_error_state_handling(self):
		js = PAGE_JS.read_text(encoding="utf-8")
		self.assertIn("ntd-global-error", js)
		self.assertIn("Unable to load KPI cards.", js)
		self.assertIn("Unable to load widget.", js)
		self.assertIn("Unable to load chart.", js)
		self.assertIn("Access denied", js)
		self.assertIn("console.error", js)

	def test_refresh_prevents_overlapping_requests(self):
		js = PAGE_JS.read_text(encoding="utf-8")
		self.assertIn("state.loading", js)
		self.assertIn("request_id", js)
		self.assertIn("if (state.loading)", js)
		self.assertIn('.prop("disabled", !!loading)', js)

	def test_task_links_use_valid_nave_task_routes(self):
		js = PAGE_JS.read_text(encoding="utf-8")
		self.assertIn("/app/nave-task/", js)
		self.assertIn("encodeURIComponent(name", js)
		self.assertNotIn("/app/task/", js)

	def test_truncation_metadata_notice(self):
		js = PAGE_JS.read_text(encoding="utf-8")
		self.assertIn("meta.truncated", js)
		self.assertIn("returned_groups", js)
		self.assertIn("total_groups", js)
		self.assertIn("Showing top", js)

	def test_chart_instances_destroyed_before_rerender(self):
		js = PAGE_JS.read_text(encoding="utf-8")
		self.assertIn("destroy_chart", js)
		self.assertIn("chart_instances", js)
		self.assertIn("frappe.Chart", js)
		self.assertNotIn("chart.js", js.lower())
		self.assertNotIn("highcharts", js.lower())

	def test_required_widgets_and_charts_present(self):
		js = PAGE_JS.read_text(encoding="utf-8")
		for widget in (
			"due_today",
			"due_tomorrow",
			"overdue",
			"high_priority",
			"recently_updated",
		):
			self.assertIn(f'type: "{widget}"', js)
		for chart in (
			"monthly_trend",
			"status_distribution",
			"priority_distribution",
			"department_performance",
			"project_performance",
			"overdue_trend",
		):
			self.assertIn(f'type: "{chart}"', js)

	def test_no_polling_or_realtime(self):
		js = PAGE_JS.read_text(encoding="utf-8")
		self.assertNotIn("setInterval", js)
		self.assertNotIn("frappe.realtime", js)
		self.assertNotIn("socket", js.lower())


class TestBackendPermissionStillAuthoritative(unittest.TestCase):
	def test_guest_blocked_on_dashboard_apis(self):
		import frappe
		from project_custom.api import nave_task_dashboard as api

		frappe.session.user = "Guest"
		frappe.get_roles = lambda user=None: []
		with self.assertRaises(Exception):
			api.get_task_dashboard_metadata()
		with self.assertRaises(Exception):
			api.get_task_dashboard_kpi_cards()
		with self.assertRaises(Exception):
			api.get_task_dashboard_widget("overdue")
		with self.assertRaises(Exception):
			api.get_task_dashboard_chart("monthly_trend")

		frappe.session.user = "emp@example.com"
		frappe.get_roles = lambda user=None: ["Employee"]
		with patch(
			"project_custom.api.nave_task_dashboard.get_dashboard_metadata",
			return_value={"ok": 1},
		):
			self.assertEqual(api.get_task_dashboard_metadata(), {"ok": 1})


class TestJsDoesNotRecalculateBackendMetrics(unittest.TestCase):
	def test_no_overdue_or_kpi_math_helpers(self):
		js = PAGE_JS.read_text(encoding="utf-8")
		# Client must not invent overdue/KPI math — only render API payloads.
		self.assertNotIn("days_overdue", js)
		self.assertNotIn("is_overdue", js)
		self.assertNotIn("completion_pct", js)
		# Chart values come from datasets, not JS aggregation
		self.assertIn("payload.datasets", js)
		self.assertIn("payload.labels", js)


if __name__ == "__main__":
	unittest.main()
