"""Step 6 — NAVE Project Unbilled Expense Alert Script Report + Desk entry."""

from __future__ import annotations

import json
import sys
import types
import unittest
from datetime import date, datetime
from pathlib import Path
from unittest.mock import patch

WORKSPACE = Path(__file__).resolve().parents[2]
if str(WORKSPACE) not in sys.path:
	sys.path.insert(0, str(WORKSPACE))


def _install_fake_frappe():
	if "frappe" in sys.modules and hasattr(sys.modules["frappe"], "_unbilled_report_stub"):
		return sys.modules["frappe"]

	frappe = types.ModuleType("frappe")
	frappe._unbilled_report_stub = True
	frappe.session = types.SimpleNamespace(user="manager@example.com")
	frappe.PermissionError = type("PermissionError", (Exception,), {})
	frappe.ValidationError = type("ValidationError", (Exception,), {})

	def throw(msg, exc=None):
		raise (exc or Exception)(msg)

	frappe.throw = throw
	frappe.get_roles = lambda user=None: [
		"Projects Manager",
		"NAVE Task Manager",
	]
	frappe._ = lambda s: s
	frappe._dict = dict
	frappe.whitelist = lambda *a, **k: (lambda fn: fn)
	frappe.db = types.SimpleNamespace(get_value=lambda *a, **k: None)
	frappe.get_all = lambda *a, **k: []
	frappe.flags = types.SimpleNamespace()
	frappe.local = types.SimpleNamespace()
	frappe.log_error = lambda *a, **k: None

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

	utils.flt = flt
	utils.cint = cint
	utils.getdate = getdate
	utils.nowdate = lambda: "2026-08-08"
	utils.now_datetime = lambda: datetime(2026, 8, 8, 12, 0, 0)
	utils.get_datetime = lambda d: d if isinstance(d, datetime) else datetime.fromisoformat(str(d))
	frappe.utils = utils

	sys.modules["frappe"] = frappe
	sys.modules["frappe.utils"] = utils
	sys.modules["frappe.model"] = types.ModuleType("frappe.model")
	doc_mod = types.ModuleType("frappe.model.document")
	doc_mod.Document = type("Document", (), {})
	sys.modules["frappe.model.document"] = doc_mod
	return frappe


_install_fake_frappe()

from project_custom import project_unbilled_alert_report as rpt  # noqa: E402

REPORT_DIR = (
	WORKSPACE
	/ "project_custom"
	/ "project_custom"
	/ "report"
	/ "nave_project_unbilled_expense_alert"
)
REPORT_JSON = REPORT_DIR / "nave_project_unbilled_expense_alert.json"
REPORT_JS = REPORT_DIR / "nave_project_unbilled_expense_alert.js"
REPORT_PY = REPORT_DIR / "nave_project_unbilled_expense_alert.py"
NAVE_HOME = (
	WORKSPACE / "project_custom" / "project_custom" / "page" / "nave_home" / "nave_home.js"
)
TODAY = date(2026, 8, 8)


def _row(**kwargs):
	base = {
		"name": "NPUA-1",
		"project": "PROJ-A",
		"project_name": "Alpha",
		"customer": "Cust-A",
		"company": "Nave",
		"project_status": "Open",
		"current_expense_amount": 20000,
		"current_billed_amount": 5000,
		"current_unbilled_amount": 15000,
		"threshold_amount": 10000,
		"threshold_crossed_on": date(2026, 8, 1),
		"ageing_days": 7,
		"last_sales_invoice_date": date(2026, 7, 10),
		"alert_status": "Pending",
		"alert_sent": 0,
		"alert_sent_on": None,
		"cycle_no": 1,
		"last_evaluated_on": datetime(2026, 8, 8, 9, 0),
		"resolved_on": None,
	}
	base.update(kwargs)
	return base


