# Copyright (c) 2026, Nave Industries and contributors
# License: MIT. See LICENSE
"""
Script Report data for NAVE Project Unbilled Expense Alert.

Reads NAVE Project Unbilled Alert cycle records only (no PI/JE/SI recalculation).
"""

from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate, nowdate

from project_custom.project_unbilled_alert_cycle import (
	ALERT_DOCTYPE,
	calculate_ageing_days,
)

REPORT_NAME = "NAVE Project Unbilled Expense Alert"

ALLOWED_REPORT_ROLES = (
	"System Manager",
	"Accounts Manager",
	"Projects Manager",
	"NAVE Task Director",
	"NAVE Task Manager",
)

STATUS_SORT_ORDER = {"Pending": 0, "Alerted": 1, "Resolved": 2}


def assert_unbilled_alert_report_access(user: str | None = None) -> None:
	"""Server-side gate — Report.roles is not enough alone."""
	user = user or frappe.session.user
	if user == "Administrator":
		return
	roles = set(frappe.get_roles(user) or [])
	if roles.intersection(ALLOWED_REPORT_ROLES):
		return
	frappe.throw(
		_("You are not permitted to view {0}.").format(REPORT_NAME),
		frappe.PermissionError,
	)


def get_columns() -> list[dict[str, Any]]:
	return [
		{
			"label": _("Alert"),
			"fieldname": "name",
			"fieldtype": "Link",
			"options": "NAVE Project Unbilled Alert",
			"width": 140,
		},
		{
			"label": _("Project ID"),
			"fieldname": "project",
			"fieldtype": "Link",
			"options": "Project",
			"width": 120,
		},
		{
			"label": _("Project Name"),
			"fieldname": "project_name",
			"fieldtype": "Data",
			"width": 160,
		},
		{
			"label": _("Customer"),
			"fieldname": "customer",
			"fieldtype": "Link",
			"options": "Customer",
			"width": 140,
		},
		{
			"label": _("Company"),
			"fieldname": "company",
			"fieldtype": "Link",
			"options": "Company",
			"width": 120,
		},
		{
			"label": _("Project Status"),
			"fieldname": "project_status",
			"fieldtype": "Data",
			"width": 110,
		},
		{
			"label": _("Current Expense Amount"),
			"fieldname": "current_expense_amount",
			"fieldtype": "Currency",
			"width": 140,
		},
		{
			"label": _("Current Billed Amount"),
			"fieldname": "current_billed_amount",
			"fieldtype": "Currency",
			"width": 140,
		},
		{
			"label": _("Unbilled Expense Amount"),
			"fieldname": "current_unbilled_amount",
			"fieldtype": "Currency",
			"width": 150,
		},
		{
			"label": _("Threshold Amount"),
			"fieldname": "threshold_amount",
			"fieldtype": "Currency",
			"width": 120,
		},
		{
			"label": _("Threshold Crossed Date"),
			"fieldname": "threshold_crossed_on",
			"fieldtype": "Date",
			"width": 140,
		},
		{
			"label": _("Ageing Days"),
			"fieldname": "ageing_days",
			"fieldtype": "Int",
			"width": 100,
		},
		{
			"label": _("Last Sales Invoice Date"),
			"fieldname": "last_sales_invoice_date",
			"fieldtype": "Date",
			"width": 150,
		},
		{
			"label": _("Alert Status"),
			"fieldname": "alert_status",
			"fieldtype": "Data",
			"width": 110,
		},
		{
			"label": _("Alert Sent"),
			"fieldname": "alert_sent",
			"fieldtype": "Check",
			"width": 90,
		},
		{
			"label": _("Alert Sent On"),
			"fieldname": "alert_sent_on",
			"fieldtype": "Datetime",
			"width": 150,
		},
		{
			"label": _("Cycle No"),
			"fieldname": "cycle_no",
			"fieldtype": "Int",
			"width": 80,
		},
		{
			"label": _("Last Evaluated On"),
			"fieldname": "last_evaluated_on",
			"fieldtype": "Datetime",
			"width": 150,
		},
	]


def _validate_filters(filters: dict[str, Any]) -> None:
	filters = filters or {}
	from_date = filters.get("threshold_crossed_from")
	to_date = filters.get("threshold_crossed_to")
	if from_date and to_date and getdate(from_date) > getdate(to_date):
		frappe.throw(_("Threshold Crossed From cannot be after Threshold Crossed To."))

	if filters.get("ageing_days_min") not in (None, ""):
		if cint(filters.get("ageing_days_min")) < 0:
			frappe.throw(_("Ageing Days >= cannot be negative."))

	if filters.get("unbilled_amount_min") not in (None, ""):
		if flt(filters.get("unbilled_amount_min")) < 0:
			frappe.throw(_("Unbilled Amount >= cannot be negative."))


