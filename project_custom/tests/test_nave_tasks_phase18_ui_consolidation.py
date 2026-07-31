"""Phase 4.5 — Consolidate NAVE Task UI and Desk Home entry tests."""

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

PAGE_DIR = WORKSPACE / "project_custom" / "project_custom" / "page"
NAVE_TASKS_JS = PAGE_DIR / "nave_tasks" / "nave_tasks.js"
NAVE_TASKS_JSON = PAGE_DIR / "nave_tasks" / "nave_tasks.json"
DASHBOARD_PAGE_JS = PAGE_DIR / "nave_task_dashboard" / "nave_task_dashboard.js"
DASHBOARD_PAGE_JSON = PAGE_DIR / "nave_task_dashboard" / "nave_task_dashboard.json"
SHARED_UI_JS = WORKSPACE / "project_custom" / "public" / "js" / "nave_task_dashboard_ui.js"
HOOKS = WORKSPACE / "project_custom" / "hooks.py"
DESKTOP_ICON = WORKSPACE / "project_custom" / "desktop_icon" / "nave_tasks.json"
NAVE_HOME_JS = PAGE_DIR / "nave_home" / "nave_home.js"

EXPECTED_APIS = (
	"project_custom.api.nave_task_dashboard.get_task_dashboard_metadata",
	"project_custom.api.nave_task_dashboard.get_task_dashboard_kpi_cards",
	"project_custom.api.nave_task_dashboard.get_task_dashboard_widget",
	"project_custom.api.nave_task_dashboard.get_task_dashboard_chart",
)

TASK_VIEW_APIS = (
	"project_custom.api.nave_task.get_my_tasks",
	"project_custom.api.nave_task.get_tasks_created_by_me",
	"project_custom.api.nave_task.get_all_tasks",
	"project_custom.api.nave_task.get_overdue_tasks",
	"project_custom.api.nave_task.get_recurring_tasks",
	"project_custom.api.nave_task.get_task_updates_list",
)


class TestSingleNavigationEntry(unittest.TestCase):
	def test_only_one_apps_screen_nave_tasks_entry(self):
		hooks = HOOKS.read_text(encoding="utf-8")
		self.assertEqual(hooks.count('"title": "NAVE Tasks"'), 1)
		self.assertIn('"/desk/nave-tasks"', hooks)
		# add_to_apps_screen must not point at the legacy dashboard page.
		apps_block = hooks.split("add_to_apps_screen")[1].split("website_redirects")[0]
		self.assertNotIn("nave-task-dashboard", apps_block)

	def test_desktop_icon_is_nave_tasks_only(self):
		self.assertTrue(DESKTOP_ICON.exists())
		icon = json.loads(DESKTOP_ICON.read_text(encoding="utf-8"))
		self.assertEqual(icon["doctype"], "Desktop Icon")
		self.assertEqual(icon["label"], "NAVE Tasks")
		self.assertEqual(icon["link"], "/desk/nave-tasks")
		self.assertEqual(icon["app"], "project_custom")
		self.assertEqual(icon["standard"], 1)
		self.assertEqual(icon["hidden"], 0)

	def test_standalone_dashboard_not_in_desktop_icon_folder(self):
		folder = WORKSPACE / "project_custom" / "desktop_icon"
		names = {p.name for p in folder.glob("*.json")}
		self.assertEqual(names, {"nave_tasks.json"})
		for path in folder.glob("*.json"):
			doc = json.loads(path.read_text(encoding="utf-8"))
			self.assertNotEqual(doc.get("label"), "NAVE Task Dashboard")
			self.assertNotIn("nave-task-dashboard", str(doc.get("link") or ""))


class TestDashboardConsolidation(unittest.TestCase):
	def test_shared_renderer_exists(self):
		self.assertTrue(SHARED_UI_JS.exists())
		js = SHARED_UI_JS.read_text(encoding="utf-8")
		self.assertIn("frappe.project_custom.mount_nave_task_dashboard", js)
		for method in EXPECTED_APIS:
			self.assertIn(method, js)

	def test_nave_tasks_dashboard_tab_uses_shared_renderer(self):
		js = NAVE_TASKS_JS.read_text(encoding="utf-8")
		self.assertIn('id: "dashboard"', js)
		self.assertIn("mount_nave_task_dashboard", js)
		self.assertIn("embedded: true", js)
		self.assertIn("dashboard_controller", js)

	def test_hooks_include_shared_dashboard_ui(self):
		hooks = HOOKS.read_text(encoding="utf-8")
		self.assertIn("/assets/project_custom/js/nave_task_dashboard_ui.js", hooks)

	def test_standalone_page_redirects_to_nave_tasks(self):
		js = DASHBOARD_PAGE_JS.read_text(encoding="utf-8")
		self.assertIn('frappe.pages["nave-task-dashboard"].on_page_load', js)
		self.assertIn('frappe.set_route("nave-tasks")', js)
		self.assertNotIn("mount_nave_task_dashboard", js)
		self.assertNotIn("get_task_dashboard_kpi_cards", js)


