"""Phase 5.1 production bug fixes — targeted regression tests."""

from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

WORKSPACE = Path(__file__).resolve().parents[2]
if str(WORKSPACE) not in sys.path:
	sys.path.insert(0, str(WORKSPACE))


def _install_fake_frappe():
	if "frappe" in sys.modules and hasattr(sys.modules["frappe"], "_nave_tasks_stub"):
		return sys.modules["frappe"]

	frappe = types.ModuleType("frappe")
	frappe._nave_tasks_stub = True
	frappe.session = types.SimpleNamespace(user="creator@example.com")
	frappe.PermissionError = type("PermissionError", (Exception,), {})
	frappe.ValidationError = type("ValidationError", (Exception,), {})
	frappe.flags = types.SimpleNamespace(in_migrate=False, in_install=False, in_patch=False)
	frappe.local = types.SimpleNamespace()

	def throw(msg, exc=None):
		raise (exc or Exception)(msg)

	frappe.throw = throw
	frappe.get_roles = lambda user=None: ["Employee"]
	frappe.db = types.SimpleNamespace(
		escape=lambda value: f"'{value}'",
		get_value=MagicMock(return_value=None),
		get_single_value=MagicMock(return_value="Nave Industries"),
		exists=MagicMock(return_value=False),
		set_value=MagicMock(),
		sql=MagicMock(return_value=((0,),)),
		has_column=MagicMock(return_value=True),
		table_exists=MagicMock(return_value=True),
	)
	frappe.get_doc = MagicMock()
	frappe.get_list = MagicMock(return_value=[])
	frappe.get_all = MagicMock(return_value=[])
	frappe.whitelist = lambda *a, **k: (lambda fn: fn)
	frappe.utils = types.ModuleType("frappe.utils")
	frappe.utils.cint = lambda v: int(float(v or 0))
	frappe.utils.flt = lambda v: float(v or 0)
	frappe.utils.nowdate = lambda: "2026-07-31"
	frappe.utils.now_datetime = lambda: "2026-07-31 22:00:00"
	frappe.utils.add_days = lambda d, n: d
	frappe.utils.getdate = lambda d: d

	model = types.ModuleType("frappe.model")
	document = types.ModuleType("frappe.model.document")

	class Document:
		pass

	document.Document = Document
	sys.modules["frappe"] = frappe
	sys.modules["frappe.utils"] = frappe.utils
	sys.modules["frappe.model"] = model
	sys.modules["frappe.model.document"] = document
	return frappe


_install_fake_frappe()

from project_custom.api import nave_task as api  # noqa: E402
from project_custom.nave_task_notifications import (  # noqa: E402
	EVENT_ASSIGNED,
	EVENT_MESSAGE,
	notify_nave_task_event,
)
from project_custom.nave_task_utils import user_can_access_task  # noqa: E402


class _Dict(dict):
	"""Mimic frappe._dict: missing attrs resolve to None via __getattr__."""

	def __getattr__(self, key):
		return self.get(key)

	def __setattr__(self, key, value):
		self[key] = value


class TestSerializeTaskAllTasksBug(unittest.TestCase):
	def test_serialize_task_handles_frappe_dict_without_as_dict(self):
		row = _Dict(
			name="NT-1",
			subject="Hello",
			description="Desc",
			category=None,
			priority="Medium",
			status="Open",
			progress=0,
			assigned_to="emp@example.com",
			assigned_employee=None,
			assigned_by="creator@example.com",
			owner="creator@example.com",
			department="Sales",
			company="Nave",
			project=None,
			site=None,
			start_date=None,
			due_date="2026-08-01",
			is_overdue=0,
			is_recurring=0,
			recurrence_active=0,
			recurrence_frequency=None,
			recurrence_start_date=None,
			recurrence_end_date=None,
			next_creation_date=None,
			last_generated_date=None,
			recurrence_due_after_days=None,
			recurring_template=None,
			generated_from=None,
			recurrence_sequence=None,
			recurrence_occurrence_date=None,
			latest_update="hi",
			pending_reason=None,
			support_required=None,
			completed_on=None,
			completion_remarks=None,
			completion_attachment=None,
			modified="2026-07-31",
			creation="2026-07-31",
		)
		# Classic crash: hasattr(_dict, "as_dict") is True and value is None.
		self.assertTrue(hasattr(row, "as_dict"))
		self.assertIsNone(row.as_dict)
		with patch.object(api, "get_user_full_name", return_value="Emp"):
			payload = api.serialize_task(row)
		self.assertEqual(payload["name"], "NT-1")
		self.assertEqual(payload["subject"], "Hello")
		self.assertEqual(payload["assigned_to_name"], "Emp")


