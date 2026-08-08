"""Step 5 — Unbilled alert batch email + in-app notification."""

from __future__ import annotations

import copy
import sys
import types
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

WORKSPACE = Path(__file__).resolve().parents[2]
if str(WORKSPACE) not in sys.path:
	sys.path.insert(0, str(WORKSPACE))


def _install_fake_frappe():
	if "frappe" in sys.modules and hasattr(sys.modules["frappe"], "_unbilled_notify_stub"):
		return sys.modules["frappe"]

	frappe = types.ModuleType("frappe")
	frappe._unbilled_notify_stub = True
	frappe.session = types.SimpleNamespace(user="Administrator")
	frappe.ValidationError = type("ValidationError", (Exception,), {})
	frappe.PermissionError = type("PermissionError", (Exception,), {})
	frappe.flags = types.SimpleNamespace(mute_emails=False)
	frappe.log_error = MagicMock()
	frappe.sendmail = MagicMock()

	def throw(msg, exc=None):
		raise (exc or Exception)(msg)

	frappe.throw = throw
	frappe.whitelist = lambda *a, **k: (lambda fn: fn)
	frappe.db = types.SimpleNamespace(
		sql=lambda *a, **k: [],
		get_value=lambda *a, **k: None,
		get_single_value=lambda *a, **k: 5,
		exists=lambda *a, **k: False,
	)
	frappe.get_all = lambda *a, **k: []
	frappe.get_single = lambda *a, **k: types.SimpleNamespace()
	frappe.get_doc = MagicMock()

	utils = types.ModuleType("frappe.utils")

	def flt(v, precision=None):
		try:
			return float(v or 0)
		except Exception:
			return 0.0

	def cint(v):
		try:
			return int(float(v or 0))
		except Exception:
			return 0

	def getdate(d):
		if d is None or d == "":
			return None
		if isinstance(d, date) and not isinstance(d, datetime):
			return d
		if isinstance(d, datetime):
			return d.date()
		return date.fromisoformat(str(d)[:10])

	def formatdate(d, df=None):
		d = getdate(d)
		if not d:
			return ""
		if df == "dd MMM yyyy":
			return d.strftime("%d %b %Y")
		return d.isoformat()

	def fmt_money(amount, currency=None):
		return f"{currency or ''} {flt(amount):,.2f}".strip()

	def validate_email_address(email, throw=False):
		if not email or "@" not in email or email.startswith("bad"):
			if throw:
				frappe.throw(f"Invalid email: {email}")
			return None
		return email.strip()

	def escape_html(s):
		return (
			str(s)
			.replace("&", "&amp;")
			.replace("<", "&lt;")
			.replace(">", "&gt;")
			.replace('"', "&quot;")
		)

	utils.flt = flt
	utils.cint = cint
	utils.getdate = getdate
	utils.get_datetime = lambda d: datetime.fromisoformat(str(d)) if d else None
	utils.formatdate = formatdate
	utils.fmt_money = fmt_money
	utils.validate_email_address = validate_email_address
	utils.escape_html = escape_html
	utils.nowdate = lambda: "2026-08-08"
	utils.now_datetime = lambda: datetime(2026, 8, 8, 12, 0, 0)
	utils.add_days = lambda d, n: getdate(d) + timedelta(days=n)
	frappe.utils = utils

	sys.modules["frappe"] = frappe
	sys.modules["frappe.utils"] = utils
	sys.modules["frappe.model"] = types.ModuleType("frappe.model")
	doc_mod = types.ModuleType("frappe.model.document")
	doc_mod.Document = type("Document", (), {})
	sys.modules["frappe.model.document"] = doc_mod
	return frappe


_install_fake_frappe()

from project_custom import project_unbilled_alert_cycle as cycle  # noqa: E402
from project_custom import project_unbilled_alert_notify as notify  # noqa: E402

NOTIFY_MOD = WORKSPACE / "project_custom" / "project_unbilled_alert_notify.py"


class FakeCycleDoc:
	store: dict = {}

	def __init__(self, data):
		self._data = dict(data)
		self.name = data.get("name") or "NPUA-X"
		self._data["name"] = self.name
		for k, v in list(self._data.items()):
			setattr(self, k, v)

	def __setattr__(self, key, value):
		if key.startswith("_") or key == "name":
			object.__setattr__(self, key, value)
			if key == "name":
				self._data["name"] = value
			return
		object.__setattr__(self, key, value)
		self._data[key] = value

	def save(self):
		FakeCycleDoc.store[self.name] = copy.deepcopy(self._data)
		return self

	def insert(self, ignore_permissions=False):
		FakeCycleDoc.store[self.name] = copy.deepcopy(self._data)
		return self

	def as_dict(self):
		return copy.deepcopy(self._data)


