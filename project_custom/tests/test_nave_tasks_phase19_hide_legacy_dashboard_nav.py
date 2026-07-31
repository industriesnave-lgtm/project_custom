"""Hide legacy NAVE Task Dashboard from sidebar / Awesome Bar (nav-only fix)."""

from __future__ import annotations

import json
import sys
import types
import unittest
from datetime import date, timedelta
from pathlib import Path

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
	frappe.db = types.SimpleNamespace(
		escape=lambda value: f"'{value}'",
		exists=lambda *a, **k: False,
	)
	frappe.get_list = lambda *a, **k: []
	frappe.get_all = lambda *a, **k: []
	frappe.set_user = lambda u: None
	frappe.whitelist = lambda *a, **k: (lambda fn: fn)
	frappe.flags = types.SimpleNamespace(mute_emails=True)
	frappe.local = types.SimpleNamespace()
	import json as _json

	frappe.parse_json = lambda v: _json.loads(v) if isinstance(v, str) else (v or {})
	frappe.get_doc = lambda *a, **k: types.SimpleNamespace(insert=lambda **kw: None)

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

PAGE_DIR = WORKSPACE / "project_custom" / "project_custom" / "page"
DASHBOARD_JSON = PAGE_DIR / "nave_task_dashboard" / "nave_task_dashboard.json"
DASHBOARD_JS = PAGE_DIR / "nave_task_dashboard" / "nave_task_dashboard.js"
NAVE_TASKS_JSON = PAGE_DIR / "nave_tasks" / "nave_tasks.json"
NAVE_TASKS_JS = PAGE_DIR / "nave_tasks" / "nave_tasks.js"
HOOKS = WORKSPACE / "project_custom" / "hooks.py"
REDIRECT_JS = WORKSPACE / "project_custom" / "public" / "js" / "role_dashboard_redirect.js"
DESKTOP_ICON = WORKSPACE / "project_custom" / "desktop_icon" / "nave_tasks.json"

VISIBLE_NAV_ROLES = {
	"Employee",
	"NAVE Task Manager",
	"NAVE Task Director",
	"System Manager",
}


class TestStandaloneHiddenFromNavigation(unittest.TestCase):
	def test_standalone_page_not_assigned_to_visible_roles(self):
		page = json.loads(DASHBOARD_JSON.read_text(encoding="utf-8"))
		roles = {row["role"] for row in page.get("roles") or []}
		self.assertTrue(roles, "empty roles would expose the page to everyone")
		self.assertTrue(roles.isdisjoint(VISIBLE_NAV_ROLES))
		self.assertEqual(roles, {"NAVE Task Internal Redirect"})

	def test_nave_tasks_page_still_visible_to_app_roles(self):
		page = json.loads(NAVE_TASKS_JSON.read_text(encoding="utf-8"))
		roles = {row["role"] for row in page.get("roles") or []}
		self.assertEqual(roles, VISIBLE_NAV_ROLES)

	def test_desktop_icon_only_nave_tasks(self):
		icon = json.loads(DESKTOP_ICON.read_text(encoding="utf-8"))
		self.assertEqual(icon["label"], "NAVE Tasks")
		self.assertEqual(icon["link"], "/desk/nave-tasks")
		self.assertNotIn("nave-task-dashboard", icon["link"])


class TestRedirectPreserved(unittest.TestCase):
	def test_page_js_redirects_to_nave_tasks(self):
		js = DASHBOARD_JS.read_text(encoding="utf-8")
		self.assertIn('frappe.set_route("nave-tasks")', js)
		self.assertIn('frappe.pages["nave-task-dashboard"].on_page_load', js)

	def test_app_include_redirects_legacy_urls(self):
		js = REDIRECT_JS.read_text(encoding="utf-8")
		self.assertIn("nave-task-dashboard", js)
		self.assertIn("/desk/nave-tasks", js)
		self.assertIn("window.location.replace", js)

	def test_website_redirects_configured(self):
		hooks = HOOKS.read_text(encoding="utf-8")
		self.assertIn("website_redirects", hooks)
		self.assertIn("/app/nave-task-dashboard", hooks)
		self.assertIn("/desk/nave-task-dashboard", hooks)
		self.assertIn('"/app/nave-tasks"', hooks)
		self.assertIn('"/desk/nave-tasks"', hooks)

	def test_before_migrate_ensures_sentinel_role(self):
		hooks = HOOKS.read_text(encoding="utf-8")
		self.assertIn('before_migrate = "project_custom.install.before_migrate"', hooks)
		install = (WORKSPACE / "project_custom" / "install.py").read_text(encoding="utf-8")
		self.assertIn('NAVE_TASK_INTERNAL_REDIRECT_ROLE = "NAVE Task Internal Redirect"', install)
		self.assertIn("def before_migrate(", install)
		self.assertIn("def ensure_nave_task_internal_redirect_role(", install)


class TestNaveTasksStillAccessible(unittest.TestCase):
	def test_nave_tasks_route_and_tabs(self):
		page = json.loads(NAVE_TASKS_JSON.read_text(encoding="utf-8"))
		self.assertEqual(page["name"], "nave-tasks")
		js = NAVE_TASKS_JS.read_text(encoding="utf-8")
		for view_id in (
			"dashboard",
			"my_tasks",
			"created_by_me",
			"all_tasks",
			"overdue_tasks",
			"recurring_tasks",
			"task_updates",
		):
			self.assertIn(f'id: "{view_id}"', js)
		self.assertIn("mount_nave_task_dashboard", js)


class TestDashboardApisUnchanged(unittest.TestCase):
	def test_api_methods_still_importable(self):
		from project_custom.api import nave_task_dashboard as api

		for name in (
			"get_task_dashboard_metadata",
			"get_task_dashboard_kpi_cards",
			"get_task_dashboard_widget",
			"get_task_dashboard_chart",
			"get_task_dashboard_summary",
		):
			self.assertTrue(callable(getattr(api, name, None)), name)


if __name__ == "__main__":
	unittest.main()
