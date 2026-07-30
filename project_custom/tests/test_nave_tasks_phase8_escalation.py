"""Batch 6 NAVE Task overdue escalation tests.

Mocks email and in-app notification creation — no real SMTP.
"""

from __future__ import annotations

import sys
import types
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

WORKSPACE = Path(__file__).resolve().parents[2]
if str(WORKSPACE) not in sys.path:
	sys.path.insert(0, str(WORKSPACE))


def _ensure_stub(frappe):
	if not hasattr(frappe, "sendmail") or not isinstance(
		getattr(frappe, "sendmail", None), MagicMock
	):
		frappe.sendmail = MagicMock()
	if not hasattr(frappe, "log_error") or not isinstance(
		getattr(frappe, "log_error", None), MagicMock
	):
		frappe.log_error = MagicMock()
	if not hasattr(frappe, "get_traceback"):
		frappe.get_traceback = MagicMock(return_value="traceback")
	if not hasattr(frappe, "get_doc") or not isinstance(
		getattr(frappe, "get_doc", None), MagicMock
	):
		frappe.get_doc = MagicMock()
	if not hasattr(frappe, "get_all") or not isinstance(
		getattr(frappe, "get_all", None), MagicMock
	):
		frappe.get_all = MagicMock(return_value=[])
	if not hasattr(frappe, "flags"):
		frappe.flags = types.SimpleNamespace(
			in_migrate=False, in_install=False, in_patch=False, mute_emails=False
		)
	if not hasattr(frappe, "local"):
		frappe.local = types.SimpleNamespace()
	if not hasattr(frappe, "cache"):
		store = {}

		class _Cache:
			def get_value(self, key):
				return store.get(key)

			def set_value(self, key, value, expires_in_sec=None):
				store[key] = value

		frappe._test_cache_store = store
		frappe.cache = lambda: _Cache()
	utils = getattr(frappe, "utils", None)
	if utils is not None:
		if not hasattr(utils, "escape_html"):
			utils.escape_html = lambda v: str(v or "")
		if not hasattr(utils, "get_url_to_form"):
			utils.get_url_to_form = (
				lambda doctype, name: f"/app/{doctype.lower().replace(' ', '-')}/{name}"
			)
		if not hasattr(utils, "getdate"):
			utils.getdate = (
				lambda d: d if hasattr(d, "year") else date.fromisoformat(str(d)[:10])
			)
		if not hasattr(utils, "nowdate"):
			utils.nowdate = lambda: "2026-07-29"
	if "frappe.utils.user" not in sys.modules:
		user_mod = types.ModuleType("frappe.utils.user")
		user_mod.get_users_with_role = lambda role: []
		sys.modules["frappe.utils.user"] = user_mod
	return frappe


def _install_fake_frappe():
	if "frappe" in sys.modules and hasattr(sys.modules["frappe"], "_nave_tasks_stub"):
		return _ensure_stub(sys.modules["frappe"])

	frappe = types.ModuleType("frappe")
	frappe._nave_tasks_stub = True
	frappe.session = types.SimpleNamespace(user="Guest")
	frappe.PermissionError = type("PermissionError", (Exception,), {})
	frappe.ValidationError = type("ValidationError", (Exception,), {})

	def throw(msg, exc=None):
		raise (exc or Exception)(msg)

	frappe.throw = throw
	frappe.get_roles = lambda user=None: []
	frappe.db = types.SimpleNamespace(
		escape=lambda value: f"'{value}'",
		get_value=MagicMock(return_value=None),
		exists=MagicMock(return_value=False),
		set_value=MagicMock(),
		count=MagicMock(return_value=0),
		sql=MagicMock(),
		commit=MagicMock(),
		has_column=MagicMock(return_value=True),
	)
	frappe.get_doc = MagicMock()
	frappe.get_all = MagicMock(return_value=[])
	frappe.whitelist = lambda *a, **k: (lambda fn: fn)
	frappe.sendmail = MagicMock()
	frappe.log_error = MagicMock()
	frappe.get_traceback = MagicMock(return_value="traceback")
	frappe.flags = types.SimpleNamespace(
		in_migrate=False, in_install=False, in_patch=False, mute_emails=False
	)
	frappe.local = types.SimpleNamespace()

	utils = types.ModuleType("frappe.utils")
	utils.cint = lambda v: int(float(v or 0))
	utils.flt = lambda v: float(v or 0)
	utils.nowdate = lambda: "2026-07-29"
	utils.now_datetime = lambda: "2026-07-29 12:00:00"
	utils.add_days = lambda d, n: d
	utils.getdate = lambda d: d if hasattr(d, "year") else date.fromisoformat(str(d)[:10])
	utils.escape_html = lambda v: str(v or "")
	utils.get_url_to_form = (
		lambda doctype, name: f"/app/{doctype.lower().replace(' ', '-')}/{name}"
	)
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
	return _ensure_stub(frappe)


