"""Step 7 — Full integration + safety tests for Project Unbilled Expense Alert.

No business-rule changes. Exercises Step 3–6 modules end-to-end with fakes.
"""

from __future__ import annotations

import copy
import importlib
import json
import sys
import types
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, call, patch

WORKSPACE = Path(__file__).resolve().parents[2]
if str(WORKSPACE) not in sys.path:
	sys.path.insert(0, str(WORKSPACE))


def _install_fake_frappe():
	if "frappe" in sys.modules and hasattr(sys.modules["frappe"], "_unbilled_step7_stub"):
		return sys.modules["frappe"]

	frappe = types.ModuleType("frappe")
	frappe._unbilled_step7_stub = True
	frappe.session = types.SimpleNamespace(user="Administrator")
	frappe.PermissionError = type("PermissionError", (Exception,), {})
	frappe.ValidationError = type("ValidationError", (Exception,), {})
	frappe.DuplicateEntryError = type("DuplicateEntryError", (Exception,), {})
	frappe.flags = types.SimpleNamespace(mute_emails=False)
	frappe.local = types.SimpleNamespace()
	frappe.log_error = MagicMock()
	frappe.sendmail = MagicMock()
	frappe._ = lambda s: s
	frappe._dict = dict
	frappe.get_roles = lambda user=None: ["System Manager"]

	def throw(msg, exc=None):
		raise (exc or Exception)(msg)

	frappe.throw = throw
	frappe.whitelist = lambda *a, **k: (lambda fn: fn)
	frappe.db = types.SimpleNamespace(
		sql=lambda *a, **k: [],
		get_value=lambda *a, **k: None,
		get_single_value=lambda *a, **k: None,
		exists=lambda *a, **k: False,
	)
	frappe.get_all = lambda *a, **k: []
	frappe.get_single = lambda *a, **k: types.SimpleNamespace(
		enabled=1,
		threshold_amount=10000,
		ageing_days=5,
		director_emails="dir@nave.com",
		send_email=1,
		create_in_app_notification=1,
	)
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

	def get_datetime(d):
		if d is None or d == "":
			return None
		if isinstance(d, datetime):
			return d
		if isinstance(d, date):
			return datetime(d.year, d.month, d.day)
		s = str(d)
		if " " in s:
			return datetime.fromisoformat(s.replace("Z", ""))
		return datetime.fromisoformat(s[:10])

	def formatdate(d, df=None):
		d = getdate(d)
		if not d:
			return ""
		if df == "dd MMM yyyy":
			return d.strftime("%d %b %Y")
		return d.isoformat()

	def fmt_money(amount, currency=None):
		return f"{currency or 'INR'} {flt(amount):,.2f}"

	def validate_email_address(email, throw=False):
		if not email or "@" not in str(email):
			if throw:
				frappe.throw(f"Invalid email: {email}")
			return None
		return str(email).strip()

	def escape_html(s):
		return (
			str(s)
			.replace("&", "&amp;")
			.replace("<", "&lt;")
			.replace(">", "&gt;")
		)

	utils.flt = flt
	utils.cint = cint
	utils.getdate = getdate
	utils.get_datetime = get_datetime
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

from project_custom import project_unbilled_alert as eng  # noqa: E402
from project_custom import project_unbilled_alert_cycle as cycle  # noqa: E402
from project_custom import project_unbilled_alert_notify as notify  # noqa: E402
from project_custom import project_unbilled_alert_report as rpt  # noqa: E402

APP = WORKSPACE / "project_custom"
DOCTYPE_ROOT = APP / "project_custom" / "doctype"
REPORT_DIR = (
	APP / "project_custom" / "report" / "nave_project_unbilled_expense_alert"
)
HOOKS = APP / "hooks.py"
PATCHES = APP / "patches.txt"
SETTINGS_PY = (
	DOCTYPE_ROOT
	/ "nave_project_unbilled_alert_settings"
	/ "nave_project_unbilled_alert_settings.py"
)


def _load_settings_module():
	import importlib.util

	spec = importlib.util.spec_from_file_location(
		"nave_project_unbilled_alert_settings_step7", SETTINGS_PY
	)
	mod = importlib.util.module_from_spec(spec)
	spec.loader.exec_module(mod)
	return mod