class TestReportConfig(unittest.TestCase):
	def test_report_json_exists(self):
		self.assertTrue(REPORT_JSON.is_file())
		doc = json.loads(REPORT_JSON.read_text(encoding="utf-8"))
		self.assertEqual(doc["name"], "NAVE Project Unbilled Expense Alert")
		self.assertEqual(doc["report_type"], "Script Report")
		self.assertEqual(doc["ref_doctype"], "NAVE Project Unbilled Alert")
		roles = {r["role"] for r in doc["roles"]}
		self.assertIn("System Manager", roles)
		self.assertIn("Accounts Manager", roles)
		self.assertIn("Projects Manager", roles)
		self.assertIn("NAVE Task Director", roles)
		self.assertNotIn("Employee", roles)

	def test_columns_and_project_link(self):
		cols = {c["fieldname"]: c for c in rpt.get_columns()}
		for key in [
			"project",
			"project_name",
			"customer",
			"company",
			"project_status",
			"current_expense_amount",
			"current_billed_amount",
			"current_unbilled_amount",
			"threshold_amount",
			"threshold_crossed_on",
			"ageing_days",
			"last_sales_invoice_date",
			"alert_status",
			"alert_sent",
			"alert_sent_on",
			"cycle_no",
			"last_evaluated_on",
			"name",
		]:
			self.assertIn(key, cols)
		self.assertEqual(cols["project"]["fieldtype"], "Link")
		self.assertEqual(cols["project"]["options"], "Project")
		self.assertEqual(cols["name"]["options"], "NAVE Project Unbilled Alert")

	def test_desk_shortcut_points_to_report(self):
		text = NAVE_HOME.read_text(encoding="utf-8")
		self.assertIn("Project Unbilled Expense Alert", text)
		self.assertIn("NAVE Project Unbilled Expense Alert", text)
		self.assertIn('["query-report", "NAVE Project Unbilled Expense Alert"]', text)
		self.assertTrue(REPORT_PY.is_file())
		self.assertTrue(REPORT_JS.is_file())


class TestReportFiltersAndSort(unittest.TestCase):
	def setUp(self):
		self.dataset = [
			_row(
				name="NPUA-P",
				project="PROJ-B",
				alert_status="Pending",
				threshold_crossed_on=date(2026, 8, 1),
				current_unbilled_amount=12000,
				company="Nave",
				customer="Cust-B",
				project_status="Completed",
			),
			_row(
				name="NPUA-A",
				project="PROJ-A",
				alert_status="Alerted",
				alert_sent=1,
				threshold_crossed_on=date(2026, 7, 20),
				current_unbilled_amount=25000,
				company="Nave",
				customer="Cust-A",
			),
			_row(
				name="NPUA-R",
				project="PROJ-C",
				alert_status="Resolved",
				alert_sent=1,
				resolved_on=datetime(2026, 8, 5, 10, 0),
				threshold_crossed_on=date(2026, 7, 1),
				current_unbilled_amount=8000,
				company="Other Co",
				customer="Cust-C",
			),
			_row(
				name="NPUA-X",
				project="PROJ-D",
				alert_status="Pending",
				threshold_crossed_on=date(2026, 8, 6),
				current_unbilled_amount=11000,
				company="Nave",
			),
		]

	def _run(self, filters=None, rows=None):
		rows = rows if rows is not None else self.dataset

		def fake_get_all(doctype, filters=None, fields=None):
			# Apply simple filter simulation
			out = list(rows)
			for f in filters or []:
				field, op, val = f[0], f[1], f[2]
				if op == "=":
					out = [r for r in out if r.get(field) == val]
				elif op == "in":
					out = [r for r in out if r.get(field) in val]
				elif op == ">=":
					out = [r for r in out if r.get(field) is not None and r.get(field) >= val]
				elif op == "<=":
					out = [r for r in out if r.get(field) is not None and r.get(field) <= val]
			return [dict(r) for r in out]

		with patch.object(rpt.frappe, "get_all", side_effect=fake_get_all):
			return rpt.fetch_unbilled_alert_report_rows(filters or {}, today=TODAY)

	def test_active_only_default(self):
		data = self._run({})
		statuses = {r["alert_status"] for r in data}
		self.assertNotIn("Resolved", statuses)
		self.assertTrue(statuses <= {"Pending", "Alerted"})

	def test_include_resolved(self):
		data = self._run({"include_resolved": 1})
		self.assertIn("Resolved", {r["alert_status"] for r in data})

	def test_company_filter(self):
		data = self._run({"company": "Other Co", "include_resolved": 1})
		self.assertEqual([r["name"] for r in data], ["NPUA-R"])

	def test_project_filter(self):
		data = self._run({"project": "PROJ-A"})
		self.assertEqual([r["project"] for r in data], ["PROJ-A"])

	def test_customer_filter(self):
		data = self._run({"customer": "Cust-B"})
		self.assertEqual([r["customer"] for r in data], ["Cust-B"])

	def test_alert_status_filter(self):
		data = self._run({"alert_status": "Alerted"})
		self.assertTrue(all(r["alert_status"] == "Alerted" for r in data))

	def test_alert_sent_filter(self):
		data = self._run({"alert_sent": 1, "include_resolved": 1})
		self.assertTrue(all(int(r["alert_sent"]) == 1 for r in data))

	def test_threshold_crossed_date_filters(self):
		data = self._run(
			{
				"threshold_crossed_from": "2026-07-15",
				"threshold_crossed_to": "2026-08-02",
			}
		)
		for r in data:
			d = r["threshold_crossed_on"]
			self.assertGreaterEqual(d, date(2026, 7, 15))
			self.assertLessEqual(d, date(2026, 8, 2))

	def test_ageing_and_unbilled_min(self):
		data = self._run({"ageing_days_min": 10})
		self.assertTrue(all(r["ageing_days"] >= 10 for r in data))
		data2 = self._run({"unbilled_amount_min": 20000})
		self.assertTrue(all(r["current_unbilled_amount"] >= 20000 for r in data2))

	def test_completed_project_visible(self):
		data = self._run({})
		self.assertTrue(any(r["project_status"] == "Completed" for r in data))

	def test_default_sort(self):
		data = self._run({})
		# Pending first, then Alerted; within Pending higher ageing first
		statuses = [r["alert_status"] for r in data]
		self.assertEqual(statuses, sorted(statuses, key=lambda s: {"Pending": 0, "Alerted": 1}[s]))
		pending = [r for r in data if r["alert_status"] == "Pending"]
		ages = [r["ageing_days"] for r in pending]
		self.assertEqual(ages, sorted(ages, reverse=True))


