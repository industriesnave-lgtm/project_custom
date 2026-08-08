"""Step 4 — Unbilled alert cycle engine + daily scheduler (no email)."""

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
	if "frappe" in sys.modules and hasattr(sys.modules["frappe"], "_unbilled_cycle_stub"):
		return sys.modules["frappe"]

	frappe = types.ModuleType("frappe")
	frappe._unbilled_cycle_stub = True
	frappe.session = types.SimpleNamespace(user="Administrator")
	frappe.ValidationError = type("ValidationError", (Exception,), {})
	frappe.DuplicateEntryError = type("DuplicateEntryError", (Exception,), {})
	frappe.PermissionError = type("PermissionError", (Exception,), {})

	def throw(msg, exc=None):
		raise (exc or Exception)(msg)

	frappe.throw = throw
	frappe.whitelist = lambda *a, **k: (lambda fn: fn)
	frappe.flags = types.SimpleNamespace()
	frappe.local = types.SimpleNamespace()
	frappe.log_error = MagicMock()
	frappe.db = types.SimpleNamespace(
		sql=lambda *a, **k: [],
		get_value=lambda *a, **k: None,
		get_single_value=lambda *a, **k: None,
		exists=lambda *a, **k: False,
		set_value=lambda *a, **k: None,
	)
	frappe.get_all = lambda *a, **k: []
	frappe.get_single = lambda *a, **k: types.SimpleNamespace(
		enabled=1,
		threshold_amount=10000,
		ageing_days=5,
		director_emails="",
		send_email=0,
		create_in_app_notification=0,
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

	utils.flt = flt
	utils.cint = cint
	utils.getdate = getdate
	utils.get_datetime = get_datetime
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

HOOKS = WORKSPACE / "project_custom" / "hooks.py"
CYCLE_MOD = WORKSPACE / "project_custom" / "project_unbilled_alert_cycle.py"


class FakeAlertDoc:
	_seq = 0

	def __init__(self, data):
		FakeAlertDoc._seq += 1
		self._data = dict(data)
		self.name = data.get("name") or f"NPUA-TEST-{FakeAlertDoc._seq}"
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

	def insert(self):
		# Simulate DocType validate: one active cycle per project+company
		store = getattr(FakeAlertDoc, "store", {})
		if self.alert_status in ("Pending", "Alerted") and not self.resolved_on:
			for row in store.values():
				if (
					row["project"] == self.project
					and row["company"] == self.company
					and row["alert_status"] in ("Pending", "Alerted")
					and not row.get("resolved_on")
				):
					raise Exception(
						f"Project {self.project} already has an active unbilled alert cycle"
					)
		store[self.name] = copy.deepcopy(self._data)
		FakeAlertDoc.store = store
		return self

	def save(self):
		store = getattr(FakeAlertDoc, "store", {})
		store[self.name] = copy.deepcopy(self._data)
		FakeAlertDoc.store = store
		return self

	def as_dict(self):
		return copy.deepcopy(self._data)


def _reset_store():
	FakeAlertDoc.store = {}
	FakeAlertDoc._seq = 0


def _settings(**kwargs):
	base = {
		"enabled": 1,
		"threshold_amount": 10000,
		"ageing_days": 5,
		"director_emails": "",
		"send_email": 0,
		"create_in_app_notification": 0,
	}
	base.update(kwargs)
	return base


def _snap(**kwargs):
	base = {
		"project": "PROJ-1",
		"project_name": "Job",
		"company": "Nave",
		"customer": "Cust",
		"project_status": "Open",
		"expense_amount": 12000,
		"billed_amount": 0,
		"unbilled_amount": 12000,
		"threshold_crossed_on": date(2026, 8, 3),
		"last_sales_invoice_date": None,
		"currency": "INR",
		"threshold_amount": 10000,
		"skipped": False,
		"skip_reason": None,
	}
	base.update(kwargs)
	return base


def _patch_cycle_db():
	"""Wire get_doc / sql to FakeAlertDoc.store."""

	def get_doc(arg, name=None):
		if isinstance(arg, dict):
			return FakeAlertDoc(arg)
		store = FakeAlertDoc.store
		if name not in store:
			raise Exception(f"Missing {name}")
		return FakeAlertDoc(store[name])

	def sql(query, args=None, as_dict=False):
		q = " ".join(query.split()).lower()
		store = FakeAlertDoc.store
		rows = list(store.values())

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
			if "select name" in q and "name !=" in q:
				# validate path uses name !=
				exclude = args[2] if len(args) > 2 else ""
				matches = [m for m in matches if m["name"] != exclude]
				return [(matches[0]["name"],)] if matches else []
			return matches[:1] if matches else []

		return [] if as_dict else []

	return patch.object(cycle.frappe, "get_doc", side_effect=get_doc), patch.object(
		cycle.frappe.db, "sql", side_effect=sql
	)


class TestAgeingAndEligibility(unittest.TestCase):
	def test_ageing_day_zero(self):
		self.assertEqual(
			cycle.calculate_ageing_days(date(2026, 8, 8), today=date(2026, 8, 8)), 0
		)

	def test_ageing_day_five_eligibility(self):
		self.assertEqual(
			cycle.calculate_ageing_days(date(2026, 8, 3), today=date(2026, 8, 8)), 5
		)
		c = {
			"alert_status": "Pending",
			"alert_sent": 0,
			"current_unbilled_amount": 12000,
			"threshold_amount": 10000,
			"threshold_crossed_on": date(2026, 8, 3),
		}
		self.assertTrue(
			cycle.is_cycle_alert_eligible(c, today=date(2026, 8, 8), ageing_threshold=5)
		)

	def test_pending_unsent_required(self):
		c = {
			"alert_status": "Pending",
			"alert_sent": 1,
			"current_unbilled_amount": 12000,
			"threshold_amount": 10000,
			"threshold_crossed_on": date(2026, 8, 1),
		}
		self.assertFalse(
			cycle.is_cycle_alert_eligible(c, today=date(2026, 8, 8), ageing_threshold=5)
		)

	def test_alerted_not_newly_eligible(self):
		c = {
			"alert_status": "Alerted",
			"alert_sent": 1,
			"current_unbilled_amount": 12000,
			"threshold_amount": 10000,
			"threshold_crossed_on": date(2026, 8, 1),
		}
		self.assertFalse(
			cycle.is_cycle_alert_eligible(c, today=date(2026, 8, 8), ageing_threshold=5)
		)


class TestCycleEngine(unittest.TestCase):
	def setUp(self):
		_reset_store()
		self.settings = _settings()

	def test_below_threshold_creates_nothing(self):
		p1, p2 = _patch_cycle_db()
		with p1, p2, patch.object(
			cycle, "get_project_unbilled_snapshot", return_value=_snap(unbilled_amount=5000, expense_amount=5000, threshold_crossed_on=None)
		):
			out = cycle.evaluate_project_unbilled_alert("PROJ-1", self.settings)
		self.assertEqual(out["action"], "noop")
		self.assertEqual(FakeAlertDoc.store, {})

	def test_exactly_threshold_creates_nothing(self):
		p1, p2 = _patch_cycle_db()
		with p1, p2, patch.object(
			cycle,
			"get_project_unbilled_snapshot",
			return_value=_snap(
				unbilled_amount=10000,
				expense_amount=10000,
				threshold_crossed_on=None,
			),
		):
			out = cycle.evaluate_project_unbilled_alert("PROJ-1", self.settings)
		self.assertEqual(out["action"], "noop")
		self.assertEqual(len(FakeAlertDoc.store), 0)

	def test_above_threshold_creates_pending(self):
		p1, p2 = _patch_cycle_db()
		with p1, p2, patch.object(
			cycle, "get_project_unbilled_snapshot", return_value=_snap()
		):
			out = cycle.evaluate_project_unbilled_alert("PROJ-1", self.settings)
		self.assertEqual(out["action"], "opened")
		row = next(iter(FakeAlertDoc.store.values()))
		self.assertEqual(row["alert_status"], "Pending")
		self.assertEqual(row["cycle_no"], 1)
		self.assertEqual(row["threshold_crossed_on"], date(2026, 8, 3))
		self.assertEqual(row["alert_sent"], 0)

	def test_uses_ledger_crossed_date(self):
		p1, p2 = _patch_cycle_db()
		with p1, p2, patch.object(
			cycle,
			"get_project_unbilled_snapshot",
			return_value=_snap(threshold_crossed_on=date(2026, 7, 20)),
		):
			cycle.evaluate_project_unbilled_alert("PROJ-1", self.settings)
		row = next(iter(FakeAlertDoc.store.values()))
		self.assertEqual(row["threshold_crossed_on"], date(2026, 7, 20))

	def test_rerun_does_not_duplicate(self):
		p1, p2 = _patch_cycle_db()
		with p1, p2, patch.object(
			cycle, "get_project_unbilled_snapshot", return_value=_snap()
		):
			cycle.evaluate_project_unbilled_alert("PROJ-1", self.settings)
			out2 = cycle.evaluate_project_unbilled_alert("PROJ-1", self.settings)
		self.assertEqual(out2["action"], "refreshed")
		self.assertEqual(len(FakeAlertDoc.store), 1)

	def test_refresh_updates_amounts_preserves_alert_sent(self):
		p1, p2 = _patch_cycle_db()
		with p1, p2, patch.object(
			cycle, "get_project_unbilled_snapshot", return_value=_snap()
		):
			cycle.evaluate_project_unbilled_alert("PROJ-1", self.settings)
		name = next(iter(FakeAlertDoc.store))
		FakeAlertDoc.store[name]["alert_sent"] = 1
		FakeAlertDoc.store[name]["alert_sent_on"] = datetime(2026, 8, 7, 9, 0)
		FakeAlertDoc.store[name]["alert_status"] = "Alerted"

		with p1, p2, patch.object(
			cycle,
			"get_project_unbilled_snapshot",
			return_value=_snap(unbilled_amount=15000, expense_amount=15000),
		):
			out = cycle.evaluate_project_unbilled_alert("PROJ-1", self.settings)
		self.assertEqual(out["action"], "refreshed")
		row = FakeAlertDoc.store[name]
		self.assertEqual(row["current_unbilled_amount"], 15000)
		self.assertEqual(row["alert_sent"], 1)
		self.assertEqual(row["alert_status"], "Alerted")
		self.assertEqual(row["cycle_no"], 1)

	def test_backdated_updates_crossed_date(self):
		p1, p2 = _patch_cycle_db()
		with p1, p2, patch.object(
			cycle, "get_project_unbilled_snapshot", return_value=_snap()
		):
			cycle.evaluate_project_unbilled_alert("PROJ-1", self.settings)
		name = next(iter(FakeAlertDoc.store))
		with p1, p2, patch.object(
			cycle,
			"get_project_unbilled_snapshot",
			return_value=_snap(threshold_crossed_on=date(2026, 8, 1)),
		):
			cycle.evaluate_project_unbilled_alert("PROJ-1", self.settings)
		self.assertEqual(FakeAlertDoc.store[name]["threshold_crossed_on"], date(2026, 8, 1))

	def test_resolve_and_preserve_then_recross(self):
		p1, p2 = _patch_cycle_db()
		with p1, p2, patch.object(
			cycle, "get_project_unbilled_snapshot", return_value=_snap()
		):
			cycle.evaluate_project_unbilled_alert("PROJ-1", self.settings)
		name1 = next(iter(FakeAlertDoc.store))
		FakeAlertDoc.store[name1]["alert_sent"] = 1
		FakeAlertDoc.store[name1]["alert_sent_on"] = datetime(2026, 8, 7, 9, 0)

		with p1, p2, patch.object(
			cycle,
			"get_project_unbilled_snapshot",
			return_value=_snap(
				unbilled_amount=2000,
				expense_amount=2000,
				threshold_crossed_on=None,
			),
		):
			out = cycle.evaluate_project_unbilled_alert("PROJ-1", self.settings)
		self.assertEqual(out["action"], "resolved")
		resolved = FakeAlertDoc.store[name1]
		self.assertEqual(resolved["alert_status"], "Resolved")
		self.assertIsNotNone(resolved["resolved_on"])
		self.assertEqual(resolved["threshold_crossed_on"], date(2026, 8, 3))
		self.assertEqual(resolved["alert_sent"], 1)
		self.assertEqual(resolved["cycle_no"], 1)

		with p1, p2, patch.object(
			cycle,
			"get_project_unbilled_snapshot",
			return_value=_snap(threshold_crossed_on=date(2026, 8, 10)),
		):
			out2 = cycle.evaluate_project_unbilled_alert("PROJ-1", self.settings)
		self.assertEqual(out2["action"], "opened")
		self.assertEqual(out2["cycle_no"], 2)
		active = [
			r
			for r in FakeAlertDoc.store.values()
			if r["alert_status"] == "Pending" and not r.get("resolved_on")
		]
		self.assertEqual(len(active), 1)
		self.assertEqual(active[0]["alert_sent"], 0)
		self.assertEqual(len(FakeAlertDoc.store), 2)

	def test_missing_crossed_on_does_not_create(self):
		p1, p2 = _patch_cycle_db()
		with p1, p2, patch.object(
			cycle,
			"get_project_unbilled_snapshot",
			return_value=_snap(threshold_crossed_on=None),
		):
			out = cycle.evaluate_project_unbilled_alert("PROJ-1", self.settings)
		self.assertEqual(out["action"], "error")
		self.assertEqual(out["error"], "missing_threshold_crossed_on")
		self.assertEqual(FakeAlertDoc.store, {})

	def test_non_inr_skipped_leaves_active(self):
		p1, p2 = _patch_cycle_db()
		with p1, p2, patch.object(
			cycle, "get_project_unbilled_snapshot", return_value=_snap()
		):
			cycle.evaluate_project_unbilled_alert("PROJ-1", self.settings)
		self.assertEqual(len(FakeAlertDoc.store), 1)
		with p1, p2, patch.object(
			cycle,
			"get_project_unbilled_snapshot",
			return_value=_snap(
				skipped=True,
				skip_reason="Company currency is USD; V1 threshold comparison is INR-only.",
				currency="USD",
				unbilled_amount=0,
			),
		):
			out = cycle.evaluate_project_unbilled_alert("PROJ-1", self.settings)
		self.assertEqual(out["action"], "skipped")
		self.assertEqual(out["note"], "active_cycle_left_untouched_due_to_skip")
		row = next(iter(FakeAlertDoc.store.values()))
		self.assertEqual(row["alert_status"], "Pending")

	def test_duplicate_active_prevented_on_race(self):
		p1, p2 = _patch_cycle_db()
		# Seed an active cycle
		with p1, p2, patch.object(
			cycle, "get_project_unbilled_snapshot", return_value=_snap()
		):
			cycle.evaluate_project_unbilled_alert("PROJ-1", self.settings)

		# Force open_cycle path that rechecks and refreshes
		with p1, p2:
			out = cycle.open_cycle(_snap(unbilled_amount=13000, expense_amount=13000), self.settings)
		self.assertEqual(out["action"], "refreshed")
		self.assertEqual(out["reason"], "active_cycle_exists_on_recheck")
		self.assertEqual(len(FakeAlertDoc.store), 1)

	def test_insert_race_recovers_to_refresh(self):
		p1, p2 = _patch_cycle_db()
		with p1, p2, patch.object(
			cycle, "get_project_unbilled_snapshot", return_value=_snap()
		):
			cycle.evaluate_project_unbilled_alert("PROJ-1", self.settings)

		calls = {"n": 0}
		real_get_active = cycle.get_active_cycle

		def flaky_active(project, company):
			calls["n"] += 1
			# First call in open_cycle (recheck) pretends empty; insert then fails; second finds it
			if calls["n"] == 1:
				return None
			return real_get_active(project, company)

		with p1, p2, patch.object(cycle, "get_active_cycle", side_effect=flaky_active):
			out = cycle.open_cycle(_snap(), self.settings)
		self.assertEqual(out["action"], "refreshed")
		self.assertEqual(out["reason"], "duplicate_insert_race_recovered")
		self.assertEqual(len(FakeAlertDoc.store), 1)


class TestScheduler(unittest.TestCase):
	def setUp(self):
		_reset_store()

	def test_all_statuses_fetched_and_completed_evaluated(self):
		projects = [
			{"name": "P-OPEN", "status": "Open", "company": "Nave", "customer": "C", "project_name": "A"},
			{
				"name": "P-DONE",
				"status": "Completed",
				"company": "Nave",
				"customer": "C",
				"project_name": "B",
			},
		]
		evaluated = []

		def fake_eval(project, settings=None, today=None):
			evaluated.append(project)
			return {"action": "noop", "eligible_for_alert": False}

		with patch.object(cycle, "get_all_projects_for_evaluation", return_value=projects), patch.object(
			cycle, "evaluate_project_unbilled_alert", side_effect=fake_eval
		), patch.object(cycle, "load_unbilled_alert_settings", return_value=_settings()):
			summary = cycle.evaluate_all_project_unbilled_alerts(settings=_settings())
		self.assertEqual(evaluated, ["P-OPEN", "P-DONE"])
		self.assertEqual(summary["evaluated"], 2)

	def test_one_exception_does_not_abort(self):
		projects = [{"name": "BAD"}, {"name": "GOOD"}]

		def fake_eval(project, settings=None, today=None):
			if project == "BAD":
				raise RuntimeError("boom")
			return {"action": "noop", "eligible_for_alert": False}

		with patch.object(cycle, "get_all_projects_for_evaluation", return_value=projects), patch.object(
			cycle, "evaluate_project_unbilled_alert", side_effect=fake_eval
		):
			summary = cycle.evaluate_all_project_unbilled_alerts(settings=_settings())
		self.assertEqual(summary["evaluated"], 1)
		self.assertEqual(len(summary["errors"]), 1)
		self.assertEqual(summary["errors"][0]["project"], "BAD")

	def test_disabled_settings_skips_scheduler(self):
		with patch.object(
			cycle, "load_unbilled_alert_settings", return_value=_settings(enabled=0)
		), patch.object(cycle, "evaluate_all_project_unbilled_alerts") as ev:
			summary = cycle.run_project_unbilled_alert_daily()
		ev.assert_not_called()
		self.assertEqual(summary["skipped_reason"], "settings_disabled")
		self.assertEqual(summary["evaluated"], 0)

	def test_scheduler_hook_registered_once(self):
		text = HOOKS.read_text(encoding="utf-8")
		needle = "project_custom.project_unbilled_alert_cycle.run_project_unbilled_alert_daily"
		self.assertEqual(text.count(needle), 1)
		self.assertIn('"daily"', text.replace(" ", ""))

	def test_no_email_or_notification_log(self):
		# Step 5 owns delivery in project_unbilled_alert_notify.py.
		src = CYCLE_MOD.read_text(encoding="utf-8")
		body = src.split('"""', 2)[-1] if src.count('"""') >= 2 else src
		self.assertNotIn("frappe.sendmail", body)
		self.assertNotIn("Notification Log", body)
		self.assertNotIn("send_email(", body)
		self.assertIn("send_unbilled_alert_batch", body)


class TestGetAllProjectsPassthrough(unittest.TestCase):
	def test_get_all_projects_no_status_filter(self):
		captured = {}

		def fake_get_all(doctype, fields=None, filters=None, order_by=None):
			captured["filters"] = filters
			captured["doctype"] = doctype
			return []

		with patch.object(eng.frappe, "get_all", side_effect=fake_get_all):
			eng.get_all_projects_for_evaluation()
		self.assertEqual(captured["doctype"], "Project")
		self.assertIsNone(captured["filters"])


if __name__ == "__main__":
	unittest.main()