def _settings(**kwargs):
	base = {
		"enabled": 1,
		"threshold_amount": 10000,
		"ageing_days": 5,
		"director_emails": "dir@nave.com",
		"send_email": 1,
		"create_in_app_notification": 0,
	}
	base.update(kwargs)
	return base


def _cycle(**kwargs):
	base = {
		"name": "NPUA-1",
		"project": "PROJ-A",
		"project_name": "Alpha",
		"company": "Nave",
		"customer": "Cust-A",
		"cycle_no": 1,
		"current_unbilled_amount": 15000,
		"threshold_amount": 10000,
		"threshold_crossed_on": date(2026, 8, 1),
		"ageing_days": 7,
		"last_sales_invoice_date": date(2026, 7, 15),
		"project_status": "Open",
		"alert_status": "Pending",
		"alert_sent": 0,
		"resolved_on": None,
	}
	base.update(kwargs)
	return base


class TestRecipientParser(unittest.TestCase):
	def test_comma_separated(self):
		out = notify.parse_director_recipient_emails("a@x.com, b@y.com")
		self.assertEqual(out["valid"], ["a@x.com", "b@y.com"])
		self.assertEqual(out["invalid"], [])

	def test_newline_separated(self):
		out = notify.parse_director_recipient_emails("a@x.com\nb@y.com")
		self.assertEqual(out["valid"], ["a@x.com", "b@y.com"])

	def test_invalid_skipped(self):
		out = notify.parse_director_recipient_emails("good@x.com, bad-email, also@ok.com")
		self.assertEqual(out["valid"], ["good@x.com", "also@ok.com"])
		self.assertEqual(out["invalid"], ["bad-email"])

	def test_duplicates_removed(self):
		out = notify.parse_director_recipient_emails("a@x.com, A@x.com; a@x.com")
		self.assertEqual(out["valid"], ["a@x.com"])