class TestCreatorConversationAccess(unittest.TestCase):
	def test_creator_and_assignee_both_access_task(self):
		common = dict(
			assigned_to="emp@example.com",
			owner="creator@example.com",
			assigned_by="creator@example.com",
			department="Sales",
			is_admin=False,
			is_director=False,
			is_manager=False,
			user_department="Sales",
		)
		self.assertTrue(user_can_access_task(user="creator@example.com", **common))
		self.assertTrue(user_can_access_task(user="emp@example.com", **common))

	def test_allowed_types_give_creator_reply_not_progress(self):
		task = types.SimpleNamespace(
			name="NT-1",
			assigned_to="emp@example.com",
			owner="creator@example.com",
			assigned_by="creator@example.com",
			department="Sales",
			status="Working",
		)
		self.frappe = sys.modules["frappe"]
		self.frappe.session.user = "creator@example.com"
		self.frappe.get_roles = lambda user=None: ["Employee"]
		with (
			patch.object(api, "can_submit_progress_on_task", return_value=False),
			patch.object(api, "can_manage_task_doc", return_value=True),
			patch.object(api, "is_admin", return_value=False),
			patch.object(api, "is_task_director", return_value=False),
			patch.object(api, "is_task_manager", return_value=False),
			patch.object(api, "user_can_see_internal_notes", return_value=False),
		):
			types_allowed = api._allowed_conversation_types_for_user(task, "creator@example.com")
		self.assertIn("Reply", types_allowed)
		self.assertIn("Clarification Required", types_allowed)
		self.assertNotIn("Progress Update", types_allowed)


class TestUpdatesOneCardPerTask(unittest.TestCase):
	def test_updates_list_queries_tasks_not_flat_updates(self):
		self.frappe = sys.modules["frappe"]
		self.frappe.session.user = "creator@example.com"
		task_row = _Dict(
			name="NT-1",
			subject="Subject",
			status="Working",
			priority="Medium",
			latest_update="latest msg",
			modified="2026-07-31 12:00:00",
			assigned_to="emp@example.com",
			assigned_by="creator@example.com",
			owner="creator@example.com",
			department="Sales",
			progress=10,
		)
		update_row = _Dict(
			name="NTU-1",
			task="NT-1",
			update_by="emp@example.com",
			employee=None,
			updated_on="2026-07-31 12:00:00",
			update_type="Reply",
			status="Working",
			progress=10,
			update_text="latest msg",
			pending_reason=None,
			support_required=None,
			attachment=None,
			creation="2026-07-31 12:00:00",
			parent_update=None,
			seen_receipts="{}",
		)

		def get_list(doctype, **kwargs):
			if doctype == "NAVE Task":
				return [task_row]
			if doctype == "NAVE Task Update":
				return [update_row]
			return []

		self.frappe.get_list = MagicMock(side_effect=get_list)
		with (
			patch.object(api, "require_nave_task_access"),
			patch.object(api, "_permission_aware_count", return_value=1),
			patch.object(api, "user_can_see_internal_notes", return_value=False),
			patch.object(api, "get_user_full_name", return_value="Emp"),
			patch.object(api, "get_display_role", return_value="Employee"),
		):
			result = api.get_task_updates_list(page=1, page_length=20)

		self.assertEqual(result["total"], 1)
		self.assertEqual(len(result["data"]), 1)
		self.assertEqual(result["data"][0]["task"], "NT-1")
		self.assertEqual(result["data"][0]["task_subject"], "Subject")
		self.assertEqual(result["data"][0]["update_text"], "latest msg")
		# First get_list call must be NAVE Task (one card per task).
		first_doctype = self.frappe.get_list.call_args_list[0].args[0]
		self.assertEqual(first_doctype, "NAVE Task")