class TestReportSummaryAndPerms(unittest.TestCase):
	def test_summary_counts(self):
		rows = [
			_row(
				name="1",
				alert_status="Pending",
				threshold_crossed_on=date(2026, 8, 1),
				current_unbilled_amount=10000,
			),
			_row(
				name="2",
				alert_status="Alerted",
				threshold_crossed_on=date(2026, 7, 20),
				current_unbilled_amount=20000,
			),
			_row(
				name="3",
				alert_status="Resolved",
				threshold_crossed_on=date(2026, 7, 1),
				current_unbilled_amount=50000,
			),
			_row(
				name="4",
				alert_status="Pending",
				threshold_crossed_on=date(2026, 8, 6),
				current_unbilled_amount=5000,
			),
		]
		# Ageing as of 2026-08-08: 7, 19, 38, 2
		for r in rows:
			r["ageing_days"] = rpt.calculate_ageing_days(
				r["threshold_crossed_on"], today=TODAY
			)
		summary = {s["label"]: s["value"] for s in rpt._build_summary(rows)}
		# Active excludes Resolved
		self.assertEqual(summary["Active Alert Cycles"], 3)
		self.assertEqual(summary["Pending"], 2)
		self.assertEqual(summary["Alerted"], 1)
		self.assertEqual(summary["Total Unbilled Amount"], 35000)
		self.assertEqual(summary["5+ Day Ageing"], 2)
		self.assertEqual(summary["10+ Day Ageing"], 1)

	def test_unauthorized_employee_blocked(self):
		with patch.object(rpt.frappe, "get_roles", return_value=["Employee"]), patch.object(
			rpt.frappe.session, "user", "emp@example.com"
		):
			with self.assertRaises(rpt.frappe.PermissionError):
				rpt.assert_unbilled_alert_report_access()

	def test_management_role_allowed(self):
		with patch.object(
			rpt.frappe, "get_roles", return_value=["Accounts Manager"]
		), patch.object(rpt.frappe.session, "user", "acc@example.com"):
			rpt.assert_unbilled_alert_report_access()  # no throw

	def test_execute_empty_no_error(self):
		with patch.object(rpt, "assert_unbilled_alert_report_access"), patch.object(
			rpt, "fetch_unbilled_alert_report_rows", return_value=[]
		):
			cols, data, message, chart, summary = rpt.execute_unbilled_alert_report({})
		self.assertEqual(data, [])
		self.assertIsNotNone(message)
		self.assertEqual(chart, None)
		self.assertEqual(len(summary), 6)


if __name__ == "__main__":
	unittest.main()
