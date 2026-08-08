# Copyright (c) 2026, Nave Industries and contributors
# License: MIT. See LICENSE
"""
Project-wise unbilled expense calculation (V1).

Expense sources: Purchase Invoice Item + Journal Entry Account (Expense).
Billing source: Sales Invoice Item (+ header project fallback when item.project empty).
No scheduler / email in this module.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

import frappe
from frappe.utils import flt, get_datetime, getdate

SOURCE_PI = "Purchase Invoice"
SOURCE_JE = "Journal Entry"
SOURCE_SI = "Sales Invoice"

INR = "INR"
DEFAULT_THRESHOLD = 10000.0

SOURCE_SORT_ORDER = {
	SOURCE_PI: 1,
	SOURCE_JE: 2,
	SOURCE_SI: 3,
}


def _as_date(value) -> date | None:
	if value in (None, ""):
		return None
	return getdate(value)


def _as_datetime(value) -> datetime | None:
	if value in (None, ""):
		return None
	return get_datetime(value)


def _event(
	*,
	date_value,
	creation,
	source_type: str,
	source_name: str,
	project: str,
	company: str,
	expense_delta: float = 0.0,
	billing_delta: float = 0.0,
	row_name: str | None = None,
) -> dict[str, Any]:
	return {
		"date": _as_date(date_value),
		"creation": _as_datetime(creation),
		"source_type": source_type,
		"source_name": source_name or "",
		"row_name": row_name or "",
		"project": project,
		"company": company,
		"expense_delta": flt(expense_delta),
		"billing_delta": flt(billing_delta),
	}


def get_purchase_invoice_events(project: str, company: str) -> list[dict[str, Any]]:
	"""Item-level PI events. Header-only project is ignored."""
	rows = frappe.db.sql(
		"""
		SELECT
			pi.posting_date AS posting_date,
			pi.creation AS creation,
			pi.name AS source_name,
			pii.name AS row_name,
			pii.base_net_amount AS base_net_amount
		FROM `tabPurchase Invoice Item` pii
		INNER JOIN `tabPurchase Invoice` pi ON pi.name = pii.parent
		WHERE pii.project = %s
			AND pi.docstatus = 1
			AND pi.company = %s
		""",
		(project, company),
		as_dict=True,
	)
	return [
		_event(
			date_value=row.posting_date,
			creation=row.creation,
			source_type=SOURCE_PI,
			source_name=row.source_name,
			row_name=row.row_name,
			project=project,
			company=company,
			expense_delta=row.base_net_amount,
		)
		for row in rows or []
	]


def get_journal_expense_events(project: str, company: str) -> list[dict[str, Any]]:
	"""JE Account row project + Expense root_type only. Header JE.project ignored."""
	rows = frappe.db.sql(
		"""
		SELECT
			je.posting_date AS posting_date,
			je.creation AS creation,
			je.name AS source_name,
			jea.name AS row_name,
			-- debit/credit are company-currency fields in ERPNext v16
			-- (labels: Debit/Credit in Company Currency)
			(jea.debit - jea.credit) AS signed_amount
		FROM `tabJournal Entry Account` jea
		INNER JOIN `tabJournal Entry` je ON je.name = jea.parent
		INNER JOIN `tabAccount` acc ON acc.name = jea.account
		WHERE jea.project = %s
			AND je.docstatus = 1
			AND je.company = %s
			AND acc.root_type = 'Expense'
		""",
		(project, company),
		as_dict=True,
	)
	return [
		_event(
			date_value=row.posting_date,
			creation=row.creation,
			source_type=SOURCE_JE,
			source_name=row.source_name,
			row_name=row.row_name,
			project=project,
			company=company,
			expense_delta=row.signed_amount,
		)
		for row in rows or []
	]


def get_sales_invoice_events(project: str, company: str) -> list[dict[str, Any]]:
	"""
	SI billing events:
	1) Items with item.project = project
	2) Items with empty item.project where SI.project = project (header fallback)
	No double-count: (2) requires item.project IS NULL / ''.
	"""
	item_rows = frappe.db.sql(
		"""
		SELECT
			si.posting_date AS posting_date,
			si.creation AS creation,
			si.name AS source_name,
			sii.name AS row_name,
			sii.base_net_amount AS base_net_amount
		FROM `tabSales Invoice Item` sii
		INNER JOIN `tabSales Invoice` si ON si.name = sii.parent
		WHERE sii.project = %s
			AND si.docstatus = 1
			AND si.company = %s
		""",
		(project, company),
		as_dict=True,
	)
	header_rows = frappe.db.sql(
		"""
		SELECT
			si.posting_date AS posting_date,
			si.creation AS creation,
			si.name AS source_name,
			sii.name AS row_name,
			sii.base_net_amount AS base_net_amount
		FROM `tabSales Invoice Item` sii
		INNER JOIN `tabSales Invoice` si ON si.name = sii.parent
		WHERE si.project = %s
			AND si.docstatus = 1
			AND si.company = %s
			AND (sii.project IS NULL OR sii.project = '')
		""",
		(project, company),
		as_dict=True,
	)
	events = []
	for row in (item_rows or []) + (header_rows or []):
		events.append(
			_event(
				date_value=row.posting_date,
				creation=row.creation,
				source_type=SOURCE_SI,
				source_name=row.source_name,
				row_name=row.row_name,
				project=project,
				company=company,
				billing_delta=row.base_net_amount,
			)
		)
	return events


def sort_financial_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
	"""Deterministic chronological sort."""

	def key(e: dict[str, Any]):
		d = e.get("date") or date.min
		c = e.get("creation") or datetime.min
		st = SOURCE_SORT_ORDER.get(e.get("source_type") or "", 99)
		sn = e.get("source_name") or ""
		rn = e.get("row_name") or ""
		return (d, c, st, sn, rn)

	return sorted(events or [], key=key)


def build_project_financial_ledger(project: str, company: str) -> list[dict[str, Any]]:
	events = []
	events.extend(get_purchase_invoice_events(project, company))
	events.extend(get_journal_expense_events(project, company))
	events.extend(get_sales_invoice_events(project, company))
	return sort_financial_events(events)


def calculate_current_totals(events: list[dict[str, Any]]) -> dict[str, float]:
	expense = 0.0
	billed = 0.0
	for e in events or []:
		expense += flt(e.get("expense_delta"))
		billed += flt(e.get("billing_delta"))
	return {
		"expense_amount": flt(expense),
		"billed_amount": flt(billed),
		"unbilled_amount": flt(expense - billed),
	}


def calculate_current_unbilled(events: list[dict[str, Any]]) -> float:
	return calculate_current_totals(events)["unbilled_amount"]


def calculate_threshold_crossed_on(
	events: list[dict[str, Any]], threshold: float
) -> date | None:
	"""
	Return start date of the *current* unresolved above-threshold segment.
	Resets when running unbilled falls to <= threshold.
	"""
	threshold = flt(threshold)
	running = 0.0
	crossed_on: date | None = None

	for e in sort_financial_events(events):
		running += flt(e.get("expense_delta"))
		running -= flt(e.get("billing_delta"))
		if running > threshold:
			if crossed_on is None:
				crossed_on = e.get("date")
		else:
			crossed_on = None

	final_unbilled = calculate_current_unbilled(events)
	if final_unbilled <= threshold:
		return None
	return crossed_on


def get_last_sales_invoice_date(events: list[dict[str, Any]]) -> date | None:
	"""Latest SI posting date with non-zero billing contribution."""
	latest: date | None = None
	for e in events or []:
		if e.get("source_type") != SOURCE_SI:
			continue
		if flt(e.get("billing_delta")) == 0:
			continue
		d = e.get("date")
		if d and (latest is None or d > latest):
			latest = d
	return latest


def get_company_currency(company: str) -> str | None:
	if not company:
		return None
	return frappe.db.get_value("Company", company, "default_currency")


def get_all_projects_for_evaluation() -> list[dict[str, Any]]:
	"""All Project records — no status filter."""
	return frappe.get_all(
		"Project",
		fields=["name", "project_name", "company", "customer", "status"],
		order_by="name asc",
	)


def get_settings_threshold() -> float:
	try:
		value = frappe.db.get_single_value(
			"NAVE Project Unbilled Alert Settings", "threshold_amount"
		)
	except Exception:
		value = None
	return flt(value if value not in (None, "") else DEFAULT_THRESHOLD)


def get_project_unbilled_snapshot(project: str, threshold: float | None = None) -> dict[str, Any]:
	"""Build evaluation snapshot for one project (no persistence / no email)."""
	meta = frappe.db.get_value(
		"Project",
		project,
		["name", "project_name", "company", "customer", "status"],
		as_dict=True,
	)
	if not meta:
		frappe.throw(f"Project {project} not found.")

	company = meta.company
	currency = get_company_currency(company)
	threshold = flt(threshold if threshold is not None else get_settings_threshold())

	base = {
		"project": meta.name,
		"project_name": meta.project_name,
		"company": company,
		"customer": meta.customer,
		"project_status": meta.status,
		"expense_amount": 0.0,
		"billed_amount": 0.0,
		"unbilled_amount": 0.0,
		"threshold_crossed_on": None,
		"last_sales_invoice_date": None,
		"currency": currency,
		"threshold_amount": threshold,
		"skipped": False,
		"skip_reason": None,
	}

	if currency != INR:
		base["skipped"] = True
		base["skip_reason"] = (
			f"Company currency is {currency or 'unset'}; "
			f"V1 threshold comparison is INR-only."
		)
		return base

	events = build_project_financial_ledger(project, company)
	totals = calculate_current_totals(events)
	base.update(totals)
	base["threshold_crossed_on"] = calculate_threshold_crossed_on(events, threshold)
	base["last_sales_invoice_date"] = get_last_sales_invoice_date(events)
	return base


# --- Future adapter seam (Expense Claim / HRMS) — not implemented in V1 ---


def get_expense_claim_events(project: str, company: str) -> list[dict[str, Any]]:
	"""Reserved for HRMS Expense Claim. V1 returns no events."""
	return []
