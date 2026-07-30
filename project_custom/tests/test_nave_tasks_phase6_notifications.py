"""Batch 4 NAVE Task basic notification tests.

Mocks in-app Notification Log creation and email delivery — no real SMTP.
"""

from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, call, patch

WORKSPACE = Path(__file__).resolve().parents[2]
if str(WORKSPACE) not in sys.path:
	sys.path.insert(0, str(WORKSPACE))


def _ensure_notification_stub_attrs(frappe):
	"""Enrich a shared phase1–5 stub so Batch 4 tests can run in one suite."""
	if not hasattr(frappe, "OutgoingEmailError"):
		frappe.OutgoingEmailError = type("OutgoingEmailError", (Exception,), {})
	if not hasattr(frappe, "sendmail") or not isinstance(frappe.sendmail, MagicMock):
		frappe.sendmail = MagicMock()
	if not hasattr(frappe, "log_error") or not isinstance(frappe.log_error, MagicMock):
		frappe.log_error = MagicMock()
	if not hasattr(frappe, "get_traceback"):
		frappe.get_traceback = MagicMock(return_value="traceback")
	if not hasattr(frappe, "get_doc") or not isinstance(frappe.get_doc, MagicMock):
		frappe.get_doc = MagicMock()
	if not hasattr(frappe, "flags"):
		frappe.flags = types.SimpleNamespace(
			in_migrate=False,
			in_install=False,
			in_patch=False,
			mute_emails=False,
		)
	else:
		if not hasattr(frappe.flags, "mute_emails"):
			frappe.flags.mute_emails = False
	if not hasattr(frappe, "local"):
		frappe.local = types.SimpleNamespace()
	utils = getattr(frappe, "utils", None)
	if utils is not None:
		if not hasattr(utils, "escape_html"):
			utils.escape_html = lambda v: str(v or "")
		if not hasattr(utils, "get_url_to_form"):
			utils.get_url_to_form = (
				lambda doctype, name: f"/app/{doctype.lower().replace(' ', '-')}/{name}"
			)
	if "frappe.desk.doctype.notification_settings.notification_settings" not in sys.modules:
		desk = types.ModuleType("frappe.desk")
		desk_doctype = types.ModuleType("frappe.desk.doctype")
		notif_settings = types.ModuleType("frappe.desk.doctype.notification_settings")
		notif_settings_mod = types.ModuleType(
			"frappe.desk.doctype.notification_settings.notification_settings"
		)
		notif_settings_mod.is_notifications_enabled = lambda user: True
		notif_settings_mod.is_email_notifications_enabled_for_type = lambda user, t: False
		sys.modules.setdefault("frappe.desk", desk)
		sys.modules.setdefault("frappe.desk.doctype", desk_doctype)
		sys.modules.setdefault(
			"frappe.desk.doctype.notification_settings", notif_settings
		)
		sys.modules[
			"frappe.desk.doctype.notification_settings.notification_settings"
		] = notif_settings_mod
	if "frappe.utils.user" not in sys.modules:
		user_mod = types.ModuleType("frappe.utils.user")
		user_mod.get_users_with_role = lambda role: []
		sys.modules["frappe.utils.user"] = user_mod
	return frappe


