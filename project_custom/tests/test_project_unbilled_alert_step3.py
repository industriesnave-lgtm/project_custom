"""Step 3 — Project unbilled expense calculation + DocType contracts."""

from __future__ import annotations

import json
import sys
import types
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

WORKSPACE = Path(__file__).resolve().parents[2]
if str(WORKSPACE) not in sys.path:
	sys.path.insert(0, str(WORKSPACE))


def _install_fake_frappe():
	if "frappe" in sys.modules and hasattr(sys.modules["frappe"], "_unbilled_stub"):
		return sys.modules["frappe"]

	frappe = types.ModuleType("frappe")
	frappe._unbilled_stub = True
	frappe.session = types.SimpleNamespace(user="Administrator")
	frappe.ValidationError = type("ValidationError", (Exception,), {})
	frappe.PermissionError = type("PermissionError", (Exception,), {})

	def throw(msg, exc=None):
		raise (exc or Exception)(msg)

	frappe.throw = throw
	frappe.whitelist = lambda *a, **k: (lambda fn: fn)
	frappe.flags = types.SimpleNamespace()
	frappe.local = types.SimpleNamespace()
	frappe.db = types.SimpleNamespace(
		sql=lambda *a, **k: [],
		get_value=lambda *a, **k: None,
		get_single_value=lambda *a, **k: None,
		exists=lambda *a, **k: False,
	)
	frappe.get_all = lambda *a, **k: []
	frappe.get_single = lambda *a, **k: types.SimpleNamespace()

	utils = types.ModuleType("frappe.utils")

	def flt(v, precision=None):
		try:
			return float(v or 0)
		except Exception:
			return 0.0

	def cint(v):
		try:
			return int(v or 0)
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

	def validate_email_address(email, throw=False):
		if "@" not in (email or ""):
			if throw:
				frappe.throw(f"Invalid email: {email}")
			return None
		return email

	utils.flt = flt
	utils.cint = cint
	utils.getdate = getdate
	utils.get_datetime = get_datetime
	utils.validate_email_address = validate_email_address
	utils.nowdate = lambda: "2026-08-08"
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

DOCTYPE_DIR = WORKSPACE / "project_custom" / "project_custom" / "doctype"
SETTINGS_JSON = (
	DOCTYPE_DIR
	/ "nave_project_unbilled_alert_settings"
	/ "nave_project_unbilled_alert_settings.json"
)
SETTINGS_PY = (
	DOCTYPE_DIR
	/ "nave_project_unbilled_alert_settings"
	/ "nave_project_unbilled_alert_settings.py"
)
ALERT_JSON = (
	DOCTYPE_DIR / "nave_project_unbilled_alert" / "nave_project_unbilled_alert.json"
)
ENGINE = WORKSPACE / "project_custom" / "project_unbilled_alert.py"


def _load_settings_module():
	import importlib.util

	spec = importlib.util.spec_from_file_location(
		"nave_project_unbilled_alert_settings_mod", SETTINGS_PY
	)
	mod = importlib.util.module_from_spec(spec)
	spec.loader.exec_module(mod)
	return mod


def _ev(day, source_type, name, expense=0.0, billing=0.0, creation=None, row="r1"):
	return {
		"date": day if isinstance(day, date) else date.fromisoformat(day),
		"creation": creation or datetime(2026, 8, 1, 10, 0, 0),
		"source_type": source_type,
		"source_name": name,
		"row_name": row,
		"project": "PROJ-1",
		"company": "Nave",
		"expense_delta": expense,
		"billing_delta": billing,
	}