_install_fake_frappe()

from project_custom import nave_task_escalation as esc  # noqa: E402
from project_custom.nave_task_escalation import (  # noqa: E402
	ESCALATION_DIRECTOR_7,
	ESCALATION_MANAGER_3,
	classify_escalation,
	send_nave_task_escalations,
)
from project_custom.nave_task_reminders import (  # noqa: E402
	REMINDER_OVERDUE,
	classify_reminder,
	send_nave_task_due_reminders,
)


TODAY = date(2026, 7, 29)


def _task(**kwargs):
	defaults = {
		"name": "NT-ESC-1",
		"subject": "Critical follow-up",
		"status": "Working",
		"assigned_to": "emp@example.com",
		"assigned_by": "creator@example.com",
		"owner": "creator@example.com",
		"priority": "High",
		"due_date": (TODAY - timedelta(days=3)).isoformat(),
		"project": "PROJ-1",
		"department": "Sales",
	}
	defaults.update(kwargs)
	return types.SimpleNamespace(**defaults)


class EscalationClassifyTests(unittest.TestCase):
	def test_only_exact_milestones(self):
		self.assertIsNone(classify_escalation(TODAY - timedelta(days=2), TODAY))
		self.assertEqual(
			classify_escalation(TODAY - timedelta(days=3), TODAY),
			ESCALATION_MANAGER_3,
		)
		self.assertIsNone(classify_escalation(TODAY - timedelta(days=4), TODAY))
		self.assertIsNone(classify_escalation(TODAY - timedelta(days=6), TODAY))
		self.assertEqual(
			classify_escalation(TODAY - timedelta(days=7), TODAY),
			ESCALATION_DIRECTOR_7,
		)
		self.assertIsNone(classify_escalation(TODAY - timedelta(days=8), TODAY))