def _ev(day, source_type, name, expense=0.0, billing=0.0, creation=None, row="r1"):
	d = day if isinstance(day, date) else date.fromisoformat(day)
	return {
		"date": d,
		"creation": creation or datetime(d.year, d.month, d.day, 10, 0, 0),
		"source_type": source_type,
		"source_name": name,
		"row_name": row,
		"project": "PROJ-1",
		"company": "Nave",
		"expense_delta": expense,
		"billing_delta": billing,
	}


def _settings(**kwargs):
	base = {
		"enabled": 1,
		"threshold_amount": 10000,
		"ageing_days": 5,
		"director_emails": "dir@nave.com",
		"send_email": 1,
		"create_in_app_notification": 1,
	}
	base.update(kwargs)
	return base


class FakeAlertDoc:
	store: dict = {}
	_seq = 0

	def __init__(self, data):
		FakeAlertDoc._seq += 1
		self._data = dict(data)
		self.name = data.get("name") or f"NPUA-I-{FakeAlertDoc._seq}"
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

	def insert(self, ignore_permissions=False):
		store = FakeAlertDoc.store
		if self.alert_status in ("Pending", "Alerted") and not self.resolved_on:
			for row in store.values():
				if (
					row["project"] == self.project
					and row["company"] == self.company
					and row["alert_status"] in ("Pending", "Alerted")
					and not row.get("resolved_on")
				):
					raise Exception("duplicate active cycle")
		store[self.name] = copy.deepcopy(self._data)
		return self

	def save(self):
		FakeAlertDoc.store[self.name] = copy.deepcopy(self._data)
		return self

	def as_dict(self):
		return copy.deepcopy(self._data)


def _reset_store():
	FakeAlertDoc.store = {}
	FakeAlertDoc._seq = 0


def _patch_cycle_db():
	def get_doc(arg, name=None):
		if isinstance(arg, dict):
			return FakeAlertDoc(arg)
		if name not in FakeAlertDoc.store:
			raise Exception(f"Missing {name}")
		return FakeAlertDoc(FakeAlertDoc.store[name])

	def sql(query, args=None, as_dict=False):
		q = " ".join(query.split()).lower()
		rows = list(FakeAlertDoc.store.values())
		if "max(cycle_no)" in q:
			project, company = args
			mx = 0
			for r in rows:
				if r["project"] == project and r["company"] == company:
					mx = max(mx, int(r.get("cycle_no") or 0))
			return ((mx,),)
		if "from `tabnave project unbilled alert`" in q and "alert_status in" in q:
			project, company = args[0], args[1]
			matches = [
				r
				for r in rows
				if r["project"] == project
				and r["company"] == company
				and r.get("alert_status") in ("Pending", "Alerted")
				and not r.get("resolved_on")
			]
			matches.sort(key=lambda r: int(r.get("cycle_no") or 0), reverse=True)
			if as_dict:
				return matches[:1]
			return matches[:1] if matches else []
		return [] if as_dict else []

	return (
		patch.object(cycle.frappe, "get_doc", side_effect=get_doc),
		patch.object(cycle.frappe.db, "sql", side_effect=sql),
		patch.object(notify.frappe, "get_doc", side_effect=get_doc),
	)


def _snap_from_events(events, project="PROJ-1", company="Nave", status="Open", **extra):
	totals = eng.calculate_current_totals(events)
	threshold = 10000
	return {
		"project": project,
		"project_name": extra.get("project_name", "Job"),
		"company": company,
		"customer": extra.get("customer", "Cust"),
		"project_status": status,
		"expense_amount": totals["expense_amount"],
		"billed_amount": totals["billed_amount"],
		"unbilled_amount": totals["unbilled_amount"],
		"threshold_crossed_on": eng.calculate_threshold_crossed_on(events, threshold),
		"last_sales_invoice_date": eng.get_last_sales_invoice_date(events),
		"currency": extra.get("currency", "INR"),
		"threshold_amount": threshold,
		"skipped": extra.get("skipped", False),
		"skip_reason": extra.get("skip_reason"),
	}