class TestPurchaseInvoiceEvents(unittest.TestCase):
	def test_submitted_pi_counted(self):
		rows = [
			types.SimpleNamespace(
				posting_date=date(2026, 8, 1),
				creation=datetime(2026, 8, 1, 9, 0),
				source_name="PINV-1",
				row_name="row-a",
				base_net_amount=4000,
			)
		]
		with patch.object(eng.frappe.db, "sql", return_value=rows):
			events = eng.get_purchase_invoice_events("PROJ-1", "Nave")
		self.assertEqual(len(events), 1)
		self.assertEqual(events[0]["expense_delta"], 4000)
		self.assertEqual(events[0]["source_type"], eng.SOURCE_PI)

	def test_cancelled_pi_ignored_via_query_filter(self):
		captured = {}

		def fake_sql(query, args=None, as_dict=False):
			captured["query"] = query
			captured["args"] = args
			return []

		with patch.object(eng.frappe.db, "sql", side_effect=fake_sql):
			eng.get_purchase_invoice_events("PROJ-1", "Nave")
		self.assertIn("docstatus = 1", captured["query"])
		self.assertIn("pii.project = %s", captured["query"])
		self.assertNotIn("pi.project = %s", captured["query"])

	def test_multi_project_pi_item_wise(self):
		# Adapter is called per project; only matching item rows returned by SQL.
		rows = [
			types.SimpleNamespace(
				posting_date=date(2026, 8, 1),
				creation=datetime(2026, 8, 1, 9, 0),
				source_name="PINV-M",
				row_name="row-p1",
				base_net_amount=2500,
			)
		]
		with patch.object(eng.frappe.db, "sql", return_value=rows):
			events = eng.get_purchase_invoice_events("PROJ-1", "Nave")
		self.assertEqual(events[0]["expense_delta"], 2500)

	def test_purchase_return_reduces_cost(self):
		rows = [
			types.SimpleNamespace(
				posting_date=date(2026, 8, 2),
				creation=datetime(2026, 8, 2, 9, 0),
				source_name="PINV-RET",
				row_name="row-r",
				base_net_amount=-1500,
			)
		]
		with patch.object(eng.frappe.db, "sql", return_value=rows):
			events = eng.get_purchase_invoice_events("PROJ-1", "Nave")
		self.assertEqual(events[0]["expense_delta"], -1500)

	def test_header_only_project_ignored(self):
		# Query never selects by pi.project — only pii.project.
		captured = {}

		def fake_sql(query, args=None, as_dict=False):
			captured["query"] = " ".join(query.split())
			return []

		with patch.object(eng.frappe.db, "sql", side_effect=fake_sql):
			eng.get_purchase_invoice_events("PROJ-1", "Nave")
		self.assertIn("pii.project = %s", captured["query"])
		self.assertNotIn("AND pi.project = %s", captured["query"])


class TestJournalEntryEvents(unittest.TestCase):
	def _row(self, amount, name="JE-1", row="r1"):
		return types.SimpleNamespace(
			posting_date=date(2026, 8, 3),
			creation=datetime(2026, 8, 3, 9, 0),
			source_name=name,
			row_name=row,
			signed_amount=amount,
		)

	def test_submitted_expense_debit_counted(self):
		with patch.object(eng.frappe.db, "sql", return_value=[self._row(5000)]):
			events = eng.get_journal_expense_events("PROJ-1", "Nave")
		self.assertEqual(events[0]["expense_delta"], 5000)

	def test_expense_credit_reduces_cost(self):
		with patch.object(eng.frappe.db, "sql", return_value=[self._row(-2000)]):
			events = eng.get_journal_expense_events("PROJ-1", "Nave")
		self.assertEqual(events[0]["expense_delta"], -2000)

	def test_query_requires_expense_root_and_row_project(self):
		captured = {}

		def fake_sql(query, args=None, as_dict=False):
			captured["q"] = " ".join(query.split())
			return []

		with patch.object(eng.frappe.db, "sql", side_effect=fake_sql):
			eng.get_journal_expense_events("PROJ-1", "Nave")
		self.assertIn("acc.root_type = 'Expense'", captured["q"])
		self.assertIn("jea.project = %s", captured["q"])
		self.assertIn("je.docstatus = 1", captured["q"])
		# Header project must not be the attribution key.
		self.assertNotIn("AND je.project = %s", captured["q"])

	def test_non_expense_and_bank_ignored_by_root_type_filter(self):
		# Adapter only receives rows already filtered by SQL root_type=Expense.
		with patch.object(eng.frappe.db, "sql", return_value=[]):
			self.assertEqual(eng.get_journal_expense_events("PROJ-1", "Nave"), [])