def _install_fake_frappe():
	if "frappe" in sys.modules and hasattr(sys.modules["frappe"], "_nave_tasks_stub"):
		return _ensure_notification_stub_attrs(sys.modules["frappe"])

	frappe = types.ModuleType("frappe")
	frappe._nave_tasks_stub = True
	frappe.session = types.SimpleNamespace(user="Guest")
	frappe.PermissionError = type("PermissionError", (Exception,), {})
	frappe.ValidationError = type("ValidationError", (Exception,), {})
	frappe.OutgoingEmailError = type("OutgoingEmailError", (Exception,), {})

	def throw(msg, exc=None):
		raise (exc or Exception)(msg)

	frappe.throw = throw
	frappe.get_roles = lambda user=None: []
	frappe.db = types.SimpleNamespace(
		escape=lambda value: f"'{value}'",
		get_value=MagicMock(return_value=None),
		exists=MagicMock(return_value=True),
		set_value=MagicMock(),
		count=MagicMock(return_value=0),
		sql=MagicMock(),
		commit=MagicMock(),
		has_column=MagicMock(return_value=True),
	)
	frappe.get_doc = MagicMock()
	frappe.get_list = MagicMock(return_value=[])
	frappe.get_all = MagicMock(return_value=[])
	frappe.whitelist = lambda *args, **kwargs: (lambda fn: fn)
	frappe.sendmail = MagicMock()
	frappe.log_error = MagicMock()
	frappe.get_traceback = MagicMock(return_value="traceback")
	frappe.flags = types.SimpleNamespace(
		in_migrate=False,
		in_install=False,
		in_patch=False,
		mute_emails=False,
	)
	frappe.local = types.SimpleNamespace()
	frappe._dict = dict

	utils = types.ModuleType("frappe.utils")
	utils.cint = lambda v: int(float(v or 0))
	utils.flt = lambda v: float(v or 0)
	utils.nowdate = lambda: "2026-07-29"
	utils.now_datetime = lambda: "2026-07-29 12:00:00"
	utils.add_days = lambda d, n: d
	utils.getdate = lambda d: d
	utils.escape_html = lambda v: str(v or "")
	utils.get_url_to_form = lambda doctype, name: f"/app/{doctype.lower().replace(' ', '-')}/{name}"
	frappe.utils = utils

	model = types.ModuleType("frappe.model")
	document = types.ModuleType("frappe.model.document")

	class Document:
		pass

	document.Document = Document
	sys.modules["frappe"] = frappe
	sys.modules["frappe.utils"] = utils
	sys.modules["frappe.model"] = model
	sys.modules["frappe.model.document"] = document

	return _ensure_notification_stub_attrs(frappe)


_install_fake_frappe()

from project_custom import nave_task_notifications as notif  # noqa: E402
from project_custom.nave_task_notifications import (  # noqa: E402
	EVENT_ASSIGNED,
	EVENT_CLOSED,
	EVENT_COMPLETED,
	EVENT_REASSIGNED,
	EVENT_REOPENED,
	notify_document_insert,
	notify_document_update,
	notify_nave_task_event,
	notify_status_change,
)


def _reset_local(frappe):
	_ensure_notification_stub_attrs(frappe)
	frappe.local = types.SimpleNamespace()
	frappe.flags.mute_emails = False
	frappe.sendmail.reset_mock()
	frappe.log_error.reset_mock()
	frappe.get_doc.reset_mock()


def _task(**kwargs):
	defaults = {
		"name": "NT-2026-00099",
		"subject": "Inspect site",
		"status": "Working",
		"assigned_to": "emp@example.com",
		"owner": "creator@example.com",
		"assigned_by": "creator@example.com",
		"department": "Sales",
		"project": "PROJ-1",
		"priority": "High",
		"due_date": "2026-08-01",
		"progress": 10,
	}
	defaults.update(kwargs)
	return types.SimpleNamespace(**defaults)


class NotificationTestCase(unittest.TestCase):
	def setUp(self):
		self.frappe = sys.modules["frappe"]
		_reset_local(self.frappe)
		self.frappe.session.user = "mgr@example.com"
		self.user_map = {
			"emp@example.com": {
				"name": "emp@example.com",
				"email": "emp@example.com",
				"enabled": 1,
			},
			"creator@example.com": {
				"name": "creator@example.com",
				"email": "creator@example.com",
				"enabled": 1,
			},
			"prev@example.com": {
				"name": "prev@example.com",
				"email": "prev@example.com",
				"enabled": 1,
			},
			"mgr@example.com": {
				"name": "mgr@example.com",
				"email": "mgr@example.com",
				"enabled": 1,
			},
			"director@example.com": {
				"name": "director@example.com",
				"email": "director@example.com",
				"enabled": 1,
			},
			"disabled@example.com": {
				"name": "disabled@example.com",
				"email": "disabled@example.com",
				"enabled": 0,
			},
			"noemail@example.com": {
				"name": "noemail@example.com",
				"email": "",
				"enabled": 1,
			},
			"outsider@example.com": {
				"name": "outsider@example.com",
				"email": "outsider@example.com",
				"enabled": 1,
			},
		}

		def get_value(doctype, name=None, fieldname=None, as_dict=False, **kwargs):
			# User lookup
			if doctype == "User":
				key = name if isinstance(name, str) else None
				if isinstance(name, dict):
					key = name.get("name")
				info = self.user_map.get(key)
				if not info:
					return None
				if as_dict:
					return dict(info)
				if isinstance(fieldname, (list, tuple)):
					return tuple(info.get(f) for f in fieldname)
				return info.get(fieldname)
			# Employee department for managers
			if doctype == "Employee":
				filters = name if isinstance(name, dict) else {}
				user_id = filters.get("user_id")
				if user_id in ("mgr@example.com", "director@example.com"):
					return "Sales" if not as_dict and fieldname == "department" else (
						{"department": "Sales"} if as_dict else "Sales"
					)
				if user_id == "emp@example.com":
					return "Sales" if fieldname == "department" else None
				return None
			return None

		self.frappe.db.get_value = MagicMock(side_effect=get_value)

		notif_doc = MagicMock()
		notif_doc.insert = MagicMock()
		self.frappe.get_doc = MagicMock(return_value=notif_doc)
		self.notif_doc = notif_doc

	def _access_patch(self, allowed_users):
		return patch.object(
			notif,
			"recipient_may_access_task",
			side_effect=lambda task, user: user in allowed_users,
		)

	def _sent_users_in_app(self):
		users = []
		for c in self.frappe.get_doc.call_args_list:
			args = c.args[0] if c.args else c.kwargs
			if isinstance(args, dict) and args.get("doctype") == "Notification Log":
				users.append(args.get("for_user"))
		return users

	def _sent_emails(self):
		return [c.kwargs.get("recipients") or c.args[0] for c in self.frappe.sendmail.call_args_list]