# ---------------------------------------------------------------------------
# Scenario A–E: threshold, ageing, billing resolve, re-cross
# ---------------------------------------------------------------------------


class TestScenarioThresholdAgeingResolveRecross(unittest.TestCase):
	def setUp(self):
		_reset_store()
		self.settings = _settings()
		self.base_events = [
			_ev("2026-08-01", eng.SOURCE_PI, "PI-1", expense=4000),
			_ev("2026-08-02", eng.SOURCE_PI, "PI-2", expense=3000),
			_ev("2026-08-03", eng.SOURCE_PI, "PI-3", expense=5000),
		]

	def test_scenario_a_threshold_cross(self):
		snap = _snap_from_events(self.base_events)
		self.assertEqual(snap["expense_amount"], 12000)
		self.assertEqual(snap["billed_amount"], 0)
		self.assertEqual(snap["unbilled_amount"], 12000)
		self.assertEqual(snap["threshold_crossed_on"], date(2026, 8, 3))
		self.assertEqual(
			cycle.calculate_ageing_days(snap["threshold_crossed_on"], today=date(2026, 8, 3)),
			0,
		)

		p1, p2, p3 = _patch_cycle_db()
		with p1, p2, p3, patch.object(
			cycle, "get_project_unbilled_snapshot", return_value=snap
		):
			out = cycle.evaluate_project_unbilled_alert("PROJ-1", self.settings, today=date(2026, 8, 3))
		self.assertEqual(out["action"], "opened")
		row = next(iter(FakeAlertDoc.store.values()))
		self.assertEqual(row["alert_status"], "Pending")
		self.assertEqual(row["threshold_crossed_on"], date(2026, 8, 3))
		self.assertEqual(row["alert_sent"], 0)

	def test_scenario_ageing_eligibility_day_5(self):
		crossed = date(2026, 8, 3)
		for day, age in [
			(date(2026, 8, 4), 1),
			(date(2026, 8, 5), 2),
			(date(2026, 8, 6), 3),
			(date(2026, 8, 7), 4),
			(date(2026, 8, 8), 5),
		]:
			self.assertEqual(cycle.calculate_ageing_days(crossed, today=day), age)

		c = {
			"alert_status": "Pending",
			"alert_sent": 0,
			"current_unbilled_amount": 12000,
			"threshold_amount": 10000,
			"threshold_crossed_on": crossed,
		}
		self.assertFalse(
			cycle.is_cycle_alert_eligible(c, today=date(2026, 8, 7), ageing_threshold=5)
		)
		self.assertTrue(
			cycle.is_cycle_alert_eligible(c, today=date(2026, 8, 8), ageing_threshold=5)
		)

	def test_scenario_billing_before_day_5_resolves(self):
		events = self.base_events + [
			_ev("2026-08-07", eng.SOURCE_SI, "SI-1", billing=5000),
		]
		snap = _snap_from_events(events)
		self.assertEqual(snap["unbilled_amount"], 7000)
		self.assertIsNone(snap["threshold_crossed_on"])

		# Open first while above threshold
		open_snap = _snap_from_events(self.base_events)
		p1, p2, p3 = _patch_cycle_db()
		with p1, p2, p3, patch.object(
			cycle, "get_project_unbilled_snapshot", return_value=open_snap
		):
			cycle.evaluate_project_unbilled_alert("PROJ-1", self.settings, today=date(2026, 8, 3))
		name = next(iter(FakeAlertDoc.store))
		crossed = FakeAlertDoc.store[name]["threshold_crossed_on"]

		with p1, p2, p3, patch.object(
			cycle, "get_project_unbilled_snapshot", return_value=snap
		):
			out = cycle.evaluate_project_unbilled_alert("PROJ-1", self.settings, today=date(2026, 8, 7))
		self.assertEqual(out["action"], "resolved")
		row = FakeAlertDoc.store[name]
		self.assertEqual(row["alert_status"], "Resolved")
		self.assertEqual(row["alert_sent"], 0)
		self.assertEqual(row["threshold_crossed_on"], crossed)
		self.assertIsNotNone(row["resolved_on"])
		# Not eligible for email
		self.assertFalse(
			cycle.is_cycle_alert_eligible(row, today=date(2026, 8, 8), ageing_threshold=5)
		)

	def test_scenario_recross_new_cycle(self):
		# Resolve then re-cross
		events_open = self.base_events
		events_resolved = events_open + [_ev("2026-08-07", eng.SOURCE_SI, "SI-1", billing=5000)]
		events_recross = events_resolved + [
			_ev("2026-08-10", eng.SOURCE_PI, "PI-4", expense=6000),
		]
		p1, p2, p3 = _patch_cycle_db()
		with p1, p2, p3, patch.object(
			cycle,
			"get_project_unbilled_snapshot",
			return_value=_snap_from_events(events_open),
		):
			cycle.evaluate_project_unbilled_alert("PROJ-1", self.settings)
		name1 = next(iter(FakeAlertDoc.store))

		with p1, p2, p3, patch.object(
			cycle,
			"get_project_unbilled_snapshot",
			return_value=_snap_from_events(events_resolved),
		):
			cycle.evaluate_project_unbilled_alert("PROJ-1", self.settings)

		recross_snap = _snap_from_events(events_recross)
		self.assertEqual(recross_snap["unbilled_amount"], 13000)
		self.assertEqual(recross_snap["threshold_crossed_on"], date(2026, 8, 10))

		with p1, p2, p3, patch.object(
			cycle, "get_project_unbilled_snapshot", return_value=recross_snap
		):
			out = cycle.evaluate_project_unbilled_alert("PROJ-1", self.settings)
		self.assertEqual(out["action"], "opened")
		self.assertEqual(out["cycle_no"], 2)
		self.assertEqual(FakeAlertDoc.store[name1]["alert_status"], "Resolved")
		self.assertEqual(FakeAlertDoc.store[name1]["cycle_no"], 1)
		active = [
			r
			for r in FakeAlertDoc.store.values()
			if r["alert_status"] == "Pending" and not r.get("resolved_on")
		]
		self.assertEqual(len(active), 1)
		self.assertEqual(active[0]["threshold_crossed_on"], date(2026, 8, 10))
		self.assertEqual(active[0]["alert_sent"], 0)


