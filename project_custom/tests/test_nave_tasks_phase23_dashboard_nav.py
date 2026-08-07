"""Dashboard navigation + layout contract tests (NAVE Tasks + Sales)."""

from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[2]
if str(WORKSPACE) not in sys.path:
	sys.path.insert(0, str(WORKSPACE))

NTD_UI = WORKSPACE / "project_custom" / "public" / "js" / "nave_task_dashboard_ui.js"
NAVE_TASKS_JS = (
	WORKSPACE
	/ "project_custom"
	/ "project_custom"
	/ "page"
	/ "nave_tasks"
	/ "nave_tasks.js"
)
SALES_JS = (
	WORKSPACE
	/ "project_custom"
	/ "project_custom"
	/ "page"
	/ "nave_sales_dashboard"
	/ "nave_sales_dashboard.js"
)
REPORT_DIR = WORKSPACE / "project_custom" / "project_custom" / "report"


def _report_names():
	names = set()
	for path in REPORT_DIR.rglob("*.json"):
		try:
			doc = json.loads(path.read_text(encoding="utf-8"))
		except Exception:
			continue
		if doc.get("doctype") == "Report" and doc.get("report_name"):
			names.add(doc["report_name"])
	return names


class TestNaveDashboardCardRoutes(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		cls.js = NTD_UI.read_text(encoding="utf-8")
		cls.reports = _report_names()

	def test_kpi_nav_maps_valid_reports_or_lists(self):
		self.assertIn("const KPI_NAV = {", self.js)
		self.assertIn('report: "NAVE Overdue Tasks"', self.js)
		self.assertIn('doctype: "NAVE Task"', self.js)
		self.assertIn('status: "Open"', self.js)
		self.assertIn("NAVE Overdue Tasks", self.reports)
		self.assertIn('frappe.set_route("List", nav.doctype)', self.js)

	def test_total_and_active_not_forced_clickable(self):
		# Ambiguous KPIs stay without KPI_NAV entries (comment documents why).
		self.assertIn("total / active", self.js)
		# Clickable class only applied when nav exists.
		self.assertIn('const clickable = nav ? "is-clickable" : "is-static"', self.js)

	def test_report_shortcuts_use_existing_report_names(self):
		required = [
			"NAVE My Tasks",
			"NAVE Overdue Tasks",
			"NAVE Completed Task Report",
			"NAVE Department Task Report",
			"NAVE Project Task Report",
			"NAVE Employee Performance Report",
			"NAVE Weekly Task Summary",
			"NAVE Monthly Task Summary",
		]
		for name in required:
			self.assertIn(name, self.reports)
			self.assertIn(f'report: "{name}"', self.js)

	def test_uses_frappe_set_route_query_report(self):
		self.assertIn('frappe.set_route("query-report", nav.report)', self.js)

	def test_single_delegated_nav_handler(self):
		self.assertIn('click.ntdNav', self.js)
		self.assertEqual(self.js.count('$container.off("click.ntdNav")'), 1)


class TestNaveDashboardParentWiring(unittest.TestCase):
	def test_embedded_mount_still_wires_shared_renderer(self):
		js = NAVE_TASKS_JS.read_text(encoding="utf-8")
		self.assertIn("mount_nave_task_dashboard", js)
		self.assertIn("embedded: true", js)
		self.assertIn('frappe.set_route("query-report"', NTD_UI.read_text(encoding="utf-8"))
		self.assertIn('frappe.set_route("List", nav.doctype)', NTD_UI.read_text(encoding="utf-8"))


class TestSalesDashboardCardRoutes(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		cls.js = SALES_JS.read_text(encoding="utf-8")

	def test_kpi_cards_route_to_list_doctypes(self):
		self.assertIn('frappe.set_route("List", nav.doctype)', self.js)
		self.assertIn('doctype: "Sales Invoice"', self.js)
		self.assertIn('doctype: "Sales Order"', self.js)
		for key in (
			"today_sales",
			"month_sales",
			"pending_orders",
			"pending_collection",
			"overdue_amount",
			"credit_note_amount",
		):
			self.assertIn(key, self.js)

	def test_clickable_only_when_mapped(self):
		self.assertIn('const clickable = KPI_NAV[key] ? "is-clickable" : "is-static"', self.js)
		self.assertIn("click.naveSalesKpi", self.js)

	def test_no_hardcoded_invalid_report_routes(self):
		self.assertNotIn('query-report", "Sales', self.js)
		self.assertIn("frappe.route_options = filters", self.js)


class TestDashboardLayoutContract(unittest.TestCase):
	def test_nave_equal_height_kpi_grid(self):
		js = NTD_UI.read_text(encoding="utf-8")
		self.assertIn("align-items:stretch", js.replace(" ", ""))
		self.assertIn("min-height:88px", js.replace(" ", ""))
		self.assertIn(".ntd-embedded", js)
		self.assertIn(".ntd-shortcut-grid", js)

	def test_sales_equal_height_kpi_grid(self):
		js = SALES_JS.read_text(encoding="utf-8")
		self.assertIn("align-items: stretch", js)
		self.assertIn("min-height: 104px", js)
		self.assertIn("height: 100%", js)


class TestReportJsonIntegrity(unittest.TestCase):
	def test_all_shortcut_reports_exist_as_files(self):
		names = _report_names()
		self.assertGreaterEqual(len(names), 8)
		self.assertTrue(any("My Tasks" in n for n in names))


if __name__ == "__main__":
	unittest.main()
