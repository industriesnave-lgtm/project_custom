"""FINAL PRODUCTION CLEANUP — route + asset + layout contracts."""

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
NAVE_HOME_JS = PAGE_DIR / "nave_home" / "nave_home.js"
NAVE_TASKS_JS = PAGE_DIR / "nave_tasks" / "nave_tasks.js"
CF_DASH_JS = PAGE_DIR / "customer_feedback_dashboard" / "customer_feedback_dashboard.js"
NTD_UI = WORKSPACE / "project_custom" / "public" / "js" / "nave_task_dashboard_ui.js"
NAVE_CSS = WORKSPACE / "project_custom" / "public" / "css" / "nave_tasks.css"
HOOKS = WORKSPACE / "project_custom" / "hooks.py"
REPORT_DIR = WORKSPACE / "project_custom" / "project_custom" / "report"

# Stale duplicate page tree must not host the production NAVE/CF pages.
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


class TestCustomerFeedbackRoutes(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		cls.home = NAVE_HOME_JS.read_text(encoding="utf-8")
		cls.dash = CF_DASH_JS.read_text(encoding="utf-8")

	def test_home_has_customer_feedback_list_card(self):
		self.assertIn('title: "Customer Feedback"', self.home)
		self.assertIn('route: ["List", "Customer Feedback"]', self.home)
		self.assertIn('href: "/desk/customer-feedback"', self.home)

	def test_home_has_customer_feedback_dashboard_card(self):
		self.assertIn('title: "Customer Feedback Dashboard"', self.home)
		self.assertIn('route: ["customer-feedback-dashboard"]', self.home)
		self.assertIn('href: "/desk/customer-feedback-dashboard"', self.home)

	def test_home_cards_use_set_route(self):
		self.assertIn("frappe.set_route(...card.route)", self.home)
		self.assertIn('.nave-home-card").on("click"', self.home)

	def test_dashboard_links_use_desk_not_app(self):
		self.assertNotIn('href="/app/customer-feedback', self.dash)
		self.assertIn('href="/desk/customer-feedback"', self.dash)
		self.assertIn('href="/desk/customer-feedback-settings"', self.dash)
		self.assertIn('frappe.set_route(...route)', self.dash)
		self.assertIn('frappe.set_route("Form", doctype, name)', self.dash)

	def test_no_dead_app_prefix_feedback_links(self):
		self.assertNotIn("/app/customer-feedback", self.dash)
		self.assertNotIn("/app/customer-feedback", self.home)


class TestNaveTasksRoutes(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		cls.home = NAVE_HOME_JS.read_text(encoding="utf-8")
		cls.tasks = NAVE_TASKS_JS.read_text(encoding="utf-8")
		cls.ui = NTD_UI.read_text(encoding="utf-8")
		cls.reports = _report_names()

	def test_home_nave_tasks_set_route(self):
		self.assertIn('title: "NAVE Tasks"', self.home)
		self.assertIn('route: ["nave-tasks"]', self.home)
		self.assertIn("frappe.set_route(...card.route)", self.home)

	def test_in_app_nav_views_present(self):
		for view_id in (
			"dashboard",
			"my_tasks",
			"created_by_me",
			"all_tasks",
			"overdue_tasks",
			"recurring_tasks",
			"task_updates",
		):
			self.assertIn(f'id: "{view_id}"', self.tasks)

	def test_report_shortcuts_all_valid(self):
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
			self.assertIn(f'report: "{name}"', self.ui)

	def test_unmapped_kpis_stay_static(self):
		self.assertIn('const clickable = nav ? "is-clickable" : "is-static"', self.ui)
		self.assertIn("total / active", self.ui)

	def test_single_dashboard_nav_handler(self):
		self.assertEqual(self.ui.count('$container.off("click.ntdNav")'), 1)
		self.assertIn('frappe.set_route("query-report", nav.report)', self.ui)

	def test_form_links_use_get_form_link(self):
		self.assertIn('frappe.utils.get_form_link("NAVE Task"', self.ui)
		self.assertIn('frappe.utils.get_form_link(', self.tasks)
		self.assertNotIn("/app/nave-task/", self.ui)
		self.assertNotIn("/app/nave-task/", self.tasks)


class TestNaveTasksLayoutAndAssets(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		cls.css = NAVE_CSS.read_text(encoding="utf-8")
		cls.hooks = HOOKS.read_text(encoding="utf-8")
		cls.tasks = NAVE_TASKS_JS.read_text(encoding="utf-8")

	def test_css_included_in_hooks(self):
		self.assertIn("app_include_css", self.hooks)
		self.assertIn("/assets/project_custom/css/nave_tasks.css", self.hooks)

	def test_dashboard_ui_js_still_in_hooks(self):
		self.assertIn("/assets/project_custom/js/nave_task_dashboard_ui.js", self.hooks)
		self.assertIn("/assets/project_custom/js/role_dashboard_redirect.js", self.hooks)

	def test_ensure_styles_and_page_wrap(self):
		self.assertIn("ensure_styles", self.tasks)
		self.assertIn("/assets/project_custom/css/nave_tasks.css", self.tasks)
		self.assertIn("nave-tasks-page-wrap", self.tasks)
		self.assertIn("mark_page_shell", self.tasks)

	def test_layout_contract_selectors(self):
		self.assertIn(".nave-tasks-page-wrap .layout-main-section", self.css)
		self.assertIn("max-width: 1440px", self.css)
		self.assertIn("margin: 0 auto", self.css)
		self.assertIn("--nt-sidebar-width: 240px", self.css)
		self.assertIn("align-items: stretch", self.css)
		self.assertIn("min-height: 88px", self.css)

	def test_no_global_destructive_body_overrides(self):
		# Scoped page wrap only — no bare body/html layout nukes.
		self.assertNotRegex(self.css, r"(?m)^body\s*\{")
		self.assertNotRegex(self.css, r"(?m)^html\s*\{")
		self.assertNotIn(".layout-main-section {", self.css.replace(
			".nave-tasks-page-wrap .layout-main-section {", "SCOPED"
		))


class TestNoDuplicateRouteHandlersOrPages(unittest.TestCase):
	def test_production_pages_only_in_module_tree(self):
		self.assertTrue((PAGE_DIR / "nave_tasks" / "nave_tasks.js").is_file())
		self.assertTrue((PAGE_DIR / "nave_home" / "nave_home.js").is_file())
		self.assertTrue(
			(PAGE_DIR / "customer_feedback_dashboard" / "customer_feedback_dashboard.js").is_file()
		)
		# Stale sibling page tree must not shadow NAVE Tasks / CF.
		self.assertFalse((STALE_PAGE_DIR / "nave_tasks").exists())
		self.assertFalse((STALE_PAGE_DIR / "nave_home").exists())
		self.assertFalse((STALE_PAGE_DIR / "customer_feedback_dashboard").exists())

	def test_single_on_page_load_per_page(self):
		tasks = NAVE_TASKS_JS.read_text(encoding="utf-8")
		home = NAVE_HOME_JS.read_text(encoding="utf-8")
		cf = CF_DASH_JS.read_text(encoding="utf-8")
		self.assertEqual(tasks.count('frappe.pages["nave-tasks"].on_page_load'), 1)
		self.assertEqual(home.count('frappe.pages["nave-home"].on_page_load'), 1)
		self.assertEqual(
			cf.count('frappe.pages["customer-feedback-dashboard"].on_page_load'), 1
		)

	def test_home_dead_feedback_dashboard_title_removed(self):
		home = NAVE_HOME_JS.read_text(encoding="utf-8")
		# Old ambiguous title replaced with explicit dashboard title.
		self.assertNotIn('title: "Feedback Dashboard"', home)


if __name__ == "__main__":
	unittest.main()