# ---------------------------------------------------------------------------
# Email batch + multi-project + idempotency
# ---------------------------------------------------------------------------


class TestEmailAndIdempotency(unittest.TestCase):
	def setUp(self):
		_reset_store()
		notify.frappe.sendmail = MagicMock()

	def test_day5_email_marks_alerted_once(self):
		cycles = [
			{
				"name": "NPUA-1",
				"project": "PROJ-1",
				"project_name": "One",
				"customer": "C1",
				"company": "Nave",
				"current_unbilled_amount": 12000,
				"threshold_amount": 10000,
				"threshold_crossed_on": date(2026, 8, 3),
				"ageing_days": 5,
				"last_sales_invoice_date": None,
				"project_status": "Open",
				"alert_status": "Pending",
				"alert_sent": 0,
				"resolved_on": None,
				"cycle_no": 1,
			}
		]
		FakeAlertDoc.store["NPUA-1"] = dict(cycles[0])
		p1, p2, p3 = _patch_cycle_db()
		with p1, p2, p3:
			out1 = notify.send_unbilled_alert_batch(
				_settings(create_in_app_notification=0),
				cycles=cycles,
				today=date(2026, 8, 8),
			)
			out2 = notify.send_unbilled_alert_batch(
				_settings(create_in_app_notification=0),
				cycles=[dict(FakeAlertDoc.store["NPUA-1"])],
				today=date(2026, 8, 8),
			)
		self.assertEqual(out1["alerts_sent"], 1)
		self.assertEqual(FakeAlertDoc.store["NPUA-1"]["alert_status"], "Alerted")
		self.assertEqual(FakeAlertDoc.store["NPUA-1"]["alert_sent"], 1)
		self.assertIsNotNone(FakeAlertDoc.store["NPUA-1"]["alert_sent_on"])
		self.assertEqual(out2["alerts_sent"], 0)
		self.assertEqual(out2["skipped_reason"], "no_eligible_cycles")
		self.assertEqual(notify.frappe.sendmail.call_count, 1)

	def test_multi_project_one_email_sorted(self):
		cycles = [
			{
				"name": "N1",
				"project": "PROJ-B",
				"project_name": "Beta",
				"customer": "CB",
				"current_unbilled_amount": 12000,
				"threshold_amount": 10000,
				"threshold_crossed_on": date(2026, 8, 1),
				"ageing_days": 7,
				"last_sales_invoice_date": date(2026, 7, 1),
				"project_status": "Open",
				"alert_status": "Pending",
				"alert_sent": 0,
				"resolved_on": None,
			},
			{
				"name": "N2",
				"project": "PROJ-A",
				"project_name": "Alpha",
				"customer": "CA",
				"current_unbilled_amount": 20000,
				"threshold_amount": 10000,
				"threshold_crossed_on": date(2026, 8, 1),
				"ageing_days": 7,
				"last_sales_invoice_date": None,
				"project_status": "Completed",
				"alert_status": "Pending",
				"alert_sent": 0,
				"resolved_on": None,
			},
			{
				"name": "N3",
				"project": "PROJ-C",
				"project_name": "Gamma",
				"customer": "CG",
				"current_unbilled_amount": 50000,
				"threshold_amount": 10000,
				"threshold_crossed_on": date(2026, 7, 20),
				"ageing_days": 19,
				"last_sales_invoice_date": date(2026, 7, 10),
				"project_status": "Open",
				"alert_status": "Pending",
				"alert_sent": 0,
				"resolved_on": None,
			},
		]
		for c in cycles:
			FakeAlertDoc.store[c["name"]] = dict(c)
		p1, p2, p3 = _patch_cycle_db()
		with p1, p2, p3:
			out = notify.send_unbilled_alert_batch(
				_settings(create_in_app_notification=0),
				cycles=cycles,
				today=date(2026, 8, 8),
			)
		self.assertEqual(out["alerts_sent"], 3)
		self.assertEqual(notify.frappe.sendmail.call_count, 1)
		msg = notify.frappe.sendmail.call_args.kwargs["message"]
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
		self.assertTrue(msg.find("PROJ-C") < msg.find("PROJ-A") < msg.find("PROJ-B"))

	def test_email_failure_no_sent_in_app_fail_after_email_ok(self):
		cycles = [
			{
				"name": "NPUA-1",
				"project": "P1",
				"project_name": "P",
				"customer": "C",
				"current_unbilled_amount": 15000,
				"threshold_amount": 10000,
				"threshold_crossed_on": date(2026, 8, 1),
				"ageing_days": 7,
				"last_sales_invoice_date": None,
				"project_status": "Open",
				"alert_status": "Pending",
				"alert_sent": 0,
				"resolved_on": None,
			}
		]
		FakeAlertDoc.store["NPUA-1"] = dict(cycles[0])
		notify.frappe.sendmail.side_effect = RuntimeError("SMTP")
		p1, p2, p3 = _patch_cycle_db()
		with p1, p2, p3:
			out = notify.send_unbilled_alert_batch(
				_settings(create_in_app_notification=0), cycles=cycles
			)
		self.assertEqual(out["alerts_sent"], 0)
		self.assertEqual(FakeAlertDoc.store["NPUA-1"]["alert_sent"], 0)

		notify.frappe.sendmail.side_effect = None
		notify.frappe.sendmail.reset_mock()
		with p1, p2, p3, patch.object(
			notify,
			"create_in_app_unbilled_notifications",
			return_value={"created": 0, "failed": 1, "errors": [{"e": "x"}]},
		):
			out2 = notify.send_unbilled_alert_batch(
				_settings(send_email=1, create_in_app_notification=1),
				cycles=[dict(FakeAlertDoc.store["NPUA-1"])],
			)
		self.assertEqual(out2["alerts_sent"], 1)
		self.assertEqual(FakeAlertDoc.store["NPUA-1"]["alert_status"], "Alerted")