class TestMessageNotification(unittest.TestCase):
	def setUp(self):
		self.frappe = sys.modules["frappe"]
		self.frappe.local = types.SimpleNamespace()
		self.frappe.get_doc = MagicMock()
		self.frappe.get_roles = lambda user=None: ["Employee"]
		self.frappe.db.get_value = MagicMock(
			side_effect=lambda *a, **k: (
				{"name": a[1], "email": a[1], "enabled": 1}
				if a[0] == "User"
				else None
			)
		)

	def test_message_event_notifies_assignee_and_creator(self):
		import project_custom.nave_task_notifications as notif

		task = types.SimpleNamespace(
			name="NT-9",
			subject="Chat",
			assigned_to="emp@example.com",
			assigned_by="creator@example.com",
			owner="creator@example.com",
			department="Sales",
			status="Working",
			priority="Medium",
			due_date="2026-08-01",
			progress=0,
		)
		sent = []

		def capture_in_app(**kwargs):
			sent.append(kwargs.get("user"))

		with (
			patch.object(notif, "_create_in_app_notification", side_effect=capture_in_app),
			patch.object(notif, "_send_email_safely", MagicMock()),
			patch.object(notif, "recipient_may_access_task", return_value=True),
			patch.object(notif, "_in_app_enabled", return_value=True),
		):
			notify_nave_task_event(task, EVENT_MESSAGE, actor="creator@example.com")

		self.assertIn("emp@example.com", sent)
		self.assertNotIn("creator@example.com", sent)

	def test_post_task_message_triggers_message_event(self):
		task = types.SimpleNamespace(
			name="NT-2",
			assigned_to="emp@example.com",
			owner="creator@example.com",
			assigned_by="creator@example.com",
			department="Sales",
			status="Working",
			progress=20,
			due_date="2026-08-01",
			support_required=0,
			completed_on=None,
			db_set=MagicMock(),
		)
		history = types.SimpleNamespace(
			name="NTU-2",
			update_by="creator@example.com",
			employee=None,
			updated_on="2026-07-31",
			update_type="Reply",
			status="Working",
			progress=20,
			update_text="hello",
			pending_reason=None,
			support_required=None,
			attachment=None,
			creation="2026-07-31",
			parent_update=None,
			seen_receipts="{}",
		)
		self.frappe.session.user = "creator@example.com"
		with (
			patch.object(api, "require_nave_task_access"),
			patch.object(api, "get_task_for_user", return_value=task),
			patch.object(api, "_create_history_entry", return_value=history),
			patch.object(api, "notify_nave_task_event") as notify,
			patch.object(api, "get_user_full_name", return_value="Creator"),
			patch.object(api, "get_display_role", return_value="Employee"),
			patch.object(api, "enrich_timeline_item", side_effect=lambda *a, **k: {"ok": 1}),
		):
			api.post_task_message("NT-2", message="hello", update_type="Reply")
		notify.assert_called()
		self.assertEqual(notify.call_args.args[1], EVENT_MESSAGE)


class TestUiAssets(unittest.TestCase):
	def test_updates_ui_shows_one_card_fields(self):
		js = (
			WORKSPACE
			/ "project_custom"
			/ "project_custom"
			/ "page"
			/ "nave_tasks"
			/ "nave_tasks.js"
		).read_text(encoding="utf-8")
		self.assertIn("task_subject", js)
		self.assertIn("Open Task", js)
		self.assertIn("can_reply_on_task", js)
		self.assertIn("nt-chat-bubble", js)


if __name__ == "__main__":
	unittest.main()