class TestAssignmentNotifications(NotificationTestCase):
	def test_new_assignment_notifies_assignee(self):
		task = _task()
		with self._access_patch({"emp@example.com"}):
			notify_nave_task_event(task, EVENT_ASSIGNED, actor="creator@example.com")

		self.assertIn("emp@example.com", self._sent_users_in_app())
		self.assertTrue(any("emp@example.com" in (r or []) for r in self._sent_emails()))
		subject = self.frappe.get_doc.call_args.args[0]["subject"]
		self.assertIn("New Task Assigned", subject)

	def test_creator_same_as_assignee_no_notification(self):
		task = _task(assigned_to="creator@example.com", owner="creator@example.com")
		with self._access_patch({"creator@example.com"}):
			notify_nave_task_event(task, EVENT_ASSIGNED, actor="creator@example.com")

		self.assertEqual(self._sent_users_in_app(), [])
		self.assertEqual(self.frappe.sendmail.call_count, 0)


class TestReassignmentNotifications(NotificationTestCase):
	def test_reassignment_notifies_new_assignee(self):
		task = _task(assigned_to="emp@example.com")
		with self._access_patch({"emp@example.com", "prev@example.com"}):
			notify_nave_task_event(
				task,
				EVENT_REASSIGNED,
				actor="mgr@example.com",
				previous_assignee="prev@example.com",
			)

		users = self._sent_users_in_app()
		self.assertIn("emp@example.com", users)
		subjects = [
			c.args[0]["subject"]
			for c in self.frappe.get_doc.call_args_list
			if c.args and isinstance(c.args[0], dict)
		]
		self.assertTrue(any("Reassigned to You" in s for s in subjects))

	def test_previous_assignee_gets_informational_only(self):
		task = _task(assigned_to="emp@example.com")
		with self._access_patch({"emp@example.com", "prev@example.com"}):
			notify_nave_task_event(
				task,
				EVENT_REASSIGNED,
				actor="mgr@example.com",
				previous_assignee="prev@example.com",
			)

		prev_calls = [
			c.args[0]
			for c in self.frappe.get_doc.call_args_list
			if c.args and c.args[0].get("for_user") == "prev@example.com"
		]
		self.assertEqual(len(prev_calls), 1)
		self.assertIn("Task Reassigned:", prev_calls[0]["subject"])
		self.assertIn("reassigned", prev_calls[0]["email_content"].lower())
		# Exactly one in-app per recipient
		self.assertEqual(self._sent_users_in_app().count("prev@example.com"), 1)
		self.assertEqual(self._sent_users_in_app().count("emp@example.com"), 1)


class TestCompletionNotifications(NotificationTestCase):
	def test_completion_notifies_creator(self):
		task = _task()
		self.frappe.session.user = "emp@example.com"
		with (
			self._access_patch({"creator@example.com", "mgr@example.com"}),
			patch.object(notif, "_eligible_managers_and_directors", return_value=[]),
		):
			notify_nave_task_event(task, EVENT_COMPLETED, actor="emp@example.com")

		self.assertIn("creator@example.com", self._sent_users_in_app())
		subjects = [
			c.args[0]["subject"]
			for c in self.frappe.get_doc.call_args_list
			if c.args and isinstance(c.args[0], dict)
		]
		self.assertTrue(any("Task Completed" in s for s in subjects))

	def test_completion_notifies_eligible_manager(self):
		task = _task()
		self.frappe.session.user = "emp@example.com"
		with (
			self._access_patch({"creator@example.com", "mgr@example.com"}),
			patch.object(
				notif,
				"_eligible_managers_and_directors",
				return_value=["mgr@example.com"],
			),
		):
			notify_nave_task_event(task, EVENT_COMPLETED, actor="emp@example.com")

		users = self._sent_users_in_app()
		self.assertIn("creator@example.com", users)
		self.assertIn("mgr@example.com", users)