class TestEmailBatch(unittest.TestCase):
	def setUp(self):
		FakeCycleDoc.store = {}
		notify.frappe.sendmail = MagicMock()

	def test_no_recipients_no_sent_flag(self):
		cycles = [_cycle()]
		FakeCycleDoc.store["NPUA-1"] = _cycle()

		def get_doc(dt, name=None):
			if isinstance(dt, dict):
				return FakeCycleDoc(dt)
			return FakeCycleDoc(FakeCycleDoc.store[name])

		with patch.object(notify.frappe, "get_doc", side_effect=get_doc):
			out = notify.send_unbilled_alert_batch(
				_settings(director_emails="bad-email"),
				cycles=cycles,
			)
		self.assertEqual(out["skipped_reason"], "no_valid_recipients")
		self.assertEqual(out["alerts_sent"], 0)
		self.assertEqual(FakeCycleDoc.store["NPUA-1"]["alert_sent"], 0)
		notify.frappe.sendmail.assert_not_called()

	def test_only_eligible_included_excludes_resolved_alerted(self):
		rows = [
			_cycle(name="NPUA-OK"),
			_cycle(name="NPUA-RES", alert_status="Resolved", resolved_on=datetime.now()),
			_cycle(name="NPUA-ALR", alert_status="Alerted", alert_sent=1),
			_cycle(
				name="NPUA-YOUNG",
				threshold_crossed_on=date(2026, 8, 7),
				ageing_days=1,
			),
		]
		ageing_threshold = 5
		as_of = date(2026, 8, 8)
		out_cycles = []
		for c in rows:
			c = dict(c)
			c["ageing_days"] = cycle.calculate_ageing_days(
				c["threshold_crossed_on"], today=as_of
			)
			if cycle.is_cycle_alert_eligible(
				c, today=as_of, ageing_threshold=ageing_threshold
			):
				out_cycles.append(c)
		self.assertEqual([c["name"] for c in out_cycles], ["NPUA-OK"])

	def test_one_email_multiple_projects_columns_sort_subject(self):
		cycles = [
			_cycle(
				name="NPUA-1",
				project="PROJ-B",
				project_name="Beta",
				current_unbilled_amount=12000,
				threshold_crossed_on=date(2026, 8, 1),
				ageing_days=7,
			),
			_cycle(
				name="NPUA-2",
				project="PROJ-A",
				project_name="Alpha",
				current_unbilled_amount=20000,
				threshold_crossed_on=date(2026, 8, 1),
				ageing_days=7,
			),
			_cycle(
				name="NPUA-3",
				project="PROJ-C",
				project_name="Gamma",
				current_unbilled_amount=50000,
				threshold_crossed_on=date(2026, 7, 20),
				ageing_days=19,
			),
		]
		for c in cycles:
			FakeCycleDoc.store[c["name"]] = dict(c)

		def get_doc(dt, name=None):
			if isinstance(dt, dict):
				return FakeCycleDoc(dt)
			return FakeCycleDoc(FakeCycleDoc.store[name])

		with patch.object(notify.frappe, "get_doc", side_effect=get_doc):
			out = notify.send_unbilled_alert_batch(_settings(), cycles=cycles, today=date(2026, 8, 8))

		self.assertTrue(out["email_sent"])
		self.assertEqual(out["alerts_sent"], 3)
		notify.frappe.sendmail.assert_called_once()
		kwargs = notify.frappe.sendmail.call_args.kwargs
		self.assertEqual(
			kwargs["subject"],
			"Project-wise Unbilled Expense Alert – 08 Aug 2026",
		)
		self.assertEqual(kwargs["recipients"], ["dir@nave.com"])
		msg = kwargs["message"]
		for col in [
			"Project ID",
			"Project Name",
			"Customer",
			"Unbilled Expense Amount",
			"Threshold Crossed Date",
			"Ageing Days",
			"Last Sales Invoice Date",
			"Project Status",
		]:
			self.assertIn(col, msg)
		# Sort: ageing desc -> PROJ-C first, then among age=7 unbilled desc -> PROJ-A then PROJ-B
		pos_c = msg.find("PROJ-C")
		pos_a = msg.find("PROJ-A")
		pos_b = msg.find("PROJ-B")
		self.assertTrue(pos_c < pos_a < pos_b)
		self.assertIn("Alert-eligible projects:</b> 3", msg)

	def test_email_failure_keeps_alert_sent_false(self):
		cycles = [_cycle()]
		FakeCycleDoc.store["NPUA-1"] = _cycle()
		notify.frappe.sendmail.side_effect = RuntimeError("SMTP down")

		def get_doc(dt, name=None):
			if isinstance(dt, dict):
				return FakeCycleDoc(dt)
			return FakeCycleDoc(FakeCycleDoc.store[name])

		with patch.object(notify.frappe, "get_doc", side_effect=get_doc):
			out = notify.send_unbilled_alert_batch(_settings(), cycles=cycles)
		self.assertEqual(out["alerts_sent"], 0)
		self.assertEqual(FakeCycleDoc.store["NPUA-1"]["alert_sent"], 0)
		self.assertEqual(FakeCycleDoc.store["NPUA-1"]["alert_status"], "Pending")
		self.assertEqual(out["skipped_reason"], "email_send_failed")

	def test_successful_email_marks_alerted(self):
		cycles = [_cycle()]
		FakeCycleDoc.store["NPUA-1"] = _cycle()

		def get_doc(dt, name=None):
			if isinstance(dt, dict):
				return FakeCycleDoc(dt)
			return FakeCycleDoc(FakeCycleDoc.store[name])

		with patch.object(notify.frappe, "get_doc", side_effect=get_doc):
			out = notify.send_unbilled_alert_batch(_settings(), cycles=cycles)
		self.assertEqual(out["alerts_sent"], 1)
		row = FakeCycleDoc.store["NPUA-1"]
		self.assertEqual(row["alert_sent"], 1)
		self.assertEqual(row["alert_status"], "Alerted")
		self.assertIsNotNone(row["alert_sent_on"])

	def test_scheduler_rerun_does_not_resend(self):
		# Already alerted cycles are not eligible
		alerted = _cycle(alert_status="Alerted", alert_sent=1)
		out = notify.send_unbilled_alert_batch(_settings(), cycles=[alerted])
		self.assertEqual(out["skipped_reason"], "no_eligible_cycles")
		notify.frappe.sendmail.assert_not_called()

	def test_both_channels_disabled(self):
		out = notify.send_unbilled_alert_batch(
			_settings(send_email=0, create_in_app_notification=0),
			cycles=[_cycle()],
		)
		self.assertEqual(out["skipped_reason"], "both_channels_disabled")
		self.assertEqual(out["alerts_sent"], 0)
		notify.frappe.sendmail.assert_not_called()

	def test_recheck_prevents_stale_send(self):
		# Cycle becomes ineligible (below threshold) before mark
		stale = _cycle(current_unbilled_amount=1000)
		out = notify.send_unbilled_alert_batch(_settings(), cycles=[stale])
		self.assertEqual(out["skipped_reason"], "no_eligible_cycles")
		notify.frappe.sendmail.assert_not_called()


