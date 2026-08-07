"""Phase 25 — permanent legacy page removal + real drilldowns + layout."""

from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[2]
if str(WORKSPACE) not in sys.path:
	sys.path.insert(0, str(WORKSPACE))

PAGE_DIR = WORKSPACE / "project_custom" / "project_custom" / "page"
LEGACY_DIR = PAGE_DIR / "nave_task_dashboard"
NAVE_TASKS_JS = PAGE_DIR / "nave_tasks" / "nave_tasks.js"
CF_DASH_JS = PAGE_DIR / "customer_feedback_dashboard" / "customer_feedback_dashboard.js"
NTD_UI = WORKSPACE / "project_custom" / "public" / "js" / "nave_task_dashboard_ui.js"
NAVE_CSS = WORKSPACE / "project_custom" / "public" / "css" / "nave_tasks.css"
HOOKS = WORKSPACE / "project_custom" / "hooks.py"
PATCHES = WORKSPACE / "project_custom" / "patches.txt"
PATCH = (
	WORKSPACE
	/ "project_custom"
	/ "patches"
	/ "v1_7"
	/ "delete_nave_task_dashboard_page.py"
)
REPORT_DIR = WORKSPACE / "project_custom" / "project_custom" / "report"
STALE_PAGE_DIR = WORKSPACE / "project_custom" / "page"


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


class TestLegacyPageGone(unittest.TestCase):
	def test_source_removed(self):
		self.assertFalse((LEGACY_DIR / "nave_task_dashboard.json").exists())
		self.assertFalse((LEGACY_DIR / "nave_task_dashboard.js").exists())

	def test_patch_registered(self):
		self.assertTrue(PATCH.exists())
		self.assertIn(
			"project_custom.patches.v1_7.delete_nave_task_dashboard_page",
			PATCHES.read_text(encoding="utf-8"),
		)
		text = PATCH.read_text(encoding="utf-8")
		self.assertIn("nave-task-dashboard", text)
		self.assertIn("delete_doc", text)
		# Must not delete the consolidated page.
		self.assertNotRegex(text, r'delete_doc\(\s*"Page"\s*,\s*"nave-tasks"')

	def test_hooks_no_legacy_page_reference(self):
		hooks = HOOKS.read_text(encoding="utf-8")
		self.assertNotIn("nave-task-dashboard", hooks)