class TestReopenCloseNotifications(NotificationTestCase):
	def test_reopen_notifies_assignee_and_creator(self):
		task = _task(status="Working")
		self.frappe.session.user = "mgr@example.com"
		with self._access_patch({"emp@example.com", "creator@example.com", "mgr@example.com"}):
			notify_nave_task_event(task, EVENT_REOPENED, actor="mgr@example.com")

		users = self._sent_users_in_app()
		self.assertIn("emp@example.com", users)
		self.assertIn("creator@example.com", users)
		self.assertNotIn("mgr@example.com", users)

	def test_close_notifies_assignee_and_creator(self):
		task = _task(status="Closed")
		self.frappe.session.user = "mgr@example.com"
		with self._access_patch({"emp@example.com", "creator@example.com"}):
			notify_nave_task_event(task, EVENT_CLOSED, actor="mgr@example.com")

		users = self._sent_users_in_app()
		self.assertIn("emp@example.com", users)
		self.assertIn("creator@example.com", users)


class TestDedupAndPermissions(NotificationTestCase):
	def test_recipients_deduplicated(self):
		# owner == assigned_by == creator — still one notification
		task = _task()
		self.frappe.session.user = "emp@example.com"
		with (
			self._access_patch({"creator@example.com"}),
			patch.object(notif, "_eligible_managers_and_directors", return_value=["creator@example.com"]),
		):
			notify_nave_task_event(task, EVENT_COMPLETED, actor="emp@example.com")

		self.assertEqual(self._sent_users_in_app().count("creator@example.com"), 1)
		self.assertEqual(
			sum(1 for r in self._sent_emails() if "creator@example.com" in (r or [])),
			1,
		)

	def test_unauthorized_user_does_not_receive_details(self):
		task = _task()
		with self._access_patch(set()):
			notify_nave_task_event(task, EVENT_ASSIGNED, actor="creator@example.com")

		self.assertEqual(self._sent_users_in_app(), [])
		self.assertEqual(self.frappe.sendmail.call_count, 0)

	def test_event_deduped_on_second_call(self):
		task = _task()
		with self._access_patch({"emp@example.com"}):
			notify_nave_task_event(task, EVENT_ASSIGNED, actor="creator@example.com")
			notify_nave_task_event(task, EVENT_ASSIGNED, actor="creator@example.com")

		self.assertEqual(len(self._sent_users_in_app()), 1)

	def test_no_notification_when_status_unchanged(self):
		task = _task(status="Working")
		with self._access_patch({"creator@example.com", "emp@example.com"}):
			notify_status_change(task, "Working", "Working", actor="emp@example.com")

		self.assertEqual(self._sent_users_in_app(), [])