class TestSalesInvoiceEvents(unittest.TestCase):
	def test_submitted_si_and_return(self):
		item_rows = [
			types.SimpleNamespace(
				posting_date=date(2026, 8, 4),
				creation=datetime(2026, 8, 4, 9, 0),
				source_name="SINV-1",
				row_name="si-a",
				base_net_amount=8000,
			)
		]
		return_rows = [
			types.SimpleNamespace(
				posting_date=date(2026, 8, 5),
				creation=datetime(2026, 8, 5, 9, 0),
				source_name="SINV-CN",
				row_name="si-cn",
				base_net_amount=-1000,
			)
		]

		def fake_sql(query, args=None, as_dict=False):
			q = " ".join(query.split())
			if "sii.project = %s" in q and "si.project = %s" not in q.split("WHERE")[1][:80]:
				# first query — item project
				if "sii.project = %s" in q and "(sii.project IS NULL" not in q:
					return item_rows + return_rows
			if "(sii.project IS NULL OR sii.project = '')" in q:
				return []
			return []

		# Simpler: side_effect list for two calls
		with patch.object(
			eng.frappe.db,
			"sql",
			side_effect=[item_rows + return_rows, []],
		):
			events = eng.get_sales_invoice_events("PROJ-1", "Nave")
		self.assertEqual(len(events), 2)
		self.assertEqual(events[0]["billing_delta"], 8000)
		self.assertEqual(events[1]["billing_delta"], -1000)

	def test_cancelled_si_ignored_via_docstatus(self):
		captured = []

		def fake_sql(query, args=None, as_dict=False):
			captured.append(query)
			return []

		with patch.object(eng.frappe.db, "sql", side_effect=fake_sql):
			eng.get_sales_invoice_events("PROJ-1", "Nave")
		self.assertTrue(all("docstatus = 1" in q for q in captured))

	def test_header_fallback_query_requires_null_item_project(self):
		captured = []

		def fake_sql(query, args=None, as_dict=False):
			captured.append(" ".join(query.split()))
			return []

		with patch.object(eng.frappe.db, "sql", side_effect=fake_sql):
			eng.get_sales_invoice_events("PROJ-1", "Nave")
		self.assertEqual(len(captured), 2)
		self.assertIn("(sii.project IS NULL OR sii.project = '')", captured[1])
		self.assertIn("si.project = %s", captured[1])


class TestLedgerAndTotals(unittest.TestCase):
	def test_deterministic_sort(self):
		events = [
			_ev("2026-08-02", eng.SOURCE_SI, "S2", billing=1, creation=datetime(2026, 8, 2, 12)),
			_ev("2026-08-01", eng.SOURCE_JE, "J1", expense=2, creation=datetime(2026, 8, 1, 11)),
			_ev("2026-08-01", eng.SOURCE_PI, "P1", expense=3, creation=datetime(2026, 8, 1, 10)),
		]
		sorted_events = eng.sort_financial_events(events)
		self.assertEqual(
			[e["source_name"] for e in sorted_events],
			["P1", "J1", "S2"],
		)

	def test_current_totals_and_unbilled(self):
		events = [
			_ev("2026-08-01", eng.SOURCE_PI, "P1", expense=10000),
			_ev("2026-08-02", eng.SOURCE_JE, "J1", expense=2000),
			_ev("2026-08-03", eng.SOURCE_SI, "S1", billing=5000),
		]
		totals = eng.calculate_current_totals(events)
		self.assertEqual(totals["expense_amount"], 12000)
		self.assertEqual(totals["billed_amount"], 5000)
		self.assertEqual(totals["unbilled_amount"], 7000)
		self.assertEqual(eng.calculate_current_unbilled(events), 7000)


class TestThresholdCrossing(unittest.TestCase):
	def test_crosses_on_day_three(self):
		events = [
			_ev("2026-08-01", eng.SOURCE_PI, "P1", expense=4000),
			_ev("2026-08-02", eng.SOURCE_PI, "P2", expense=3000),
			_ev("2026-08-03", eng.SOURCE_PI, "P3", expense=5000),
		]
		crossed = eng.calculate_threshold_crossed_on(events, 10000)
		self.assertEqual(crossed, date(2026, 8, 3))

	def test_exactly_threshold_does_not_trigger(self):
		events = [
			_ev("2026-08-01", eng.SOURCE_PI, "P1", expense=10000),
		]
		self.assertIsNone(eng.calculate_threshold_crossed_on(events, 10000))

	def test_drop_below_resets_and_later_recross(self):
		events = [
			_ev("2026-08-01", eng.SOURCE_PI, "P1", expense=4000),
			_ev("2026-08-02", eng.SOURCE_PI, "P2", expense=3000),
			_ev("2026-08-03", eng.SOURCE_PI, "P3", expense=5000),
			_ev("2026-08-04", eng.SOURCE_SI, "S1", billing=5000),
			_ev("2026-08-10", eng.SOURCE_PI, "P4", expense=6000),
		]
		crossed = eng.calculate_threshold_crossed_on(events, 10000)
		self.assertEqual(crossed, date(2026, 8, 10))

	def test_backdated_event_changes_crossing(self):
		# Without backdated: never crosses
		base = [
			_ev("2026-08-05", eng.SOURCE_PI, "P1", expense=6000),
			_ev("2026-08-06", eng.SOURCE_PI, "P2", expense=3000),
		]
		self.assertIsNone(eng.calculate_threshold_crossed_on(base, 10000))
		# Backdated expense on Aug 4 pushes crossing to Aug 6 when cumulative exceeds
		with_backdate = base + [
			_ev("2026-08-04", eng.SOURCE_PI, "P0", expense=2000),
		]
		crossed = eng.calculate_threshold_crossed_on(with_backdate, 10000)
		self.assertEqual(crossed, date(2026, 8, 6))


