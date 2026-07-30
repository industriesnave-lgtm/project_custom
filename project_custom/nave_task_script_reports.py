"""Shared builders for NAVE Task Script Reports (Phase 3 — Batch 7B).

Thin report modules call these helpers. Permission and filter normalization
come from nave_task_reporting.py — not duplicated per report.
"""

from __future__ import annotations

from datetime import date, timedelta

import frappe

from project_custom.nave_task_reporting import (
	_as_date,
	_row_get,
	build_summary_from_rows,
	get_task_rows,
	normalize_filters,
)
from project_custom.nave_task_utils import is_terminal_status


ACTIVE_STATUSES = ("Open", "Working", "Pending")

OVERDUE_AGING_BUCKETS = (
	"1-3 Days",
	"4-7 Days",
	"8-15 Days",
	"16-30 Days",
	"30+ Days",
)

PENDING_AGING_BUCKETS = (
	"0-3 Days",
	"4-7 Days",
	"8-15 Days",
	"16-30 Days",
	"30+ Days",
)

REPORT_FIELDS = (
	"name",
	"subject",
	"status",
	"priority",
	"assigned_to",
	"assigned_by",
	"owner",
	"department",
	"project",
	"due_date",
	"is_overdue",
	"creation",
	"modified",
)


def _today(today=None) -> date:
	if today is None:
		from frappe.utils import getdate, nowdate

		return getdate(nowdate())
	parsed = _as_date(today)
	return parsed or date.today()


def report_filters_dict(filters) -> dict:
	"""Convert Script Report filters (_dict / dict) to a plain dict."""
	if not filters:
		return {}
	if hasattr(filters, "items"):
		return {k: v for k, v in filters.items() if v not in (None, "")}
	return dict(filters)


def days_overdue(due_date, status, today=None) -> int:
	"""Positive overdue days for active tasks; 0 otherwise."""
	day = _today(today)
	if is_terminal_status(status):
		return 0
	due = _as_date(due_date)
	if not due:
		return 0
	delta = (day - due).days
	return delta if delta > 0 else 0


def overdue_aging_bucket(days: int) -> str | None:
	if days < 1:
		return None
	if days <= 3:
		return "1-3 Days"
	if days <= 7:
		return "4-7 Days"
	if days <= 15:
		return "8-15 Days"
	if days <= 30:
		return "16-30 Days"
	return "30+ Days"


def pending_age_days(creation, today=None) -> int:
	day = _today(today)
	created = _as_date(creation)
	if not created:
		return 0
	return max((day - created).days, 0)


def pending_aging_bucket(days: int) -> str:
	if days <= 3:
		return "0-3 Days"
	if days <= 7:
		return "4-7 Days"
	if days <= 15:
		return "8-15 Days"
	if days <= 30:
		return "16-30 Days"
	return "30+ Days"


def _created_by_display(row) -> str:
	return _row_get(row, "assigned_by") or _row_get(row, "owner") or ""


def _summary_items(pairs: list[tuple[str, int]]) -> list[dict]:
	return [
		{"label": label, "value": int(value or 0), "datatype": "Int"}
		for label, value in pairs
	]


def _base_columns_task_id_title():
	return [
		{
			"label": "Task ID",
			"fieldname": "name",
			"fieldtype": "Link",
			"options": "NAVE Task",
			"width": 140,
		},
		{
			"label": "Title",
			"fieldname": "subject",
			"fieldtype": "Data",
			"width": 220,
		},
	]


# ---------------------------------------------------------------------------
# My Tasks
# ---------------------------------------------------------------------------