class TestDocumentAndApiPaths(NotificationTestCase):
	def test_form_save_triggers_assignment_on_insert(self):
		task = _task()
		task.flags = types.SimpleNamespace()
		with self._access_patch({"emp@example.com"}):
			notify_document_insert(task)

		self.assertIn("emp@example.com", self._sent_users_in_app())

	def test_form_save_triggers_status_event(self):
		task = _task(status="Completed")
		task.flags = types.SimpleNamespace()
		before = _task(status="Working", assigned_to="emp@example.com")
		task.get_doc_before_save = MagicMock(return_value=before)
		self.frappe.session.user = "emp@example.com"
		with (
			self._access_patch({"creator@example.com"}),
			patch.object(notif, "_eligible_managers_and_directors", return_value=[]),
		):
			notify_document_update(task)

		self.assertIn("creator@example.com", self._sent_users_in_app())

	def test_api_plus_document_save_does_not_duplicate(self):
		task = _task(status="Completed")
		task.flags = types.SimpleNamespace()
		before = _task(status="Working")
		task.get_doc_before_save = MagicMock(return_value=before)
		self.frappe.session.user = "emp@example.com"
		with (
			self._access_patch({"creator@example.com"}),
			patch.object(notif, "_eligible_managers_and_directors", return_value=[]),
		):
			notify_status_change(task, "Working", "Completed", actor="emp@example.com")
			notify_document_update(task)

		self.assertEqual(self._sent_users_in_app().count("creator@example.com"), 1)

	def test_api_reassign_triggers_event(self):
		import project_custom.api.nave_task as api

		task = _task(assigned_to="prev@example.com")
		task.db_set = MagicMock()
		task.reload = MagicMock()
		task.sync_assignment_todos = MagicMock()
		history = types.SimpleNamespace(name="NTU-1")
		self.frappe.session.user = "mgr@example.com"
		self.frappe.get_roles = lambda user=None: ["NAVE Task Manager"]

		with (
			patch.object(api, "require_nave_task_access"),
			patch.object(api, "get_task_for_user", return_value=task),
			patch.object(api, "can_manage_task_doc", return_value=True),
			patch.object(api, "get_employee", return_value=None),
			patch.object(api, "_create_history_entry", return_value=history),
			self._access_patch({"emp@example.com", "prev@example.com"}),
			patch.object(api, "notify_nave_task_event", wraps=notif.notify_nave_task_event) as wrapped,
		):
			# After reassign, assigned_to becomes emp — simulate db_set side effect
			def db_set(field, value, update_modified=True):
				setattr(task, field, value)

			task.db_set.side_effect = db_set
			result = api.reassign_task("NT-2026-00099", "emp@example.com", note="handoff")

		self.assertTrue(result["ok"])
		self.assertTrue(wrapped.called)
		self.assertEqual(wrapped.call_args.args[1], EVENT_REASSIGNED)


class TestEmailSafety(NotificationTestCase):
	def test_email_failure_does_not_fail_task(self):
		task = _task()
		self.frappe.sendmail.side_effect = self.frappe.OutgoingEmailError("SMTP down")
		with self._access_patch({"emp@example.com"}):
			# Must not raise
			notify_nave_task_event(task, EVENT_ASSIGNED, actor="creator@example.com")

		self.assertIn("emp@example.com", self._sent_users_in_app())
		self.assertTrue(self.frappe.log_error.called)

	def test_disabled_user_skipped(self):
		task = _task(assigned_to="disabled@example.com", owner="creator@example.com")
		with self._access_patch({"disabled@example.com"}):
			notify_nave_task_event(task, EVENT_ASSIGNED, actor="creator@example.com")

		self.assertEqual(self._sent_users_in_app(), [])
		self.assertEqual(self.frappe.sendmail.call_count, 0)

	def test_user_without_email_skipped_for_email_only(self):
		task = _task(assigned_to="noemail@example.com", owner="creator@example.com")
		with self._access_patch({"noemail@example.com"}):
			notify_nave_task_event(task, EVENT_ASSIGNED, actor="creator@example.com")

		self.assertIn("noemail@example.com", self._sent_users_in_app())
		self.assertEqual(self.frappe.sendmail.call_count, 0)

	def test_in_app_works_when_email_unavailable(self):
		task = _task(assigned_to="noemail@example.com", owner="creator@example.com")
		with self._access_patch({"noemail@example.com"}):
			notify_nave_task_event(task, EVENT_ASSIGNED, actor="creator@example.com")

		self.assertEqual(len(self._sent_users_in_app()), 1)
		payload = self.frappe.get_doc.call_args.args[0]
		self.assertEqual(payload["document_type"], "NAVE Task")
		self.assertEqual(payload["document_name"], task.name)
		self.assertTrue(payload["link"])


class TestEligibleManagers(NotificationTestCase):
	def test_eligible_managers_same_department(self):
		task = _task()
		with (
			patch(
				"frappe.utils.user.get_users_with_role",
				side_effect=lambda role: {
					"NAVE Task Manager": ["mgr@example.com", "outsider@example.com"],
					"NAVE Task Director": ["director@example.com"],
				}.get(role, []),
			),
			patch.object(
				notif,
				"recipient_may_access_task",
				side_effect=lambda task, user: user
				in ("mgr@example.com", "director@example.com"),
			),
		):
			# outsider has no Sales employee dept in get_value mock → excluded
			eligible = notif._eligible_managers_and_directors(task)

		self.assertIn("mgr@example.com", eligible)
		self.assertIn("director@example.com", eligible)
		self.assertNotIn("outsider@example.com", eligible)


if __name__ == "__main__":
	unittest.main()