class TestProjectsAndSnapshot(unittest.TestCase):
	def test_get_all_projects_has_no_status_filter(self):
		captured = {}

		def fake_get_all(doctype, fields=None, filters=None, order_by=None):
			captured["doctype"] = doctype
			captured["filters"] = filters
			captured["fields"] = fields
			return [
				{
					"name": "PROJ-OLD",
					"project_name": "Done",
					"company": "Nave",
					"customer": "C1",
					"status": "Completed",
				}
			]

		with patch.object(eng.frappe, "get_all", side_effect=fake_get_all):
			rows = eng.get_all_projects_for_evaluation()
		self.assertEqual(captured["doctype"], "Project")
		self.assertIsNone(captured["filters"])
		self.assertEqual(rows[0]["status"], "Completed")

	def test_non_inr_project_skipped(self):
		meta = types.SimpleNamespace(
			name="PROJ-USD",
			project_name="USD Job",
			company="US Co",
			customer="C",
			status="Open",
		)
		with patch.object(eng.frappe.db, "get_value", side_effect=[meta, "USD"]):
			snap = eng.get_project_unbilled_snapshot("PROJ-USD", threshold=10000)
		self.assertTrue(snap["skipped"])
		self.assertIn("INR-only", snap["skip_reason"])
		self.assertEqual(snap["unbilled_amount"], 0.0)

	def test_snapshot_happy_path(self):
		meta = types.SimpleNamespace(
			name="PROJ-1",
			project_name="Job",
			company="Nave",
			customer="Cust",
			status="Open",
		)
		events = [
			_ev("2026-08-01", eng.SOURCE_PI, "P1", expense=12000),
			_ev("2026-08-02", eng.SOURCE_SI, "S1", billing=1000),
		]

		def get_value(doctype, name, fieldname=None, as_dict=False):
			if doctype == "Project":
				return meta
			if doctype == "Company":
				return "INR"
			return None

		with patch.object(eng.frappe.db, "get_value", side_effect=get_value), patch.object(
			eng, "build_project_financial_ledger", return_value=events
		):
			snap = eng.get_project_unbilled_snapshot("PROJ-1", threshold=10000)
		self.assertFalse(snap["skipped"])
		self.assertEqual(snap["expense_amount"], 12000)
		self.assertEqual(snap["billed_amount"], 1000)
		self.assertEqual(snap["unbilled_amount"], 11000)
		self.assertEqual(snap["threshold_crossed_on"], date(2026, 8, 1))
		self.assertEqual(snap["last_sales_invoice_date"], date(2026, 8, 2))


class TestDocTypeConfig(unittest.TestCase):
	def test_settings_defaults(self):
		doc = json.loads(SETTINGS_JSON.read_text(encoding="utf-8"))
		self.assertEqual(doc["issingle"], 1)
		fields = {f["fieldname"]: f for f in doc["fields"]}
		self.assertEqual(fields["threshold_amount"]["default"], "10000")
		self.assertEqual(fields["ageing_days"]["default"], "5")
		self.assertEqual(fields["enabled"]["default"], "0")

	def test_alert_status_options(self):
		doc = json.loads(ALERT_JSON.read_text(encoding="utf-8"))
		fields = {f["fieldname"]: f for f in doc["fields"]}
		self.assertEqual(
			fields["alert_status"]["options"],
			"Pending\nAlerted\nResolved",
		)
		self.assertEqual(fields["cycle_no"]["reqd"], 1)
		self.assertEqual(fields["project"]["reqd"], 1)

	def test_calc_engine_has_no_email_or_notify(self):
		# Step 4 owns the daily scheduler hook; Step 3 calc stays notification-free.
		engine = ENGINE.read_text(encoding="utf-8")
		self.assertNotIn("frappe.sendmail", engine)
		self.assertNotIn("Notification Log", engine)
		self.assertNotIn("run_project_unbilled_alert_daily", engine)

	def test_normalize_director_emails(self):
		mod = _load_settings_module()
		out = mod.normalize_director_emails("a@x.com, b@y.com;\nc@z.com\na@x.com")
		self.assertEqual(out, "a@x.com\nb@y.com\nc@z.com")

	def test_expense_claim_adapter_noop(self):
		self.assertEqual(eng.get_expense_claim_events("PROJ-1", "Nave"), [])


if __name__ == "__main__":
	unittest.main()