# ---------------------------------------------------------------------------
# Completed project, currency skip, settings, PI/JE/SI query contracts
# ---------------------------------------------------------------------------


class TestCompletedCurrencySettingsQueries(unittest.TestCase):
	def setUp(self):
		_reset_store()

	def test_completed_project_evaluated_and_reportable(self):
		snap = _snap_from_events(
			[_ev("2026-08-01", eng.SOURCE_PI, "PI", expense=15000)],
			status="Completed",
			project_name="Done Job",
		)
		p1, p2, p3 = _patch_cycle_db()
		with p1, p2, p3, patch.object(
			cycle, "get_project_unbilled_snapshot", return_value=snap
		):
			out = cycle.evaluate_project_unbilled_alert("PROJ-1", _settings())
		self.assertEqual(out["action"], "opened")
		row = next(iter(FakeAlertDoc.store.values()))
		self.assertEqual(row["project_status"], "Completed")

		def fake_get_all(doctype, filters=None, fields=None):
			return [dict(row)]

		with patch.object(rpt.frappe, "get_all", side_effect=fake_get_all), patch.object(
			rpt, "assert_unbilled_alert_report_access"
		):
			data = rpt.fetch_unbilled_alert_report_rows({}, today=date(2026, 8, 8))
		self.assertEqual(len(data), 1)
		self.assertEqual(data[0]["project_status"], "Completed")

	def test_non_inr_skipped_no_cycle_no_email(self):
		snap = _snap_from_events(
			[],
			currency="USD",
			skipped=True,
			skip_reason="Company currency is USD; V1 threshold comparison is INR-only.",
		)
		snap["unbilled_amount"] = 0
		p1, p2, p3 = _patch_cycle_db()
		with p1, p2, p3, patch.object(
			cycle, "get_project_unbilled_snapshot", return_value=snap
		):
			out = cycle.evaluate_project_unbilled_alert("PROJ-USD", _settings())
		self.assertEqual(out["action"], "skipped")
		self.assertEqual(FakeAlertDoc.store, {})
		notify.frappe.sendmail = MagicMock()
		batch = notify.send_unbilled_alert_batch(_settings(), cycles=[])
		self.assertEqual(batch["skipped_reason"], "no_eligible_cycles")
		notify.frappe.sendmail.assert_not_called()

	def test_settings_disabled_and_no_recipients_and_channels_off(self):
		with patch.object(
			cycle, "load_unbilled_alert_settings", return_value=_settings(enabled=0)
		), patch.object(cycle, "evaluate_all_project_unbilled_alerts") as ev:
			summary = cycle.run_project_unbilled_alert_daily()
		ev.assert_not_called()
		self.assertEqual(summary["skipped_reason"], "settings_disabled")

		out = notify.send_unbilled_alert_batch(
			_settings(director_emails="not-an-email"),
			cycles=[
				{
					"name": "X",
					"project": "P",
					"alert_status": "Pending",
					"alert_sent": 0,
					"current_unbilled_amount": 20000,
					"threshold_amount": 10000,
					"threshold_crossed_on": date(2026, 8, 1),
					"resolved_on": None,
				}
			],
		)
		self.assertEqual(out["skipped_reason"], "no_valid_recipients")
		self.assertEqual(out["alerts_sent"], 0)

		out2 = notify.send_unbilled_alert_batch(
			_settings(send_email=0, create_in_app_notification=0),
			cycles=[],
		)
		self.assertEqual(out2["skipped_reason"], "both_channels_disabled")

	def test_email_normalization(self):
		# Soft parser for delivery
		parsed = notify.parse_director_recipient_emails(
			"a@x.com, b@y.com\na@x.com; bad"
		)
		self.assertEqual(parsed["valid"], ["a@x.com", "b@y.com"])
		self.assertEqual(parsed["invalid"], ["bad"])
		# Settings normalize (throws on invalid) — valid path
		norm = _load_settings_module().normalize_director_emails(
			"c@z.com, C@z.com\nd@z.com"
		)
		self.assertEqual(norm, "c@z.com\nd@z.com")

	def test_pi_je_si_query_contracts(self):
		captured = []

		def fake_sql(query, args=None, as_dict=False):
			captured.append(" ".join(query.split()))
			return []

		with patch.object(eng.frappe.db, "sql", side_effect=fake_sql):
			eng.get_purchase_invoice_events("PROJ-1", "Nave")
			eng.get_journal_expense_events("PROJ-1", "Nave")
			eng.get_sales_invoice_events("PROJ-1", "Nave")

		pi, je, si_item, si_hdr = captured
		self.assertIn("pii.project = %s", pi)
		self.assertIn("pi.docstatus = 1", pi)
		self.assertNotIn("AND pi.project = %s", pi)
		self.assertIn("jea.project = %s", je)
		self.assertIn("acc.root_type = 'Expense'", je)
		self.assertIn("(jea.debit - jea.credit)", je)
		self.assertNotIn("AND je.project = %s", je)
		self.assertIn("sii.project = %s", si_item)
		self.assertIn("si.project = %s", si_hdr)
		self.assertIn("(sii.project IS NULL OR sii.project = '')", si_hdr)

	def test_backdated_threshold_recalc(self):
		base = [
			_ev("2026-08-05", eng.SOURCE_PI, "P1", expense=6000),
			_ev("2026-08-06", eng.SOURCE_PI, "P2", expense=3000),
		]
		# 9000 <= 10000 → no cross yet
		self.assertIsNone(eng.calculate_threshold_crossed_on(base, 10000))
		with_backdate = base + [
			_ev("2026-08-04", eng.SOURCE_PI, "P0", expense=2000),
		]
		# Aug4 +2k=2000, Aug5 +6k=8000, Aug6 +3k=11000 → crossed Aug 6
		self.assertEqual(
			eng.calculate_threshold_crossed_on(with_backdate, 10000),
			date(2026, 8, 6),
		)
		# Backdated billing can reset the current cycle
		with_bill = with_backdate + [
			_ev("2026-08-05", eng.SOURCE_SI, "S1", billing=5000, row="s1"),
		]
		# Aug4 +2k=2000; Aug5 PI +6k=8000; Aug5 SI -5k=3000; Aug6 +3k=6000 → None
		self.assertIsNone(eng.calculate_threshold_crossed_on(with_bill, 10000))


