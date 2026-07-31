"""Phase 5 — professional conversation helpers, threads, seen receipts."""

from __future__ import annotations

import sys
import types
import unittest
from datetime import datetime
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
	frappe.session = types.SimpleNamespace(user="emp@example.com")
	frappe.PermissionError = type("PermissionError", (Exception,), {})
	frappe.ValidationError = type("ValidationError", (Exception,), {})
	frappe.flags = types.SimpleNamespace(in_migrate=False)

	def throw(msg, exc=None):
		raise (exc or Exception)(msg)

	frappe.throw = throw
	frappe.get_roles = lambda user=None: ["Employee"]
	frappe.db = types.SimpleNamespace(
		escape=lambda value: f"'{value}'",
		get_value=MagicMock(return_value=None),
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
	frappe.parse_json = lambda v: v
	frappe.utils = types.ModuleType("frappe.utils")
	frappe.utils.cint = lambda v: int(float(v or 0))
	frappe.utils.flt = lambda v: float(v or 0)
	frappe.utils.nowdate = lambda: "2026-07-31"
	frappe.utils.now_datetime = lambda: "2026-07-31 19:15:00"
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

from project_custom.nave_task_utils import (  # noqa: E402
	attachment_kind,
	build_progress_chip,
	dump_seen_receipts,
	format_conversation_time,
	parse_seen_receipts,
)


class TestConversationFormatting(unittest.TestCase):
	def test_compact_today_yesterday_and_date(self):
		now = datetime(2026, 7, 31, 19, 20, 0)
		self.assertEqual(
			format_conversation_time("2026-07-31 19:15:55.999580", now=now),
			"Today 7:15 PM",
		)
		self.assertEqual(
			format_conversation_time("2026-07-30 17:22:01", now=now),
			"Yesterday 5:22 PM",
		)
		self.assertEqual(
			format_conversation_time("2026-07-28 18:30:00", now=now),
			"28 Jul 6:30 PM",
		)
		self.assertNotIn("999", format_conversation_time("2026-07-31 19:15:55.999580", now=now))
		self.assertNotIn("@", format_conversation_time("2026-07-31 19:15:00", now=now))

	def test_progress_chip_and_attachment_kinds(self):
		self.assertEqual(build_progress_chip("Progress Update", "Working", 50), "Working • 50%")
		self.assertEqual(build_progress_chip("Completion Update", "Completed", 100), "Completed • 100%")
		self.assertEqual(build_progress_chip("Reassignment", "Working", 10), "Reassigned")
		self.assertIsNone(build_progress_chip("Reply", "Working", 10))
		self.assertEqual(attachment_kind("/files/a.png"), "photo")
		self.assertEqual(attachment_kind("/files/a.pdf"), "pdf")
		self.assertEqual(attachment_kind("/files/a.xlsx"), "excel")
		self.assertEqual(attachment_kind("/files/a.mp4"), "video")

	def test_seen_receipts_roundtrip(self):
		raw = dump_seen_receipts({"mgr@example.com": "2026-07-31 19:16:00"})
		parsed = parse_seen_receipts(raw)
		self.assertEqual(parsed["mgr@example.com"], "2026-07-31 19:16:00")


class TestThreadAndSeenApi(unittest.TestCase):
	def setUp(self):
		self.frappe = _install_fake_frappe()
		import importlib

		import project_custom.api.nave_task as api

		importlib.reload(api)
		self.api = api
		self.frappe.session.user = "emp@example.com"
		self.frappe.get_roles = lambda user=None: ["Employee"]
		self.frappe.db.has_column = MagicMock(return_value=True)

	def test_build_conversation_timeline_nests_replies(self):
		rows = [
			{
				"name": "NTU-1",
				"task": "NT-1",
				"update_by": "mgr@example.com",
				"employee": None,
				"updated_on": "2026-07-31 18:00:00",
				"update_type": "Manager Instruction",
				"status": "Working",
				"progress": 20,
				"update_text": "Need supervisor tomorrow morning.",
				"attachment": None,
				"parent_update": None,
				"seen_receipts": "{}",
				"creation": "2026-07-31 18:00:00",
			},
			{
				"name": "NTU-2",
				"task": "NT-1",
				"update_by": "emp@example.com",
				"employee": None,
				"updated_on": "2026-07-31 18:05:00",
				"update_type": "Reply",
				"status": "Working",
				"progress": 20,
				"update_text": "Understood.",
				"attachment": None,
				"parent_update": "NTU-1",
				"seen_receipts": "{}",
				"creation": "2026-07-31 18:05:00",
			},
			{
				"name": "NTU-3",
				"task": "NT-1",
				"update_by": "emp@example.com",
				"employee": None,
				"updated_on": "2026-07-31 19:00:00",
				"update_type": "Progress Update",
				"status": "Working",
				"progress": 50,
				"update_text": "Halfway done",
				"attachment": "/files/shot.png",
				"parent_update": None,
				"seen_receipts": '{"mgr@example.com":"2026-07-31 19:01:00"}',
				"creation": "2026-07-31 19:00:00",
			},
		]
		task = types.SimpleNamespace(
			owner="mgr@example.com",
			assigned_by="mgr@example.com",
			assigned_to="emp@example.com",
		)
		with (
			patch.object(self.api, "get_user_full_name", side_effect=lambda u: u.split("@")[0].title()),
			patch.object(self.api, "is_admin", return_value=False),
			patch.object(self.api, "is_task_director", return_value=False),
			patch.object(self.api, "is_task_manager", side_effect=lambda u=None: u == "mgr@example.com"),
			patch.object(self.frappe.db, "get_value", return_value=None),
		):
			timeline = self.api.build_conversation_timeline(
				rows, task, viewer="emp@example.com"
			)

		self.assertEqual(len(timeline), 2)
		self.assertEqual(timeline[0]["name"], "NTU-1")
		self.assertEqual(len(timeline[0]["replies"]), 1)
		self.assertEqual(timeline[0]["replies"][0]["name"], "NTU-2")
		self.assertEqual(timeline[0]["replies"][0]["parent_snippet"], "Need supervisor tomorrow morning.")
		self.assertNotIn("18:00:00", timeline[0]["display_time"])
		self.assertNotIn("999", timeline[0]["display_time"])
		self.assertNotIn("@", timeline[0]["sender_full_name"] or "")
		self.assertEqual(timeline[1]["progress_chip"], "Working • 50%")
		self.assertEqual(timeline[1]["attachment_kind"], "photo")
		self.assertEqual(timeline[1]["delivery_state"], "seen")
		self.assertTrue(timeline[1]["is_mine"])

	def test_mark_timeline_seen_updates_receipts(self):
		task = types.SimpleNamespace(name="NT-1")
		row = types.SimpleNamespace(
			name="NTU-1",
			task="NT-1",
			update_by="mgr@example.com",
			seen_receipts="{}",
		)
		self.frappe.session.user = "emp@example.com"
		self.frappe.get_list = MagicMock(return_value=["NTU-1"])
		self.frappe.db.get_value = MagicMock(return_value=row)
		self.frappe.db.set_value = MagicMock()
		with patch.object(self.api, "get_task_for_user", return_value=task):
			result = self.api.mark_timeline_seen("NT-1")
		self.assertTrue(result["ok"])
		self.assertEqual(result["marked"], 1)
		self.frappe.db.set_value.assert_called_once()
		args = self.frappe.db.set_value.call_args
		self.assertEqual(args.args[0], "NAVE Task Update")
		self.assertEqual(args.args[1], "NTU-1")
		self.assertEqual(args.args[2], "seen_receipts")
		self.assertIn("emp@example.com", args.args[3])

	def test_mark_seen_denied_without_task_access(self):
		self.frappe.session.user = "stranger@example.com"
		with patch.object(
			self.api,
			"get_task_for_user",
			side_effect=self.frappe.PermissionError("denied"),
		):
			with self.assertRaises(self.frappe.PermissionError):
				self.api.mark_timeline_seen("NT-1")

	def test_post_task_message_accepts_parent_update(self):
		task = types.SimpleNamespace(
			name="NT-1",
			status="Working",
			progress=20,
			due_date="2026-08-01",
			completed_on=None,
			support_required="",
			db_set=MagicMock(),
			owner="mgr@example.com",
			assigned_by="mgr@example.com",
			assigned_to="emp@example.com",
			department="Sales",
		)
		parent = types.SimpleNamespace(
			name="NTU-1",
			task="NT-1",
			update_text="Need supervisor tomorrow morning.",
			update_by="mgr@example.com",
		)
		history = types.SimpleNamespace(
			name="NTU-2",
			update_by="emp@example.com",
			employee=None,
			updated_on="2026-07-31 19:18:00",
			update_type="Reply",
			status="Working",
			progress=20,
			update_text="Understood",
			pending_reason=None,
			support_required="",
			attachment=None,
			creation="2026-07-31 19:18:00",
			parent_update="NTU-1",
			seen_receipts="{}",
		)
		self.frappe.db.get_value = MagicMock(return_value=parent)
		with (
			patch.object(self.api, "get_task_for_user", return_value=task),
			patch.object(self.api, "get_employee", return_value=None),
			patch.object(self.api, "_create_history_entry", return_value=history) as create,
			patch.object(self.api, "get_user_full_name", return_value="Emp"),
			patch.object(self.api, "is_admin", return_value=False),
			patch.object(self.api, "is_task_director", return_value=False),
			patch.object(self.api, "is_task_manager", return_value=False),
		):
			result = self.api.post_task_message(
				"NT-1",
				"Understood",
				update_type="Reply",
				parent_update="NTU-1",
			)
		self.assertTrue(result["ok"])
		self.assertEqual(result["parent_update"], "NTU-1")
		self.assertEqual(create.call_args.kwargs.get("parent_update"), "NTU-1")
		self.assertEqual(result["timeline_item"]["parent_snippet"], "Need supervisor tomorrow morning.")


class TestConversationUiAssets(unittest.TestCase):
	def test_js_has_compact_chat_markers(self):
		js = (
			WORKSPACE
			/ "project_custom"
			/ "project_custom"
			/ "page"
			/ "nave_tasks"
			/ "nave_tasks.js"
		).read_text()
		for needle in (
			"nt-conversation",
			"nt-chat-feed",
			"nt-progress-chip",
			"nt-chat-quote",
			"nt-chat-ticks",
			"parent_update",
			"mark_timeline_seen",
			"Shift+Enter",
		):
			self.assertIn(needle, js)

	def test_css_has_conversation_layout(self):
		css = (WORKSPACE / "project_custom" / "public" / "css" / "nave_tasks.css").read_text()
		self.assertIn(".nt-conversation", css)
		self.assertIn(".nt-chat-bubble", css)
		self.assertIn(".nt-progress-chip", css)

	def test_doctype_has_thread_and_seen_fields(self):
		text = (
			WORKSPACE
			/ "project_custom"
			/ "project_custom"
			/ "doctype"
			/ "nave_task_update"
			/ "nave_task_update.json"
		).read_text()
		self.assertIn('"parent_update"', text)
		self.assertIn('"seen_receipts"', text)


if __name__ == "__main__":
	unittest.main()
