"""Permanent removal of legacy NAVE Task Dashboard Page."""

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
	frappe.delete_doc = lambda *a, **k: None

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
DASHBOARD_DIR = PAGE_DIR / "nave_task_dashboard"
DASHBOARD_JSON = DASHBOARD_DIR / "nave_task_dashboard.json"
DASHBOARD_JS = DASHBOARD_DIR / "nave_task_dashboard.js"
NAVE_TASKS_JSON = PAGE_DIR / "nave_tasks" / "nave_tasks.json"
NAVE_TASKS_JS = PAGE_DIR / "nave_tasks" / "nave_tasks.js"
HOOKS = WORKSPACE / "project_custom" / "hooks.py"
REDIRECT_JS = WORKSPACE / "project_custom" / "public" / "js" / "role_dashboard_redirect.js"
DESKTOP_ICON = WORKSPACE / "project_custom" / "desktop_icon" / "nave_tasks.json"
PATCHES = WORKSPACE / "project_custom" / "patches.txt"
PATCH_FILE = (
	WORKSPACE
	/ "project_custom"
	/ "patches"
	/ "v1_7"
	/ "delete_nave_task_dashboard_page.py"
)
INSTALL = WORKSPACE / "project_custom" / "install.py"

VISIBLE_NAV_ROLES = {
	"Employee",
	"NAVE Task Manager",
	"NAVE Task Director",
	"System Manager",
}


class TestLegacyPagePermanentlyRemoved(unittest.TestCase):
	def test_source_files_deleted(self):
		self.assertFalse(DASHBOARD_JSON.exists())
		self.assertFalse(DASHBOARD_JS.exists())

	def test_patch_deletes_only_legacy_page(self):
		self.assertTrue(PATCH_FILE.exists())
		text = PATCH_FILE.read_text(encoding="utf-8")
		self.assertIn('page_name = "nave-task-dashboard"', text)
		self.assertIn("frappe.delete_doc", text)
		self.assertIn('"Page"', text)
		self.assertNotIn("nave-tasks", text.split("delete_doc")[1] if "delete_doc" in text else "")
		patches = PATCHES.read_text(encoding="utf-8")
		self.assertIn(
			"project_custom.patches.v1_7.delete_nave_task_dashboard_page",
			patches,
		)

	def test_patch_execute_deletes_when_exists(self):
		frappe = _install_fake_frappe()
		deleted = []

		def exists(doctype, name=None, **kwargs):
			if doctype == "Page" and name == "nave-task-dashboard":
				return True
			return False

		def delete_doc(doctype, name, **kwargs):
			deleted.append((doctype, name, kwargs.get("force"), kwargs.get("ignore_permissions")))

		frappe.db.exists = exists
		frappe.delete_doc = delete_doc

		from project_custom.patches.v1_7.delete_nave_task_dashboard_page import execute

		execute()
		self.assertEqual(deleted, [("Page", "nave-task-dashboard", 1, True)])

	def test_no_website_redirects_for_legacy_page(self):
		hooks = HOOKS.read_text(encoding="utf-8")
		self.assertNotIn("nave-task-dashboard", hooks)

	def test_redirect_js_no_longer_keeps_legacy_page_alive(self):
		js = REDIRECT_JS.read_text(encoding="utf-8")
		self.assertNotIn("nave-task-dashboard", js)
		self.assertIn("/desk/nave-home", js)

	def test_sentinel_role_logic_removed_from_install(self):
		install = INSTALL.read_text(encoding="utf-8")
		self.assertNotIn("NAVE Task Internal Redirect", install)
		self.assertNotIn("ensure_nave_task_internal_redirect_role", install)

	def test_bootinfo_still_strips_stale_page_info_until_migrate(self):
		hooks = HOOKS.read_text(encoding="utf-8")
		self.assertIn('extend_bootinfo = "project_custom.boot.extend_bootinfo"', hooks)
		from project_custom.boot import extend_bootinfo

		boot = {
			"page_info": {
				"nave-task-dashboard": {"title": "x"},
				"nave-tasks": {"title": "NAVE Tasks"},
			},
			"allowed_pages": ["nave-task-dashboard", "nave-tasks"],
		}
		extend_bootinfo(boot)
		self.assertNotIn("nave-task-dashboard", boot["page_info"])
		self.assertIn("nave-tasks", boot["page_info"])
		self.assertEqual(boot["allowed_pages"], ["nave-tasks"])


class TestNaveTasksStillAccessible(unittest.TestCase):
	def test_nave_tasks_page_still_visible_to_app_roles(self):
		page = json.loads(NAVE_TASKS_JSON.read_text(encoding="utf-8"))
		roles = {row["role"] for row in page.get("roles") or []}
		self.assertEqual(roles, VISIBLE_NAV_ROLES)

	def test_desktop_icon_only_nave_tasks(self):
		icon = json.loads(DESKTOP_ICON.read_text(encoding="utf-8"))
		self.assertEqual(icon["label"], "NAVE Tasks")
		self.assertEqual(icon["link"], "/desk/nave-tasks")
		self.assertNotIn("nave-task-dashboard", icon["link"])

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


if __name__ == "__main__":
	unittest.main()