def my_tasks_columns():
	return _base_columns_task_id_title() + [
		{"label": "Status", "fieldname": "status", "fieldtype": "Data", "width": 100},
		{"label": "Priority", "fieldname": "priority", "fieldtype": "Data", "width": 90},
		{"label": "Due Date", "fieldname": "due_date", "fieldtype": "Date", "width": 110},
		{
			"label": "Project",
			"fieldname": "project",
			"fieldtype": "Link",
			"options": "Project",
			"width": 140,
		},
		{
			"label": "Department",
			"fieldname": "department",
			"fieldtype": "Link",
			"options": "Department",
			"width": 140,
		},
		{
			"label": "Created By",
			"fieldname": "created_by",
			"fieldtype": "Link",
			"options": "User",
			"width": 160,
		},
		{"label": "Modified", "fieldname": "modified", "fieldtype": "Datetime", "width": 150},
		{
			"label": "Days Overdue",
			"fieldname": "days_overdue",
			"fieldtype": "Int",
			"width": 110,
		},
	]


def execute_my_tasks(filters=None, *, user=None, today=None):
	user = user or frappe.session.user
	day = _today(today)
	raw = report_filters_dict(filters)
	# Always force assignee to the current user — ignore client override.
	raw["assigned_to"] = user
	normalized = normalize_filters(raw)
	normalized["assigned_to"] = user

	rows = get_task_rows(
		normalized,
		user=user,
		fields=REPORT_FIELDS,
		order_by="due_date asc, modified desc",
	)
	data = []
	for row in rows:
		status = _row_get(row, "status")
		data.append(
			{
				"name": _row_get(row, "name"),
				"subject": _row_get(row, "subject"),
				"status": status,
				"priority": _row_get(row, "priority"),
				"due_date": _row_get(row, "due_date"),
				"project": _row_get(row, "project"),
				"department": _row_get(row, "department"),
				"created_by": _created_by_display(row),
				"modified": _row_get(row, "modified"),
				"days_overdue": days_overdue(_row_get(row, "due_date"), status, day),
			}
		)

	summary = build_summary_from_rows(rows, today=day)
	report_summary = _summary_items(
		[
			("Total", summary["total"]),
			("Open", summary["open"]),
			("Working", summary["working"]),
			("Pending", summary["pending"]),
			("Overdue", summary["overdue"]),
		]
	)
	return my_tasks_columns(), data, None, None, report_summary


# ---------------------------------------------------------------------------
# Team Tasks
# ---------------------------------------------------------------------------


def team_tasks_columns():
	return _base_columns_task_id_title() + [
		{
			"label": "Assigned To",
			"fieldname": "assigned_to",
			"fieldtype": "Link",
			"options": "User",
			"width": 160,
		},
		{"label": "Status", "fieldname": "status", "fieldtype": "Data", "width": 100},
		{"label": "Priority", "fieldname": "priority", "fieldtype": "Data", "width": 90},
		{"label": "Due Date", "fieldname": "due_date", "fieldtype": "Date", "width": 110},
		{
			"label": "Days Overdue",
			"fieldname": "days_overdue",
			"fieldtype": "Int",
			"width": 110,
		},
		{
			"label": "Project",
			"fieldname": "project",
			"fieldtype": "Link",
			"options": "Project",
			"width": 140,
		},
		{
			"label": "Department",
			"fieldname": "department",
			"fieldtype": "Link",
			"options": "Department",
			"width": 140,
		},
		{
			"label": "Created By",
			"fieldname": "created_by",
			"fieldtype": "Link",
			"options": "User",
			"width": 160,
		},
		{"label": "Modified", "fieldname": "modified", "fieldtype": "Datetime", "width": 150},
	]