class TestNaveKpiDrilldown(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		cls.js = NTD_UI.read_text(encoding="utf-8")
		cls.reports = _report_names()

	def test_status_kpis_route_to_list(self):
		for status in ("Open", "Working", "Pending", "Completed", "Closed"):
			self.assertIn(f'status: "{status}"', self.js)
		self.assertIn('doctype: "NAVE Task"', self.js)
		self.assertIn('frappe.set_route("List", nav.doctype)', self.js)
		self.assertIn("frappe.route_options = filters", self.js)

	def test_due_and_priority_list_filters(self):
		self.assertIn("due_date: frappe.datetime.get_today()", self.js)
		self.assertIn("frappe.datetime.add_days(frappe.datetime.get_today(), 1)", self.js)
		self.assertIn('priority: "High"', self.js)
		self.assertIn("completed_on:", self.js)

	def test_completed_today_includes_completed_and_closed(self):
		# Backend KPI counts Completed + Closed finished today — drilldown must match.
		self.assertIn('status: ["in", ["Completed", "Closed"]]', self.js)
		nav_start = self.js.find("const KPI_NAV = {")
		self.assertGreater(nav_start, 0)
		block_start = self.js.find("completed_today:", nav_start)
		self.assertGreater(block_start, nav_start)
		block = self.js[block_start : block_start + 450]
		self.assertIn('["in", ["Completed", "Closed"]]', block)
		self.assertIn("completed_on:", block)
		self.assertIn('["between"', block)

	def test_overdue_uses_existing_report(self):
		self.assertIn('report: "NAVE Overdue Tasks"', self.js)
		self.assertIn("NAVE Overdue Tasks", self.reports)
		self.assertIn('frappe.set_route("query-report", nav.report)', self.js)

	def test_report_shortcuts_exist(self):
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

	def test_unmapped_kpis_static(self):
		self.assertIn("total / active", self.js)
		self.assertIn('const clickable = nav ? "is-clickable" : "is-static"', self.js)

	def test_single_delegated_handler(self):
		self.assertEqual(self.js.count('$container.off("click.ntdNav")'), 1)


class TestCustomerFeedbackDrilldown(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		cls.js = CF_DASH_JS.read_text(encoding="utf-8")

	def test_kpi_nav_mappings(self):
		self.assertIn("const KPI_NAV = {", self.js)
		self.assertIn("total_feedback:", self.js)
		self.assertIn("positive_feedback:", self.js)
		self.assertIn("low_rating:", self.js)
		self.assertIn("google_review_pending:", self.js)
		self.assertIn('follow_up_status: "Positive"', self.js)
		self.assertIn('follow_up_status: "Urgent"', self.js)
		self.assertIn('google_review_status: "Pending"', self.js)
		self.assertIn("average_rating", self.js)

	def test_average_rating_not_clickable(self):
		self.assertIn('class="feedback-kpi success is-static"', self.js)
		self.assertIn("average_rating: no meaningful", self.js)

	def test_single_delegated_kpi_handler(self):
		self.assertIn('off("click.feedbackKpi keydown.feedbackKpi")', self.js)
		self.assertIn(".feedback-kpi.is-clickable", self.js)
		self.assertIn('frappe.set_route("List", nav.doctype)', self.js)

	def test_keyboard_activation_reuses_open_kpi_nav(self):
		self.assertIn('on("keydown.feedbackKpi"', self.js)
		self.assertIn('e.key !== "Enter"', self.js)
		self.assertIn('e.key === " "', self.js)
		self.assertIn("preventDefault", self.js)
		# Click and keyboard both call the same open_kpi_nav helper.
		self.assertEqual(self.js.count("open_kpi_nav(KPI_NAV[key])"), 2)
		self.assertEqual(self.js.count("const open_kpi_nav = (nav) =>"), 1)

	def test_clickable_cursor_affordance(self):
		self.assertIn(".feedback-kpi.is-clickable", self.js)
		self.assertIn("cursor: pointer", self.js)


class TestLayoutOverflowContract(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		cls.ui = NTD_UI.read_text(encoding="utf-8")
		cls.css = NAVE_CSS.read_text(encoding="utf-8")

	def test_compact_widget_rows_not_wide_table(self):
		self.assertIn("ntd-task-row", self.ui)
		self.assertIn("ntd-task-list", self.ui)
		self.assertNotIn("ntd-table", self.ui)

	def test_min_width_zero_on_grid_children(self):
		compact = self.ui.replace(" ", "")
		self.assertIn(".ntd-widget-grid>*{min-width:0;}", compact)
		self.assertIn("min-width: 0", self.css)
		self.assertIn(".ntd-widget-grid > *", self.css)

	def test_widget_overflow_contained(self):
		compact = self.ui.replace(" ", "")
		self.assertIn("overflow-x:auto", compact)
		self.assertIn("overflow:hidden", compact)
		self.assertIn("max-height:320px", compact)
		self.assertIn("overflow-wrap:anywhere", compact)

	def test_embedded_hides_duplicate_dashboard_heading(self):
		compact = self.ui.replace(" ", "")
		self.assertIn(".ntd-wrap.ntd-embedded.ntd-headerh2{display:none;}", compact)
		self.assertIn(".ntd-wrap.ntd-embedded .ntd-header h2", self.css)

	def test_single_shared_renderer(self):
		self.assertEqual(
			NTD_UI.read_text(encoding="utf-8").count(
				"frappe.project_custom.mount_nave_task_dashboard = function"
			),
			1,
		)
		self.assertIn("mount_nave_task_dashboard", NAVE_TASKS_JS.read_text(encoding="utf-8"))
		self.assertFalse((STALE_PAGE_DIR / "nave_tasks").exists())
		self.assertFalse((STALE_PAGE_DIR / "nave_task_dashboard").exists())


if __name__ == "__main__":
	unittest.main()