# ---------------------------------------------------------------------------
# Permissions, scheduler, performance, migration safety
# ---------------------------------------------------------------------------


class TestPermissionsSchedulerPerfMigration(unittest.TestCase):
	def test_report_permissions(self):
		for role in [
			"System Manager",
			"Accounts Manager",
			"Projects Manager",
			"NAVE Task Director",
			"NAVE Task Manager",
		]:
			with patch.object(rpt.frappe, "get_roles", return_value=[role]), patch.object(
				rpt.frappe.session, "user", f"{role}@x.com"
			):
				rpt.assert_unbilled_alert_report_access()

		with patch.object(rpt.frappe, "get_roles", return_value=["Employee"]), patch.object(
			rpt.frappe.session, "user", "emp@x.com"
		):
			with self.assertRaises(rpt.frappe.PermissionError):
				rpt.assert_unbilled_alert_report_access()

	def test_scheduler_hook_and_summary_and_isolation(self):
		hooks = HOOKS.read_text(encoding="utf-8")
		needle = "project_custom.project_unbilled_alert_cycle.run_project_unbilled_alert_daily"
		self.assertEqual(hooks.count(needle), 1)

		# Import path exists
		mod = importlib.import_module("project_custom.project_unbilled_alert_cycle")
		self.assertTrue(callable(mod.run_project_unbilled_alert_daily))

		projects = [{"name": f"P-{i}"} for i in range(100)]
		projects[7] = {"name": "BROKEN"}
		settings_loads = {"n": 0}
		orig_load = cycle.load_unbilled_alert_settings

		def counting_load():
			settings_loads["n"] += 1
			return _settings()

		def fake_eval(project, settings=None, today=None):
			# settings must be passed from batch (not reloaded per project)
			self.assertIsNotNone(settings)
			if project == "BROKEN":
				raise RuntimeError("boom")
			return {"action": "noop", "eligible_for_alert": False}

		with patch.object(cycle, "get_all_projects_for_evaluation", return_value=projects), patch.object(
			cycle, "evaluate_project_unbilled_alert", side_effect=fake_eval
		), patch.object(cycle, "load_unbilled_alert_settings", side_effect=counting_load):
			# evaluate_all loads settings once if not passed — pass explicitly
			summary = cycle.evaluate_all_project_unbilled_alerts(settings=_settings())
		self.assertEqual(summary["evaluated"], 99)
		self.assertEqual(len(summary["errors"]), 1)
		for key in [
			"evaluated",
			"opened",
			"refreshed",
			"resolved",
			"eligible_for_alert",
			"alerts_sent",
			"skipped",
			"errors",
		]:
			self.assertIn(key, summary)
		# settings not reloaded inside evaluate_all when passed
		self.assertEqual(settings_loads["n"], 0)

		# Daily path loads settings once
		settings_loads["n"] = 0
		with patch.object(cycle, "load_unbilled_alert_settings", side_effect=counting_load), patch.object(
			cycle, "evaluate_all_project_unbilled_alerts", return_value=summary
		) as ev, patch(
			"project_custom.project_unbilled_alert_notify.send_unbilled_alert_batch",
			return_value={"alerts_sent": 0, "errors": []},
		):
			cycle.run_project_unbilled_alert_daily()
		self.assertEqual(settings_loads["n"], 1)
		ev.assert_called_once()

	def test_report_single_get_all(self):
		calls = {"n": 0}

		def fake_get_all(*a, **k):
			calls["n"] += 1
			return []

		with patch.object(rpt.frappe, "get_all", side_effect=fake_get_all), patch.object(
			rpt, "assert_unbilled_alert_report_access"
		):
			rpt.execute_unbilled_alert_report({})
		self.assertEqual(calls["n"], 1)

	def test_migration_safety_artifacts(self):
		settings_json = (
			DOCTYPE_ROOT
			/ "nave_project_unbilled_alert_settings"
			/ "nave_project_unbilled_alert_settings.json"
		)
		alert_json = (
			DOCTYPE_ROOT / "nave_project_unbilled_alert" / "nave_project_unbilled_alert.json"
		)
		report_json = REPORT_DIR / "nave_project_unbilled_expense_alert.json"
		for path in (settings_json, alert_json, report_json):
			self.assertTrue(path.is_file(), path)

		settings = json.loads(settings_json.read_text(encoding="utf-8"))
		alert = json.loads(alert_json.read_text(encoding="utf-8"))
		report = json.loads(report_json.read_text(encoding="utf-8"))
		self.assertEqual(settings["issingle"], 1)
		self.assertEqual(settings["name"], "NAVE Project Unbilled Alert Settings")
		self.assertEqual(alert["name"], "NAVE Project Unbilled Alert")
		self.assertEqual(report["report_type"], "Script Report")
		self.assertEqual(report["ref_doctype"], "NAVE Project Unbilled Alert")

		# Import paths resolve
		for modname in [
			"project_custom.project_unbilled_alert",
			"project_custom.project_unbilled_alert_cycle",
			"project_custom.project_unbilled_alert_notify",
			"project_custom.project_unbilled_alert_report",
			"project_custom.project_custom.report.nave_project_unbilled_expense_alert.nave_project_unbilled_expense_alert",
		]:
			importlib.import_module(modname)

		# patches.txt exists (may be empty / unrelated) — no broken unbilled patches required
		self.assertTrue(PATCHES.is_file())
		patches = PATCHES.read_text(encoding="utf-8")
		# No unbilled-specific patch required for V1 DocType sync via migrate
		self.assertNotIn("nave_project_unbilled", patches.lower())

	def test_get_all_projects_no_status_filter(self):
		captured = {}

		def fake_get_all(doctype, fields=None, filters=None, order_by=None):
			captured["filters"] = filters
			return [{"name": "X", "status": "Completed"}]

		with patch.object(eng.frappe, "get_all", side_effect=fake_get_all):
			rows = eng.get_all_projects_for_evaluation()
		self.assertIsNone(captured["filters"])
		self.assertEqual(rows[0]["status"], "Completed")


if __name__ == "__main__":
	unittest.main()
