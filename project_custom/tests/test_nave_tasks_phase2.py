"""Phase 2 NAVE Tasks UI helper and integration-mapping tests."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[2]
if str(WORKSPACE) not in sys.path:
	sys.path.insert(0, str(WORKSPACE))

from project_custom.nave_task_ui import (  # noqa: E402
	DASHBOARD_COUNTER_VIEWS,
	VIEW_API_MAP,
	can_show_all_tasks_nav,
	escape_html,
	get_task_action_visibility,
	sort_timeline_chronological,
)
from project_custom.nave_task_utils import to_plain_text  # noqa: E402


class TestViewApiMapping(unittest.TestCase):
	def test_each_functional_view_uses_expected_api(self):
		self.assertEqual(
			VIEW_API_MAP["my_tasks"],
			"project_custom.api.nave_task.get_my_tasks",
		)
		self.assertEqual(
			VIEW_API_MAP["created_by_me"],
			"project_custom.api.nave_task.get_tasks_created_by_me",
		)
		self.assertEqual(
			VIEW_API_MAP["all_tasks"],
			"project_custom.api.nave_task.get_all_tasks",
		)
		self.assertEqual(
			VIEW_API_MAP["overdue_tasks"],
			"project_custom.api.nave_task.get_overdue_tasks",
		)
		self.assertEqual(
			VIEW_API_MAP["task_updates"],
			"project_custom.api.nave_task.get_task_updates_list",
		)
		self.assertEqual(
			VIEW_API_MAP["dashboard"],
			"project_custom.api.nave_task.get_dashboard_counts",
		)
		self.assertEqual(
			VIEW_API_MAP["recurring_tasks"],
			"project_custom.api.nave_task.get_recurring_tasks",
		)

	def test_dashboard_counter_navigation_targets(self):
		self.assertEqual(DASHBOARD_COUNTER_VIEWS["overdue"]["view"], "overdue_tasks")
		self.assertEqual(DASHBOARD_COUNTER_VIEWS["open"]["status"], "Open")
		self.assertEqual(DASHBOARD_COUNTER_VIEWS["completed"]["status"], "Completed")


class TestAllTasksVisibility(unittest.TestCase):
	def test_all_tasks_nav_available_when_logged_in_roles_present(self):
		# Server still scopes rows; nav is available for permission-aware listing.
		self.assertTrue(can_show_all_tasks_nav(is_admin=False, is_manager=False))
		self.assertTrue(can_show_all_tasks_nav(is_admin=True, is_manager=False))


class TestPlainTextAndEscaping(unittest.TestCase):
	def test_plain_text_description_rendering(self):
		self.assertEqual(to_plain_text("<p>Site <b>visit</b></p>"), "Site visit")

	def test_user_content_escaping(self):
		self.assertEqual(
			escape_html('<script>alert("x")</script>'),
			"&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;",
		)


class TestActionButtonVisibility(unittest.TestCase):
	def _task(self, **kwargs):
		base = {
			"assigned_to": "emp@example.com",
			"owner": "creator@example.com",
			"assigned_by": "creator@example.com",
			"department": "Sales",
			"status": "Working",
		}
		base.update(kwargs)
		return base

	def test_assignee_sees_update_not_close(self):
		vis = get_task_action_visibility(
			user="emp@example.com",
			task=self._task(),
			is_admin=False,
			is_manager=False,
			user_department="Sales",
		)
		self.assertTrue(vis["submit_update"])
		self.assertTrue(vis["reply"])
		self.assertFalse(vis["reassign"])
		self.assertFalse(vis["close_task"])

	def test_creator_sees_reassign_and_close(self):
		vis = get_task_action_visibility(
			user="creator@example.com",
			task=self._task(),
			is_admin=False,
			is_manager=False,
			user_department="Sales",
		)
		self.assertTrue(vis["reassign"])
		self.assertTrue(vis["close_task"])
		self.assertFalse(vis["submit_update"])

	def test_closed_task_ui_restrictions_for_employee(self):
		vis = get_task_action_visibility(
			user="emp@example.com",
			task=self._task(status="Closed"),
			is_admin=False,
			is_manager=False,
			user_department="Sales",
		)
		self.assertFalse(vis["submit_update"])
		self.assertFalse(vis["close_task"])
		self.assertTrue(vis["view_updates"])


class TestTimelineOrdering(unittest.TestCase):
	def test_chronological_ordering(self):
		items = [
			{"name": "b", "updated_on": "2026-07-29 12:00:00", "creation": "2"},
			{"name": "a", "updated_on": "2026-07-29 10:00:00", "creation": "1"},
			{"name": "c", "updated_on": "2026-07-29 12:00:00", "creation": "3"},
		]
		ordered = sort_timeline_chronological(items)
		self.assertEqual([row["name"] for row in ordered], ["a", "b", "c"])


class TestBrandingAndAssets(unittest.TestCase):
	def test_hooks_title_is_nave_tasks(self):
		text = (WORKSPACE / "project_custom" / "hooks.py").read_text()
		self.assertIn('"title": "NAVE Tasks"', text)
		self.assertIn('"/desk/nave-tasks"', text)
		self.assertNotIn('"title": "Task Management"', text)

	def test_page_js_contains_empty_and_error_states(self):
		js = (
			WORKSPACE
			/ "project_custom"
			/ "project_custom"
			/ "page"
			/ "nave_tasks"
			/ "nave_tasks.js"
		).read_text()
		self.assertIn("nt-empty", js)
		self.assertIn("nt-error", js)
		self.assertIn("Load More", js)
		self.assertIn("get_recurring_tasks", js)
		self.assertNotIn("Not configured yet", js)
		self.assertIn("frappe.utils.escape_html", js)
		self.assertIn("get_dashboard_counts", js)
		self.assertIn("get_task_timeline", js)
		self.assertIn("page_length", js)

	def test_css_file_exists(self):
		css = WORKSPACE / "project_custom" / "public" / "css" / "nave_tasks.css"
		self.assertTrue(css.exists())
		content = css.read_text()
		self.assertIn(".nave-tasks-app", content)
		self.assertIn("@media", content)


if __name__ == "__main__":
	unittest.main()