def _build_db_filters(filters: dict[str, Any]) -> list:
	filters = filters or {}
	db_filters: list = []

	if filters.get("company"):
		db_filters.append(["company", "=", filters["company"]])
	if filters.get("project"):
		db_filters.append(["project", "=", filters["project"]])
	if filters.get("customer"):
		db_filters.append(["customer", "=", filters["customer"]])
	if filters.get("project_status"):
		db_filters.append(["project_status", "=", filters["project_status"]])

	alert_status = (filters.get("alert_status") or "").strip()
	include_resolved = cint(filters.get("include_resolved"))

	if alert_status:
		db_filters.append(["alert_status", "=", alert_status])
	elif include_resolved:
		# All statuses
		pass
	else:
		db_filters.append(["alert_status", "in", ["Pending", "Alerted"]])

	if filters.get("alert_sent") not in (None, ""):
		db_filters.append(["alert_sent", "=", cint(filters.get("alert_sent"))])

	if filters.get("threshold_crossed_from"):
		db_filters.append(
			["threshold_crossed_on", ">=", getdate(filters["threshold_crossed_from"])]
		)
	if filters.get("threshold_crossed_to"):
		db_filters.append(
			["threshold_crossed_on", "<=", getdate(filters["threshold_crossed_to"])]
		)

	return db_filters


def _sort_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
	def key(r):
		status_rank = STATUS_SORT_ORDER.get(r.get("alert_status") or "", 99)
		age = cint(r.get("ageing_days") or 0)
		unbilled = flt(r.get("current_unbilled_amount"))
		project = r.get("project") or ""
		return (status_rank, -age, -unbilled, project)

	return sorted(rows or [], key=key)


def _build_summary(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
	active = [r for r in rows if r.get("alert_status") in ("Pending", "Alerted")]
	pending = sum(1 for r in active if r.get("alert_status") == "Pending")
	alerted = sum(1 for r in active if r.get("alert_status") == "Alerted")
	total_unbilled = sum(flt(r.get("current_unbilled_amount")) for r in active)
	age_5 = sum(1 for r in active if cint(r.get("ageing_days") or 0) >= 5)
	age_10 = sum(1 for r in active if cint(r.get("ageing_days") or 0) >= 10)

	return [
		{
			"value": len(active),
			"label": _("Active Alert Cycles"),
			"datatype": "Int",
		},
		{
			"value": pending,
			"label": _("Pending"),
			"datatype": "Int",
		},
		{
			"value": alerted,
			"label": _("Alerted"),
			"datatype": "Int",
		},
		{
			"value": total_unbilled,
			"label": _("Total Unbilled Amount"),
			"datatype": "Currency",
		},
		{
			"value": age_5,
			"label": _("5+ Day Ageing"),
			"datatype": "Int",
		},
		{
			"value": age_10,
			"label": _("10+ Day Ageing"),
			"datatype": "Int",
		},
	]


def fetch_unbilled_alert_report_rows(
	filters: dict[str, Any] | None = None,
	*,
	today=None,
) -> list[dict[str, Any]]:
	"""Fetch and filter cycle rows for the report (no financial recalculation)."""
	filters = frappe._dict(filters or {})
	_validate_filters(filters)
	as_of = getdate(today or nowdate())

	rows = frappe.get_all(
		ALERT_DOCTYPE,
		filters=_build_db_filters(filters),
		fields=[
			"name",
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
			"resolved_on",
		],
	)

	ageing_min = filters.get("ageing_days_min")
	unbilled_min = filters.get("unbilled_amount_min")
	has_ageing_min = ageing_min not in (None, "")
	has_unbilled_min = unbilled_min not in (None, "")
	ageing_min_v = cint(ageing_min) if has_ageing_min else None
	unbilled_min_v = flt(unbilled_min) if has_unbilled_min else None

	prepared: list[dict[str, Any]] = []
	for row in rows or []:
		age = calculate_ageing_days(row.get("threshold_crossed_on"), today=as_of)
		row["ageing_days"] = age if age is not None else cint(row.get("ageing_days") or 0)

		if has_ageing_min and cint(row["ageing_days"]) < ageing_min_v:
			continue
		if has_unbilled_min and flt(row.get("current_unbilled_amount")) < unbilled_min_v:
			continue

		prepared.append(row)

	return _sort_rows(prepared)


def execute_unbilled_alert_report(filters=None, *, today=None):
	"""Return columns, data, message, chart, report_summary."""
	assert_unbilled_alert_report_access()
	columns = get_columns()
	data = fetch_unbilled_alert_report_rows(filters, today=today)
	summary = _build_summary(data)
	message = None
	if not data:
		message = _("No unbilled expense alerts match the selected filters.")
	return columns, data, message, None, summary