class EscalationSendTests(unittest.TestCase):
	def setUp(self):
		self.frappe = _install_fake_frappe()
		self.frappe.local = types.SimpleNamespace()
		if hasattr(self.frappe, "_test_cache_store"):
			self.frappe._test_cache_store.clear()
		self.frappe.sendmail.reset_mock()
		self.frappe.log_error.reset_mock()
		self.notif_doc = MagicMock()
		self.notif_doc.insert = MagicMock()
		self.frappe.get_doc = MagicMock(return_value=self.notif_doc)

		self.users = {
			"emp@example.com": {"name": "emp@example.com", "email": "emp@example.com", "enabled": 1},
			"mgr@example.com": {"name": "mgr@example.com", "email": "mgr@example.com", "enabled": 1},
			"mgr-other@example.com": {
				"name": "mgr-other@example.com",
				"email": "mgr-other@example.com",
				"enabled": 1,
			},
			"dir@example.com": {"name": "dir@example.com", "email": "dir@example.com", "enabled": 1},
			"dir-other@example.com": {
				"name": "dir-other@example.com",
				"email": "dir-other@example.com",
				"enabled": 1,
			},
			"disabled-mgr@example.com": {
				"name": "disabled-mgr@example.com",
				"email": "disabled-mgr@example.com",
				"enabled": 0,
			},
		}
		self.departments = {
			"mgr@example.com": "Sales",
			"mgr-other@example.com": "Purchase",
			"dir@example.com": "Sales",
			"dir-other@example.com": "Purchase",
			"disabled-mgr@example.com": "Sales",
			"emp@example.com": "Sales",
		}

		def get_value(doctype, name=None, fieldname=None, as_dict=False, **kwargs):
			if doctype == "User":
				info = self.users.get(name)
				if not info:
					return None
				return dict(info) if as_dict else info.get(fieldname)
			if doctype == "Employee":
				filters = name if isinstance(name, dict) else {}
				user_id = filters.get("user_id")
				dept = self.departments.get(user_id)
				if fieldname == "department":
					return dept
				return {"department": dept} if as_dict else dept
			return None

		self.frappe.db.get_value = MagicMock(side_effect=get_value)
		self.frappe.get_all = MagicMock(return_value=[])

	def _subjects(self):
		out = []
		for c in self.frappe.get_doc.call_args_list:
			payload = c.args[0] if c.args else None
			if isinstance(payload, dict) and payload.get("doctype") == "Notification Log":
				out.append((payload.get("for_user"), payload.get("subject")))
		return out

	def _recipients(self):
		return [u for u, _ in self._subjects()]

	def _run_escalations(self, tasks, *, managers=None, directors=None):
		managers = managers if managers is not None else ["mgr@example.com", "mgr-other@example.com"]
		directors = (
			directors if directors is not None else ["dir@example.com", "dir-other@example.com"]
		)

		def get_all(doctype, *args, **kwargs):
			if doctype == "NAVE Task":
				return tasks
			if doctype == "Notification Log":
				return []
			return []

		self.frappe.get_all = MagicMock(side_effect=get_all)

		def role_users(role):
			if role == "NAVE Task Manager":
				return list(managers)
			if role == "NAVE Task Director":
				return list(directors)
			return []

		allowed = {
			"mgr@example.com",
			"dir@example.com",
			"emp@example.com",
			"disabled-mgr@example.com",
			"both@example.com",
		}
		with (
			patch(
				"frappe.utils.user.get_users_with_role",
				side_effect=role_users,
			),
			patch(
				"project_custom.nave_task_notifications.recipient_may_access_task",
				side_effect=lambda task, user: user in allowed
				and self.departments.get(user) == getattr(task, "department", None),
			),
		):
			return send_nave_task_escalations(today=TODAY)

	def test_three_day_notifies_relevant_manager(self):
		task = _task(due_date=(TODAY - timedelta(days=3)).isoformat())
		stats = self._run_escalations([task])
		self.assertEqual(stats["sent_manager_3"], 1)
		self.assertIn("mgr@example.com", self._recipients())
		self.assertTrue(any("3 Days Overdue" in s for _, s in self._subjects()))

	def test_three_day_does_not_notify_unrelated_manager(self):
		task = _task(due_date=(TODAY - timedelta(days=3)).isoformat())
		self._run_escalations([task])
		self.assertNotIn("mgr-other@example.com", self._recipients())

	def test_seven_day_notifies_relevant_director(self):
		task = _task(due_date=(TODAY - timedelta(days=7)).isoformat())
		stats = self._run_escalations([task])
		self.assertEqual(stats["sent_director_7"], 1)
		self.assertIn("dir@example.com", self._recipients())
		self.assertTrue(any("7 Days Overdue" in s for _, s in self._subjects()))

	def test_seven_day_does_not_notify_unrelated_director(self):
		task = _task(due_date=(TODAY - timedelta(days=7)).isoformat())
		self._run_escalations([task])
		self.assertNotIn("dir-other@example.com", self._recipients())

	def test_non_milestone_days_no_escalation(self):
		for days in (2, 4, 6, 8):
			self.frappe.get_doc.reset_mock()
			self.frappe.local = types.SimpleNamespace()
			if hasattr(self.frappe, "_test_cache_store"):
				self.frappe._test_cache_store.clear()
			task = _task(
				name=f"NT-D{days}",
				due_date=(TODAY - timedelta(days=days)).isoformat(),
			)
			stats = self._run_escalations([task])
			self.assertEqual(stats["sent"], 0, msg=f"days={days}")
			self.assertEqual(self._subjects(), [])

	def test_completed_closed_cancelled_skipped_by_empty_fetch(self):
		# DB filter excludes terminal statuses — empty candidates.
		stats = self._run_escalations([])
		self.assertEqual(stats["checked"], 0)
		self.assertEqual(stats["sent"], 0)

	def test_missing_due_or_assignee_skipped(self):
		stats = {
			"sent": 0,
			"sent_manager_3": 0,
			"sent_director_7": 0,
			"skipped_not_milestone": 0,
			"skipped_no_assignee": 0,
			"skipped_no_due": 0,
			"skipped_no_recipients": 0,
			"skipped_duplicate": 0,
			"skipped_recipient": 0,
		}
		with patch.object(esc, "resolve_escalation_recipients", return_value=["mgr@example.com"]):
			esc._process_one_task(_task(due_date=None), TODAY, stats)
			esc._process_one_task(_task(assigned_to=""), TODAY, stats)
		self.assertEqual(stats["sent"], 0)
		self.assertGreaterEqual(stats["skipped_not_milestone"] + stats["skipped_no_assignee"], 1)

	def test_disabled_manager_skipped(self):
		task = _task(due_date=(TODAY - timedelta(days=3)).isoformat())
		stats = self._run_escalations([task], managers=["disabled-mgr@example.com"])
		self.assertEqual(stats["sent"], 0)
		self.assertEqual(self._subjects(), [])

	def test_unauthorized_recipient_skipped(self):
		task = _task(due_date=(TODAY - timedelta(days=3)).isoformat())
		self.frappe.get_all = MagicMock(
			side_effect=lambda doctype, *a, **k: [task] if doctype == "NAVE Task" else []
		)
		with (
			patch(
				"frappe.utils.user.get_users_with_role",
				side_effect=lambda role: ["mgr@example.com"]
				if role == "NAVE Task Manager"
				else [],
			),
			patch(
				"project_custom.nave_task_notifications.recipient_may_access_task",
				return_value=False,
			),
		):
			stats = send_nave_task_escalations(today=TODAY)
		self.assertEqual(stats["sent"], 0)

	def test_assignee_still_gets_batch5_overdue_reminder(self):
		# Day 3 is odd → Batch 5 overdue reminder to assignee AND manager escalation.
		task = _task(due_date=(TODAY - timedelta(days=3)).isoformat())
		self.assertEqual(classify_reminder(task.due_date, TODAY), REMINDER_OVERDUE)

		self.frappe.get_all = MagicMock(
			side_effect=lambda doctype, *a, **k: (
				[task]
				if doctype == "NAVE Task"
				else ([] if doctype == "Notification Log" else [])
			)
		)
		with patch(
			"project_custom.nave_task_notifications.recipient_may_access_task",
			side_effect=lambda t, u: u == "emp@example.com",
		):
			rem = send_nave_task_due_reminders(today=TODAY)
		self.assertEqual(rem["sent_overdue"], 1)
		self.assertTrue(any(u == "emp@example.com" for u, s in self._subjects() if "Overdue" in s))

	def test_assignee_not_escalated_unless_manager(self):
		task = _task(due_date=(TODAY - timedelta(days=3)).isoformat())
		# Managers list does not include assignee
		self._run_escalations([task], managers=["mgr@example.com"])
		self.assertNotIn("emp@example.com", self._recipients())

	def test_scheduler_rerun_no_duplicate_manager(self):
		task = _task(due_date=(TODAY - timedelta(days=3)).isoformat())
		self._run_escalations([task])
		first = len(self._subjects())
		self._run_escalations([task])
		self.assertEqual(first, 1)
		self.assertEqual(len(self._subjects()), 1)

	def test_scheduler_rerun_no_duplicate_director(self):
		task = _task(due_date=(TODAY - timedelta(days=7)).isoformat())
		self._run_escalations([task])
		first = len(self._subjects())
		self._run_escalations([task])
		self.assertEqual(first, 1)
		self.assertEqual(len(self._subjects()), 1)

	def test_manager_and_director_keys_do_not_conflict(self):
		# Same recipient cannot normally be both, but keys differ by level.
		t3 = _task(name="NT-3", due_date=(TODAY - timedelta(days=3)).isoformat())
		t7 = _task(name="NT-7", due_date=(TODAY - timedelta(days=7)).isoformat())
		# Person with both roles in Sales
		self.departments["both@example.com"] = "Sales"
		self.users["both@example.com"] = {
			"name": "both@example.com",
			"email": "both@example.com",
			"enabled": 1,
		}
		stats = self._run_escalations(
			[t3, t7],
			managers=["both@example.com"],
			directors=["both@example.com"],
		)
		# Access patch in _run_escalations only allows fixed set — extend via direct call
		self.frappe.local = types.SimpleNamespace()
		if hasattr(self.frappe, "_test_cache_store"):
			self.frappe._test_cache_store.clear()
		self.frappe.get_doc.reset_mock()

		def get_all(doctype, *args, **kwargs):
			if doctype == "NAVE Task":
				return [t3, t7]
			if doctype == "Notification Log":
				return []
			return []

		self.frappe.get_all = MagicMock(side_effect=get_all)
		with (
			patch(
				"frappe.utils.user.get_users_with_role",
				side_effect=lambda role: ["both@example.com"],
			),
			patch(
				"project_custom.nave_task_notifications.recipient_may_access_task",
				return_value=True,
			),
		):
			stats = send_nave_task_escalations(today=TODAY)
		self.assertEqual(stats["sent_manager_3"], 1)
		self.assertEqual(stats["sent_director_7"], 1)
		subjects = [s for _, s in self._subjects()]
		self.assertEqual(len(subjects), 2)
		self.assertTrue(any("3 Days" in s for s in subjects))
		self.assertTrue(any("7 Days" in s for s in subjects))

	def test_one_failure_continues(self):
		t_bad = _task(name="NT-BAD", due_date=(TODAY - timedelta(days=3)).isoformat())
		t_ok = _task(name="NT-OK", due_date=(TODAY - timedelta(days=3)).isoformat())
		original = esc._process_one_task

		def flaky(task, today, stats):
			if task.name == "NT-BAD":
				raise RuntimeError("boom")
			return original(task, today, stats)

		self.frappe.get_all = MagicMock(
			side_effect=lambda doctype, *a, **k: (
				[t_bad, t_ok] if doctype == "NAVE Task" else []
			)
		)
		with (
			patch.object(esc, "_process_one_task", side_effect=flaky),
			patch.object(
				esc,
				"resolve_escalation_recipients",
				return_value=["mgr@example.com"],
			),
			patch(
				"project_custom.nave_task_notifications.recipient_may_access_task",
				return_value=True,
			),
		):
			# Need resolve on original path — flaky wraps process
			pass

		with (
			patch.object(esc, "_process_one_task", side_effect=flaky),
			patch(
				"frappe.utils.user.get_users_with_role",
				side_effect=lambda role: ["mgr@example.com"]
				if role == "NAVE Task Manager"
				else [],
			),
			patch(
				"project_custom.nave_task_notifications.recipient_may_access_task",
				side_effect=lambda t, u: u == "mgr@example.com",
			),
		):
			stats = send_nave_task_escalations(today=TODAY)
		self.assertEqual(stats["errors"], 1)
		self.assertEqual(stats["sent"], 1)
		self.assertTrue(self.frappe.log_error.called)

	def test_daily_job_order_reminders_then_escalations(self):
		import project_custom.api.nave_task as api

		order = []

		def rem():
			order.append("reminders")
			return {"ok": True}

		def esc_fn():
			order.append("escalations")
			return {"ok": True}

		with (
			patch.object(api, "refresh_overdue_flags", return_value={"ok": True}),
			patch(
				"project_custom.nave_task_generation.generate_due_recurring_tasks",
				return_value={"ok": True},
			),
			patch(
				"project_custom.nave_task_reminders.send_nave_task_due_reminders",
				side_effect=rem,
			),
			patch(
				"project_custom.nave_task_escalation.send_nave_task_escalations",
				side_effect=esc_fn,
			),
		):
			result = api.run_daily_nave_task_jobs()
		self.assertEqual(order, ["reminders", "escalations"])
		self.assertIn("escalations", result)


if __name__ == "__main__":
	unittest.main()