class TestTaskTabsStillWired(unittest.TestCase):
	def test_task_view_apis_still_referenced(self):
		js = NAVE_TASKS_JS.read_text(encoding="utf-8")
		for method in TASK_VIEW_APIS:
			self.assertIn(method, js)
		for view_id in (
			"my_tasks",
			"created_by_me",
			"all_tasks",
			"overdue_tasks",
			"recurring_tasks",
			"task_updates",
		):
			self.assertIn(f'id: "{view_id}"', js)

	def test_legacy_dashboard_counts_api_string_retained(self):
		# Existing Phase 2 contract — keep API string in VIEW_API map.
		js = NAVE_TASKS_JS.read_text(encoding="utf-8")
		self.assertIn("get_dashboard_counts", js)


class TestDeskHomeIconConfig(unittest.TestCase):
	def test_supported_icon_clipboard_check(self):
		icon = json.loads(DESKTOP_ICON.read_text(encoding="utf-8"))
		self.assertEqual(icon.get("icon"), "clipboard-check")
		self.assertTrue(icon.get("logo_url", "").startswith("/assets/project_custom/"))

	def test_authorized_roles_on_desktop_icon(self):
		icon = json.loads(DESKTOP_ICON.read_text(encoding="utf-8"))
		roles = {row["role"] for row in icon.get("roles") or []}
		self.assertEqual(
			roles,
			{
				"Employee",
				"NAVE Task Manager",
				"NAVE Task Director",
				"System Manager",
			},
		)

	def test_nave_home_lists_nave_tasks_first(self):
		js = NAVE_HOME_JS.read_text(encoding="utf-8")
		self.assertIn('title: "NAVE Tasks"', js)
		self.assertIn('route: "/desk/nave-tasks"', js)
		# First card in the cards array should be NAVE Tasks.
		idx_cards = js.find("const cards = [")
		idx_nave = js.find('title: "NAVE Tasks"', idx_cards)
		idx_sales = js.find('title: "Sales"', idx_cards)
		self.assertGreater(idx_nave, idx_cards)
		self.assertGreater(idx_sales, idx_nave)


class TestApisUnchangedAndPermissions(unittest.TestCase):
	def test_dashboard_api_methods_unchanged(self):
		from project_custom.api import nave_task_dashboard as api

		for name in (
			"get_task_dashboard_metadata",
			"get_task_dashboard_kpi_cards",
			"get_task_dashboard_widget",
			"get_task_dashboard_chart",
			"get_task_dashboard_summary",
		):
			self.assertTrue(callable(getattr(api, name, None)), name)

	def test_unauthorized_guest_blocked(self):
		import frappe
		from project_custom.api import nave_task_dashboard as api
		from project_custom.nave_task_utils import user_has_nave_task_app_access

		frappe.session.user = "Guest"
		frappe.get_roles = lambda user=None: []
		with self.assertRaises(Exception):
			api.get_task_dashboard_kpi_cards()
		self.assertFalse(user_has_nave_task_app_access("Guest", []))
		frappe.session.user = "emp@example.com"
		frappe.get_roles = lambda user=None: ["Employee"]

	def test_has_app_permission_hook_points_to_gate(self):
		hooks = HOOKS.read_text(encoding="utf-8")
		self.assertIn(
			'"has_permission": "project_custom.api.nave_task.has_app_permission"',
			hooks,
		)
		from project_custom.nave_task_utils import user_has_nave_task_app_access

		self.assertFalse(user_has_nave_task_app_access("Guest", ["Employee"]))
		self.assertTrue(user_has_nave_task_app_access("emp@example.com", ["Employee"]))
		self.assertFalse(user_has_nave_task_app_access("x@example.com", ["Purchase User"]))

class TestNoCoreModification(unittest.TestCase):
	def test_no_frappe_or_erpnext_paths_in_changed_area(self):
		# Contract: consolidation assets live only under project_custom.
		self.assertTrue(SHARED_UI_JS.is_relative_to(WORKSPACE / "project_custom"))
		self.assertTrue(DESKTOP_ICON.is_relative_to(WORKSPACE / "project_custom"))
		hooks = HOOKS.read_text(encoding="utf-8")
		self.assertNotIn("apps/frappe", hooks)
		self.assertNotIn("apps/erpnext", hooks)

	def test_page_routes_unchanged(self):
		tasks = json.loads(NAVE_TASKS_JSON.read_text(encoding="utf-8"))
		dash = json.loads(DASHBOARD_PAGE_JSON.read_text(encoding="utf-8"))
		self.assertEqual(tasks["name"], "nave-tasks")
		self.assertEqual(dash["name"], "nave-task-dashboard")


if __name__ == "__main__":
	unittest.main()