def execute_team_tasks(filters=None, *, user=None, today=None):
	user = user or frappe.session.user
	day = _today(today)
	normalized = normalize_filters(report_filters_dict(filters))
	rows = get_task_rows(
		normalized,
		user=user,
		fields=REPORT_FIELDS,
		order_by="modified desc",
	)
	data = []
	active = 0
	for row in rows:
		status = _row_get(row, "status")
		if status in ACTIVE_STATUSES:
			active += 1
		data.append(
			{
				"name": _row_get(row, "name"),
				"subject": _row_get(row, "subject"),
				"assigned_to": _row_get(row, "assigned_to"),
				"status": status,
				"priority": _row_get(row, "priority"),
				"due_date": _row_get(row, "due_date"),
				"days_overdue": days_overdue(_row_get(row, "due_date"), status, day),
				"project": _row_get(row, "project"),
				"department": _row_get(row, "department"),
				"created_by": _created_by_display(row),
				"modified": _row_get(row, "modified"),
			}
		)
	summary = build_summary_from_rows(rows, today=day)
	report_summary = _summary_items(
		[
			("Total", summary["total"]),
			("Completed", summary["completed"]),
			("Active", active),
			("Overdue", summary["overdue"]),
		]
	)
	return team_tasks_columns(), data, None, None, report_summary


# ---------------------------------------------------------------------------
# Overdue Tasks
# ---------------------------------------------------------------------------


def overdue_tasks_columns():
	return _base_columns_task_id_title() + [
		{
			"label": "Assigned To",
			"fieldname": "assigned_to",
			"fieldtype": "Link",
			"options": "User",
			"width": 160,
		},
		{"label": "Status", "fieldname": "status", "fieldtype": "Data", "width": 100},
		{"label": "Priority", "fieldname": "priority", "fieldtype": "Data", "width": 90},
		{"label": "Due Date", "fieldname": "due_date", "fieldtype": "Date", "width": 110},
		{
			"label": "Days Overdue",
			"fieldname": "days_overdue",
			"fieldtype": "Int",
			"width": 110,
		},
		{
			"label": "Aging Bucket",
			"fieldname": "aging_bucket",
			"fieldtype": "Data",
			"width": 110,
		},
		{
			"label": "Project",
			"fieldname": "project",
			"fieldtype": "Link",
			"options": "Project",
			"width": 140,
		},
		{
			"label": "Department",
			"fieldname": "department",
			"fieldtype": "Link",
			"options": "Department",
			"width": 140,
		},
		{
			"label": "Created By",
			"fieldname": "created_by",
			"fieldtype": "Link",
			"options": "User",
			"width": 160,
		},
	]


def execute_overdue_tasks(filters=None, *, user=None, today=None):
	user = user or frappe.session.user
	day = _today(today)
	raw = report_filters_dict(filters)
	aging_bucket = (raw.pop("aging_bucket", None) or "").strip() or None

	normalized = normalize_filters(raw)
	# Active statuses only; due on or before yesterday ⇒ overdue candidates at DB level.
	normalized["status"] = list(ACTIVE_STATUSES)
	normalized["due_date_to"] = (day - timedelta(days=1)).isoformat()

	rows = get_task_rows(
		normalized,
		user=user,
		fields=REPORT_FIELDS,
		order_by="due_date asc",
	)
	data = []
	high_priority = 0
	eight_plus = 0
	thirty_plus = 0
	for row in rows:
		status = _row_get(row, "status")
		if status not in ACTIVE_STATUSES:
			continue
		days = days_overdue(_row_get(row, "due_date"), status, day)
		if days < 1:
			continue
		bucket = overdue_aging_bucket(days)
		if aging_bucket and bucket != aging_bucket:
			continue
		priority = _row_get(row, "priority") or ""
		if priority.lower() == "high":
			high_priority += 1
		if days >= 8:
			eight_plus += 1
		if days >= 30:
			thirty_plus += 1
		data.append(
			{
				"name": _row_get(row, "name"),
				"subject": _row_get(row, "subject"),
				"assigned_to": _row_get(row, "assigned_to"),
				"status": status,
				"priority": priority,
				"due_date": _row_get(row, "due_date"),
				"days_overdue": days,
				"aging_bucket": bucket,
				"project": _row_get(row, "project"),
				"department": _row_get(row, "department"),
				"created_by": _created_by_display(row),
			}
		)

	report_summary = _summary_items(
		[
			("Total Overdue", len(data)),
			("High Priority", high_priority),
			("8+ Days", eight_plus),
			("30+ Days", thirty_plus),
		]
	)
	return overdue_tasks_columns(), data, None, None, report_summary