class TestInApp(unittest.TestCase):
	def setUp(self):
		FakeCycleDoc.store = {}
		notify.frappe.sendmail = MagicMock()
		self.inserted = []

	def _get_doc(self, dt, name=None):
		if isinstance(dt, dict):
			doc = FakeCycleDoc(dt)

			def insert(ignore_permissions=False):
				self.inserted.append(copy.deepcopy(doc._data))
				return doc

			doc.insert = insert
			if dt.get("doctype") != "Notification Log":
				FakeCycleDoc.store[doc.name] = doc._data
			return doc
		return FakeCycleDoc(FakeCycleDoc.store[name])

	def test_in_app_enabled_one_per_user(self):
		cycles = [
			_cycle(name="NPUA-1", project="P1"),
			_cycle(name="NPUA-2", project="P2", current_unbilled_amount=18000),
		]
		for c in cycles:
			FakeCycleDoc.store[c["name"]] = dict(c)

		with patch.object(notify.frappe, "get_doc", side_effect=self._get_doc), patch.object(
			notify,
			"_users_for_emails",
			return_value=[{"name": "director@nave.com", "email": "dir@nave.com"}],
		):
			out = notify.send_unbilled_alert_batch(
				_settings(send_email=0, create_in_app_notification=1),
				cycles=cycles,
			)
		self.assertEqual(out["alerts_sent"], 2)
		self.assertEqual(out["in_app_created"], 1)
		self.assertEqual(len(self.inserted), 1)
		self.assertEqual(self.inserted[0]["doctype"], "Notification Log")
		self.assertEqual(self.inserted[0]["subject"], "Project Unbilled Expense Alert")
		self.assertIn("2 project", self.inserted[0]["email_content"])

	def test_disabled_user_skipped(self):
		# _users_for_emails filters enabled=1; empty means no in-app
		cycles = [_cycle()]
		FakeCycleDoc.store["NPUA-1"] = _cycle()
		with patch.object(notify.frappe, "get_doc", side_effect=self._get_doc), patch.object(
			notify, "_users_for_emails", return_value=[]
		):
			out = notify.send_unbilled_alert_batch(
				_settings(send_email=0, create_in_app_notification=1),
				cycles=cycles,
			)
		self.assertEqual(out["alerts_sent"], 0)
		self.assertEqual(out["skipped_reason"], "in_app_failed")

	def test_in_app_failure_after_email_still_marks_sent(self):
		cycles = [_cycle()]
		FakeCycleDoc.store["NPUA-1"] = _cycle()

		def boom_in_app(*a, **k):
			return {"created": 0, "failed": 1, "errors": [{"user": "u", "error": "fail"}]}

		with patch.object(notify.frappe, "get_doc", side_effect=self._get_doc), patch.object(
			notify, "create_in_app_unbilled_notifications", side_effect=boom_in_app
		):
			out = notify.send_unbilled_alert_batch(
				_settings(send_email=1, create_in_app_notification=1),
				cycles=cycles,
			)
		self.assertTrue(out["email_sent"])
		self.assertEqual(out["alerts_sent"], 1)
		self.assertEqual(FakeCycleDoc.store["NPUA-1"]["alert_status"], "Alerted")


class TestUsersForEmails(unittest.TestCase):
	def test_skips_disabled_users(self):
		users = [
			{"name": "enabled@x.com", "email": "dir@nave.com"},
		]
		with patch.object(notify.frappe, "get_all", return_value=users) as ga:
			# Simulate filter enabled=1 already applied by get_all
			matched = notify._users_for_emails(["dir@nave.com", "other@x.com"])
		self.assertEqual(len(matched), 1)
		self.assertEqual(ga.call_args.kwargs.get("filters") or ga.call_args[1].get("filters"), {"enabled": 1})


class TestDailyIntegration(unittest.TestCase):
	def test_daily_calls_notify_after_evaluate(self):
		summary = {
			"evaluated": 1,
			"opened": 1,
			"refreshed": 0,
			"resolved": 0,
			"eligible_for_alert": 1,
			"alerts_sent": 0,
			"skipped": 0,
			"errors": [],
			"noop": 0,
		}
		with patch.object(cycle, "load_unbilled_alert_settings", return_value=_settings()), patch.object(
			cycle, "evaluate_all_project_unbilled_alerts", return_value=summary
		), patch(
			"project_custom.project_unbilled_alert_notify.send_unbilled_alert_batch",
			return_value={"alerts_sent": 2, "errors": []},
		) as batch:
			out = cycle.run_project_unbilled_alert_daily()
		batch.assert_called_once()
		self.assertEqual(out["alerts_sent"], 2)


if __name__ == "__main__":
	unittest.main()