# ---------------------------------------------------------------------------
# Pending Aging
# ---------------------------------------------------------------------------


def pending_aging_columns():
	return _base_columns_task_id_title() + [
		{
			"label": "Assigned To",
			"fieldname": "assigned_to",
			"fieldtype": "Link",
			"options": "User",
			"width": 160,
		},
		{"label": "Status", "fieldname": "status", "fieldtype": "Data", "width": 100},
		{"label": "Priority", "fieldname": "priority", "fieldtype": "Data", "width": 90},
		{"label": "Created On", "fieldname": "creation", "fieldtype": "Datetime", "width": 150},
		{
			"label": "Pending Age Days",
			"fieldname": "pending_age_days",
			"fieldtype": "Int",
			"width": 130,
		},
		{
			"label": "Pending Aging Bucket",
			"fieldname": "pending_aging_bucket",
			"fieldtype": "Data",
			"width": 140,
		},
		{"label": "Due Date", "fieldname": "due_date", "fieldtype": "Date", "width": 110},
		{
			"label": "Days Overdue",
			"fieldname": "days_overdue",
			"fieldtype": "Int",
			"width": 110,
		},
		{
			"label": "Project",
			"fieldname": "project",
			"fieldtype": "Link",
			"options": "Project",
			"width": 140,
		},
		{
			"label": "Department",
			"fieldname": "department",
			"fieldtype": "Link",
			"options": "Department",
			"width": 140,
		},
	]


def execute_pending_aging(filters=None, *, user=None, today=None):
	user = user or frappe.session.user
	day = _today(today)
	raw = report_filters_dict(filters)
	pending_bucket = (raw.pop("pending_aging_bucket", None) or "").strip() or None

	normalized = normalize_filters(raw)
	# Only active statuses; allow optional status subset within active set.
	status = normalized.get("status")
	if status:
		if isinstance(status, str):
			status_list = [status]
		else:
			status_list = list(status)
		status_list = [s for s in status_list if s in ACTIVE_STATUSES]
		if not status_list:
			status_list = list(ACTIVE_STATUSES)
		normalized["status"] = status_list if len(status_list) > 1 else status_list[0]
	else:
		normalized["status"] = list(ACTIVE_STATUSES)

	rows = get_task_rows(
		normalized,
		user=user,
		fields=REPORT_FIELDS,
		order_by="creation asc",
	)
	data = []
	eight_plus = 0
	sixteen_plus = 0
	thirty_plus = 0
	for row in rows:
		status = _row_get(row, "status")
		if status not in ACTIVE_STATUSES:
			continue
		age = pending_age_days(_row_get(row, "creation"), day)
		bucket = pending_aging_bucket(age)
		if pending_bucket and bucket != pending_bucket:
			continue
		if age >= 8:
			eight_plus += 1
		if age >= 16:
			sixteen_plus += 1
		if age >= 30:
			thirty_plus += 1
		data.append(
			{
				"name": _row_get(row, "name"),
				"subject": _row_get(row, "subject"),
				"assigned_to": _row_get(row, "assigned_to"),
				"status": status,
				"priority": _row_get(row, "priority"),
				"creation": _row_get(row, "creation"),
				"pending_age_days": age,
				"pending_aging_bucket": bucket,
				"due_date": _row_get(row, "due_date"),
				"days_overdue": days_overdue(_row_get(row, "due_date"), status, day),
				"project": _row_get(row, "project"),
				"department": _row_get(row, "department"),
			}
		)

	report_summary = _summary_items(
		[
			("Total Active", len(data)),
			("8+ Days", eight_plus),
			("16+ Days", sixteen_plus),
			("30+ Days", thirty_plus),
		]
	)
	return pending_aging_columns(), data, None, None, report_summary
