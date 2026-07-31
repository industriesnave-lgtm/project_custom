"""Shared builders for NAVE Task Script Reports (Phase 3 — Batches 7B/7C/7D).

Thin report modules call these helpers. Permission and filter normalization
come from nave_task_reporting.py — not duplicated per report.

Week periods use Monday–Sunday (ISO-style) consistently — no separate
system week-start setting is consulted in this app.
"""

from __future__ import annotations

import re
from datetime import date, timedelta

import frappe

from project_custom.nave_task_reporting import (
	_as_date,
	_row_get,
	build_summary_from_rows,
	get_task_rows,
	normalize_filters,
)
from project_custom.nave_task_utils import (
	ACTIVE_STATUSES,
	DIRECTOR_ROLE,
	MANAGER_ROLE,
	SYSTEM_MANAGER_ROLE,
	is_manager_level_user,
	is_reopen_transition,
	is_terminal_status,
)


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
	"""Convert Script Report / API filters (_dict / dict / JSON str) to a plain dict.

	Desk RPC often passes filters as a JSON string. Calling dict() on a string
	raises ValueError ("dictionary update sequence element #0 has length 1").
	"""
	if not filters:
		return {}
	if isinstance(filters, str):
		parse_json = getattr(frappe, "parse_json", None)
		if callable(parse_json):
			filters = parse_json(filters) or {}
		else:
			import json

			filters = json.loads(filters) if filters.strip() else {}
	if hasattr(filters, "items"):
		return {k: v for k, v in filters.items() if v not in (None, "")}
	# Refuse opaque sequences (e.g. list of field names) that dict() would misread.
	frappe.throw("Report filters must be a dictionary.", frappe.ValidationError)



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


def _summary_items(pairs: list) -> list[dict]:
	"""Build Script Report summary cards. Pair is (label, value) or (label, value, datatype)."""
	items = []
	for pair in pairs:
		if len(pair) == 3:
			label, value, datatype = pair
		else:
			label, value = pair
			datatype = "Int"
		if datatype in ("Float", "Percent"):
			items.append({"label": label, "value": float(value or 0), "datatype": datatype})
		else:
			items.append({"label": label, "value": int(value or 0), "datatype": "Int"})
	return items


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


# ---------------------------------------------------------------------------
# Department / Project aggregates (Batch 7C Part 1)
# ---------------------------------------------------------------------------


def _empty_group_stats():
	return {
		"total": 0,
		"open": 0,
		"working": 0,
		"pending": 0,
		"completed": 0,
		"closed": 0,
		"overdue": 0,
		"due_today": 0,
		"high_priority": 0,
		"last_activity": None,
	}


def _completion_pct(completed: int, total: int) -> float:
	if not total:
		return 0.0
	return round((completed / total) * 100.0, 1)


def _bump_group_stats(stats: dict, row, today: date) -> None:
	status = (_row_get(row, "status") or "").strip()
	priority = (_row_get(row, "priority") or "").strip()
	due_date = _row_get(row, "due_date")
	is_overdue_flag = _row_get(row, "is_overdue")
	modified = _row_get(row, "modified")

	stats["total"] += 1
	key = {
		"Open": "open",
		"Working": "working",
		"Pending": "pending",
		"Completed": "completed",
		"Closed": "closed",
	}.get(status)
	if key:
		stats[key] += 1
	if priority.lower() == "high":
		stats["high_priority"] += 1

	due = _as_date(due_date)
	if due == today and not is_terminal_status(status):
		stats["due_today"] += 1

	if not is_terminal_status(status):
		if is_overdue_flag is not None and is_overdue_flag != "":
			if int(is_overdue_flag or 0) == 1:
				stats["overdue"] += 1
		elif days_overdue(due_date, status, today) > 0:
			stats["overdue"] += 1

	if modified:
		prev = stats["last_activity"]
		if not prev or str(modified) > str(prev):
			stats["last_activity"] = modified


def aggregate_by_key(rows, *, group_field: str, empty_label: str, today=None) -> dict[str, dict]:
	"""Single-pass group aggregation for department/project reports."""
	day = _today(today)
	groups: dict[str, dict] = {}
	for row in rows or []:
		raw = _row_get(row, group_field)
		label = (str(raw).strip() if raw else "") or empty_label
		if label not in groups:
			groups[label] = _empty_group_stats()
		_bump_group_stats(groups[label], row, day)
	return groups


def department_task_columns():
	return [
		{
			"label": "Department",
			"fieldname": "department",
			"fieldtype": "Data",
			"width": 180,
		},
		{"label": "Total Tasks", "fieldname": "total", "fieldtype": "Int", "width": 100},
		{"label": "Open", "fieldname": "open", "fieldtype": "Int", "width": 80},
		{"label": "Working", "fieldname": "working", "fieldtype": "Int", "width": 90},
		{"label": "Pending", "fieldname": "pending", "fieldtype": "Int", "width": 90},
		{"label": "Completed", "fieldname": "completed", "fieldtype": "Int", "width": 100},
		{"label": "Closed", "fieldname": "closed", "fieldtype": "Int", "width": 80},
		{"label": "Overdue", "fieldname": "overdue", "fieldtype": "Int", "width": 90},
		{"label": "Due Today", "fieldname": "due_today", "fieldtype": "Int", "width": 90},
		{"label": "High Priority", "fieldname": "high_priority", "fieldtype": "Int", "width": 110},
		{
			"label": "Completion %",
			"fieldname": "completion_pct",
			"fieldtype": "Percent",
			"width": 110,
		},
	]


def execute_department_task_report(filters=None, *, user=None, today=None):
	user = user or frappe.session.user
	day = _today(today)
	normalized = normalize_filters(report_filters_dict(filters))
	rows = get_task_rows(
		normalized,
		user=user,
		fields=REPORT_FIELDS,
		order_by="department asc, modified desc",
	)
	groups = aggregate_by_key(
		rows,
		group_field="department",
		empty_label="(No Department)",
		today=day,
	)
	data = []
	for department in sorted(groups.keys(), key=lambda x: (x.startswith("("), x.lower())):
		stats = groups[department]
		data.append(
			{
				"department": department,
				"total": stats["total"],
				"open": stats["open"],
				"working": stats["working"],
				"pending": stats["pending"],
				"completed": stats["completed"],
				"closed": stats["closed"],
				"overdue": stats["overdue"],
				"due_today": stats["due_today"],
				"high_priority": stats["high_priority"],
				"completion_pct": _completion_pct(stats["completed"], stats["total"]),
			}
		)

	total_tasks = sum(r["total"] for r in data)
	total_completed = sum(r["completed"] for r in data)
	total_overdue = sum(r["overdue"] for r in data)
	report_summary = _summary_items(
		[
			("Departments", len(data)),
			("Total Tasks", total_tasks),
			("Completed", total_completed),
			("Overdue", total_overdue),
		]
	)
	return department_task_columns(), data, None, None, report_summary


def project_task_columns():
	return [
		{
			"label": "Project",
			"fieldname": "project",
			"fieldtype": "Link",
			"options": "Project",
			"width": 180,
		},
		{"label": "Total Tasks", "fieldname": "total", "fieldtype": "Int", "width": 100},
		{"label": "Open", "fieldname": "open", "fieldtype": "Int", "width": 80},
		{"label": "Working", "fieldname": "working", "fieldtype": "Int", "width": 90},
		{"label": "Pending", "fieldname": "pending", "fieldtype": "Int", "width": 90},
		{"label": "Completed", "fieldname": "completed", "fieldtype": "Int", "width": 100},
		{"label": "Closed", "fieldname": "closed", "fieldtype": "Int", "width": 80},
		{"label": "Overdue", "fieldname": "overdue", "fieldtype": "Int", "width": 90},
		{
			"label": "Completion %",
			"fieldname": "completion_pct",
			"fieldtype": "Percent",
			"width": 110,
		},
		{
			"label": "Last Activity",
			"fieldname": "last_activity",
			"fieldtype": "Datetime",
			"width": 150,
		},
	]


def execute_project_task_report(filters=None, *, user=None, today=None):
	user = user or frappe.session.user
	day = _today(today)
	normalized = normalize_filters(report_filters_dict(filters))
	rows = get_task_rows(
		normalized,
		user=user,
		fields=REPORT_FIELDS,
		order_by="project asc, modified desc",
	)
	groups = aggregate_by_key(
		rows,
		group_field="project",
		empty_label="(No Project)",
		today=day,
	)
	data = []
	for project in sorted(groups.keys(), key=lambda x: (x.startswith("("), x.lower())):
		stats = groups[project]
		# Empty project groups are retained; Link value left blank for Desk safety.
		data.append(
			{
				"project": None if project == "(No Project)" else project,
				"total": stats["total"],
				"open": stats["open"],
				"working": stats["working"],
				"pending": stats["pending"],
				"completed": stats["completed"],
				"closed": stats["closed"],
				"overdue": stats["overdue"],
				"completion_pct": _completion_pct(stats["completed"], stats["total"]),
				"last_activity": stats["last_activity"],
				"_empty_project": project == "(No Project)",
			}
		)

	total_tasks = sum(r["total"] for r in data)
	total_completed = sum(r["completed"] for r in data)
	total_overdue = sum(r["overdue"] for r in data)
	report_summary = _summary_items(
		[
			("Projects", len(data)),
			("Total Tasks", total_tasks),
			("Completed", total_completed),
			("Overdue", total_overdue),
		]
	)
	return project_task_columns(), data, None, None, report_summary


# ---------------------------------------------------------------------------
# Employee Performance & Completed Tasks (Batch 7C Part 2)
# ---------------------------------------------------------------------------

PERFORMANCE_FIELDS = REPORT_FIELDS + (
	"completed_on",
	"completion_remarks",
	"completion_attachment",
)

COMPLETED_REPORT_FIELDS = PERFORMANCE_FIELDS

COMPLETED_ONLY_STATUSES = ("Completed", "Closed")

_STATUS_CHANGE_RE = re.compile(
	r"^Status changed from (.+?) to (.+?)\.?$",
	re.IGNORECASE,
)


def _user_is_manager_level(user: str) -> bool:
	roles = frappe.get_roles(user) or []
	return is_manager_level_user(
		is_admin=(user == "Administrator" or SYSTEM_MANAGER_ROLE in roles),
		is_director=DIRECTOR_ROLE in roles,
		is_manager=MANAGER_ROLE in roles,
	)


def completion_days(creation, completed_on) -> int | None:
	"""Days from creation date to completed_on date; None if either missing."""
	created = _as_date(creation)
	done = _as_date(completed_on)
	if not created or not done:
		return None
	return max((done - created).days, 0)


def delay_days(completed_on_or_today, due_date) -> int | None:
	"""max(end_date - due_date, 0); None when due_date missing."""
	due = _as_date(due_date)
	end = _as_date(completed_on_or_today)
	if not due or not end:
		return None
	return max((end - due).days, 0)


def classify_completion_result(completed_on, due_date) -> str:
	due = _as_date(due_date)
	done = _as_date(completed_on)
	if not due:
		return "No Due Date"
	if not done:
		return "No Due Date"
	if done <= due:
		return "On Time"
	return "Late"


def parse_status_change_text(update_text: str | None) -> tuple[str | None, str | None]:
	match = _STATUS_CHANGE_RE.match((update_text or "").strip())
	if not match:
		return None, None
	old_status = match.group(1).strip()
	new_status = match.group(2).strip()
	if old_status in ("—", "-", ""):
		old_status = None
	if new_status in ("—", "-", ""):
		new_status = None
	return old_status, new_status


def get_reopen_counts_by_task(task_names: list[str]) -> dict[str, int]:
	"""
	Count reopen transitions from NAVE Task Update Status Change history.

	Uses one bulk query. If history cannot be loaded, returns {} (callers treat
	missing keys as 0 — documented fallback, no schema changes).
	"""
	names = [n for n in (task_names or []) if n]
	if not names:
		return {}
	try:
		rows = frappe.get_all(
			"NAVE Task Update",
			filters={
				"task": ["in", names],
				"update_type": "Status Change",
			},
			fields=["task", "update_text"],
			limit_page_length=50000,
		)
	except Exception:
		return {}

	counts: dict[str, int] = {}
	for row in rows or []:
		task = _row_get(row, "task")
		old_status, new_status = parse_status_change_text(_row_get(row, "update_text"))
		if not task or not is_reopen_transition(old_status, new_status):
			continue
		counts[task] = counts.get(task, 0) + 1
	return counts


def _empty_employee_stats():
	return {
		"total": 0,
		"completed": 0,
		"closed": 0,
		"active": 0,
		"pending": 0,
		"overdue": 0,
		"reopened": 0,
		"on_time": 0,
		"late": 0,
		"completion_days_sum": 0,
		"completion_days_n": 0,
		"delay_days_sum": 0,
		"delay_days_n": 0,
		"last_activity": None,
		"_task_names": [],
	}


def _bump_employee_stats(stats: dict, row, today: date) -> None:
	status = (_row_get(row, "status") or "").strip()
	due_date = _row_get(row, "due_date")
	completed_on = _row_get(row, "completed_on")
	is_overdue_flag = _row_get(row, "is_overdue")
	modified = _row_get(row, "modified")
	name = _row_get(row, "name")

	stats["total"] += 1
	if name:
		stats["_task_names"].append(name)

	if status == "Completed":
		stats["completed"] += 1
	elif status == "Closed":
		stats["closed"] += 1
	elif status in ACTIVE_STATUSES:
		stats["active"] += 1
		if status == "Pending":
			stats["pending"] += 1

	if status in ACTIVE_STATUSES:
		overdue = False
		if is_overdue_flag is not None and is_overdue_flag != "":
			overdue = int(is_overdue_flag or 0) == 1
		else:
			overdue = days_overdue(due_date, status, today) > 0
		if overdue:
			stats["overdue"] += 1
			d = delay_days(today, due_date)
			if d is not None:
				stats["delay_days_sum"] += d
				stats["delay_days_n"] += 1

	if status in COMPLETED_ONLY_STATUSES:
		result = classify_completion_result(completed_on, due_date)
		if result == "On Time":
			stats["on_time"] += 1
		elif result == "Late":
			stats["late"] += 1
		cd = completion_days(_row_get(row, "creation"), completed_on)
		if cd is not None:
			stats["completion_days_sum"] += cd
			stats["completion_days_n"] += 1
		d = delay_days(completed_on, due_date)
		if d is not None:
			stats["delay_days_sum"] += d
			stats["delay_days_n"] += 1

	if modified:
		prev = stats["last_activity"]
		if not prev or str(modified) > str(prev):
			stats["last_activity"] = modified


def _avg(sum_value: float, count: int) -> float:
	if not count:
		return 0.0
	return round(sum_value / count, 1)


def employee_performance_columns():
	return [
		{
			"label": "Employee / Assigned User",
			"fieldname": "assigned_to",
			"fieldtype": "Data",
			"width": 180,
		},
		{"label": "Total Assigned", "fieldname": "total_assigned", "fieldtype": "Int", "width": 110},
		{"label": "Completed", "fieldname": "completed", "fieldtype": "Int", "width": 100},
		{"label": "Closed", "fieldname": "closed", "fieldtype": "Int", "width": 80},
		{"label": "Active", "fieldname": "active", "fieldtype": "Int", "width": 80},
		{"label": "Pending", "fieldname": "pending", "fieldtype": "Int", "width": 90},
		{"label": "Overdue", "fieldname": "overdue", "fieldtype": "Int", "width": 90},
		{"label": "Reopened", "fieldname": "reopened", "fieldtype": "Int", "width": 90},
		{
			"label": "Completion %",
			"fieldname": "completion_pct",
			"fieldtype": "Percent",
			"width": 110,
		},
		{
			"label": "On-Time Completed",
			"fieldname": "on_time_completed",
			"fieldtype": "Int",
			"width": 130,
		},
		{
			"label": "Late Completed",
			"fieldname": "late_completed",
			"fieldtype": "Int",
			"width": 120,
		},
		{
			"label": "Average Completion Days",
			"fieldname": "avg_completion_days",
			"fieldtype": "Float",
			"width": 150,
		},
		{
			"label": "Average Delay Days",
			"fieldname": "avg_delay_days",
			"fieldtype": "Float",
			"width": 140,
		},
		{
			"label": "Last Activity",
			"fieldname": "last_activity",
			"fieldtype": "Datetime",
			"width": 150,
		},
	]


def execute_employee_performance_report(filters=None, *, user=None, today=None):
	user = user or frappe.session.user
	day = _today(today)
	raw = report_filters_dict(filters)
	manager_level = _user_is_manager_level(user)
	# Employees may only see their own performance row — ignore client override.
	if not manager_level:
		raw["assigned_to"] = user
	normalized = normalize_filters(raw)
	if not manager_level:
		normalized["assigned_to"] = user

	rows = get_task_rows(
		normalized,
		user=user,
		fields=PERFORMANCE_FIELDS,
		order_by="assigned_to asc, modified desc",
	)

	groups: dict[str, dict] = {}
	for row in rows:
		assignee = (_row_get(row, "assigned_to") or "").strip() or "Unassigned"
		if assignee not in groups:
			groups[assignee] = _empty_employee_stats()
		_bump_employee_stats(groups[assignee], row, day)

	all_task_names = []
	for stats in groups.values():
		all_task_names.extend(stats["_task_names"])
	reopen_by_task = get_reopen_counts_by_task(all_task_names)

	data = []
	for assignee in sorted(groups.keys(), key=lambda x: (x == "Unassigned", x.lower())):
		stats = groups[assignee]
		reopened = sum(reopen_by_task.get(n, 0) for n in stats["_task_names"])
		done = stats["completed"] + stats["closed"]
		data.append(
			{
				"assigned_to": assignee,
				"total_assigned": stats["total"],
				"completed": stats["completed"],
				"closed": stats["closed"],
				"active": stats["active"],
				"pending": stats["pending"],
				"overdue": stats["overdue"],
				"reopened": reopened,
				"completion_pct": _completion_pct(done, stats["total"]),
				"on_time_completed": stats["on_time"],
				"late_completed": stats["late"],
				"avg_completion_days": _avg(
					stats["completion_days_sum"], stats["completion_days_n"]
				),
				"avg_delay_days": _avg(stats["delay_days_sum"], stats["delay_days_n"]),
				"last_activity": stats["last_activity"],
			}
		)

	total_assigned = sum(r["total_assigned"] for r in data)
	total_done = sum(r["completed"] + r["closed"] for r in data)
	total_active = sum(r["active"] for r in data)
	total_overdue = sum(r["overdue"] for r in data)
	report_summary = _summary_items(
		[
			("Employees", len(data)),
			("Total Assigned", total_assigned),
			("Completed/Closed", total_done),
			("Active", total_active),
			("Overdue", total_overdue),
			(
				"Overall Completion %",
				_completion_pct(total_done, total_assigned),
				"Percent",
			),
		]
	)
	return employee_performance_columns(), data, None, None, report_summary


def completed_task_columns():
	return [
		{
			"label": "Task ID",
			"fieldname": "name",
			"fieldtype": "Link",
			"options": "NAVE Task",
			"width": 140,
		},
		{"label": "Title", "fieldname": "subject", "fieldtype": "Data", "width": 220},
		{
			"label": "Assigned To",
			"fieldname": "assigned_to",
			"fieldtype": "Link",
			"options": "User",
			"width": 160,
		},
		{"label": "Status", "fieldname": "status", "fieldtype": "Data", "width": 100},
		{"label": "Priority", "fieldname": "priority", "fieldtype": "Data", "width": 90},
		{
			"label": "Created On",
			"fieldname": "creation",
			"fieldtype": "Datetime",
			"width": 150,
		},
		{"label": "Due Date", "fieldname": "due_date", "fieldtype": "Date", "width": 110},
		{
			"label": "Completed On",
			"fieldname": "completed_on",
			"fieldtype": "Datetime",
			"width": 150,
		},
		{
			"label": "Completion Days",
			"fieldname": "completion_days",
			"fieldtype": "Int",
			"width": 120,
		},
		{"label": "Delay Days", "fieldname": "delay_days", "fieldtype": "Int", "width": 100},
		{
			"label": "Completion Result",
			"fieldname": "completion_result",
			"fieldtype": "Data",
			"width": 120,
		},
		{
			"label": "Completion Remarks",
			"fieldname": "completion_remarks",
			"fieldtype": "Data",
			"width": 200,
		},
		{
			"label": "Completion Attachment",
			"fieldname": "completion_attachment",
			"fieldtype": "Attach",
			"width": 160,
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
		{
			"label": "Last Modified",
			"fieldname": "modified",
			"fieldtype": "Datetime",
			"width": 150,
		},
	]


def _normalize_completed_report_filters(raw: dict) -> dict:
	normalized = normalize_filters(raw)
	allowed = set(COMPLETED_ONLY_STATUSES)
	status = normalized.get("status")
	if status:
		if isinstance(status, list):
			statuses = [s for s in status if s in allowed]
		else:
			statuses = [status] if status in allowed else []
		normalized["status"] = statuses or list(COMPLETED_ONLY_STATUSES)
	else:
		normalized["status"] = list(COMPLETED_ONLY_STATUSES)
	return normalized


def execute_completed_task_report(filters=None, *, user=None, today=None):
	user = user or frappe.session.user
	_today(today)  # keep signature parity / future use
	raw = report_filters_dict(filters)
	normalized = _normalize_completed_report_filters(raw)
	result_filter = normalized.pop("completion_result", None)

	rows = get_task_rows(
		normalized,
		user=user,
		fields=COMPLETED_REPORT_FIELDS,
		order_by="completed_on desc, modified desc",
	)

	data = []
	on_time = late = no_due = 0
	completion_sum = completion_n = 0
	delay_sum = delay_n = 0

	for row in rows:
		status = (_row_get(row, "status") or "").strip()
		if status not in COMPLETED_ONLY_STATUSES:
			continue
		completed_on = _row_get(row, "completed_on")
		due_date = _row_get(row, "due_date")
		creation = _row_get(row, "creation")
		result = classify_completion_result(completed_on, due_date)
		if result_filter and result != result_filter:
			continue

		cd = completion_days(creation, completed_on)
		dd = delay_days(completed_on, due_date)

		if result == "On Time":
			on_time += 1
		elif result == "Late":
			late += 1
		else:
			no_due += 1
		if cd is not None:
			completion_sum += cd
			completion_n += 1
		if dd is not None:
			delay_sum += dd
			delay_n += 1

		data.append(
			{
				"name": _row_get(row, "name"),
				"subject": _row_get(row, "subject"),
				"assigned_to": _row_get(row, "assigned_to"),
				"status": status,
				"priority": _row_get(row, "priority"),
				"creation": creation,
				"due_date": due_date,
				"completed_on": completed_on,
				"completion_days": cd,
				"delay_days": dd,
				"completion_result": result,
				"completion_remarks": _row_get(row, "completion_remarks"),
				"completion_attachment": _row_get(row, "completion_attachment"),
				"project": _row_get(row, "project"),
				"department": _row_get(row, "department"),
				"created_by": _created_by_display(row),
				"modified": _row_get(row, "modified"),
			}
		)

	report_summary = _summary_items(
		[
			("Total Completed", len(data)),
			("On Time", on_time),
			("Late", late),
			("No Due Date", no_due),
			("Average Completion Days", _avg(completion_sum, completion_n), "Float"),
			("Average Delay Days", _avg(delay_sum, delay_n), "Float"),
		]
	)
	return completed_task_columns(), data, None, None, report_summary


# ---------------------------------------------------------------------------
# Weekly / Monthly Task Summary (Batch 7D)
# ---------------------------------------------------------------------------
#
# Historical-status limitation:
# "Active at Period End" and "Overdue at Period End" use the task's *current*
# status (and due_date) as of report run time — not a reconstructed historical
# status snapshot. Tasks created on/before the effective period end that are
# still Open/Working/Pending are counted. Exact past status is unavailable
# without schema/history changes (out of scope for Batch 7D).
#
# Week convention: Monday–Sunday.

MAX_SUMMARY_RANGE_DAYS = 365 * 5 + 1

PERIOD_REPORT_FIELDS = (
	"name",
	"status",
	"priority",
	"assigned_to",
	"department",
	"project",
	"due_date",
	"is_overdue",
	"creation",
	"completed_on",
	"modified",
)


def _throw_validation(message: str) -> None:
	exc = getattr(frappe, "ValidationError", None) or Exception
	frappe.throw(message, exc)


def validate_summary_date_range(from_date: date, to_date: date) -> None:
	"""Reject inverted ranges and spans longer than 5 years."""
	if from_date > to_date:
		_throw_validation("From Date cannot be after To Date.")
	if (to_date - from_date).days > MAX_SUMMARY_RANGE_DAYS:
		_throw_validation("Date range cannot exceed 5 years.")


def week_start_monday(day: date) -> date:
	"""Monday of the calendar week containing day (Monday=0)."""
	return day - timedelta(days=day.weekday())


def generate_week_periods(from_date: date, to_date: date) -> list[dict]:
	"""
	Monday–Sunday weeks that overlap [from_date, to_date].
	Partial first/last weeks are included; activity is clipped later.
	"""
	validate_summary_date_range(from_date, to_date)
	periods = []
	cursor = week_start_monday(from_date)
	while cursor <= to_date:
		end = cursor + timedelta(days=6)
		periods.append(
			{
				"key": cursor.isoformat(),
				"label": f"{cursor.strftime('%d %b %Y')} – {end.strftime('%d %b %Y')}",
				"start": cursor,
				"end": end,
			}
		)
		cursor += timedelta(days=7)
	return periods


def generate_month_periods(from_date: date, to_date: date) -> list[dict]:
	"""Calendar months that overlap [from_date, to_date]."""
	validate_summary_date_range(from_date, to_date)
	periods = []
	year, month = from_date.year, from_date.month
	while True:
		start = date(year, month, 1)
		if start > to_date:
			break
		if month == 12:
			end = date(year, 12, 31)
			next_year, next_month = year + 1, 1
		else:
			end = date(year, month + 1, 1) - timedelta(days=1)
			next_year, next_month = year, month + 1
		periods.append(
			{
				"key": f"{year:04d}-{month:02d}",
				"label": start.strftime("%B %Y"),
				"start": start,
				"end": end,
			}
		)
		year, month = next_year, next_month
	return periods


def _empty_period_stats() -> dict:
	return {
		"tasks_created": 0,
		"completed": 0,
		"closed": 0,
		"active_at_end": 0,
		"overdue_at_end": 0,
		"on_time": 0,
		"late": 0,
		"completion_days_sum": 0,
		"completion_days_n": 0,
		"delay_days_sum": 0,
		"delay_days_n": 0,
	}


def _period_activity_window(period: dict, from_date: date, to_date: date) -> tuple[date, date]:
	return max(period["start"], from_date), min(period["end"], to_date)


def _period_effective_end(period: dict, to_date: date) -> date:
	return min(period["end"], to_date)


def _resolve_summary_range(filters=None, *, today=None) -> tuple[dict, date, date, date]:
	day = _today(today)
	raw = report_filters_dict(filters)
	from_date = _as_date(raw.get("from_date")) or date(day.year, 1, 1)
	to_date = _as_date(raw.get("to_date")) or day
	validate_summary_date_range(from_date, to_date)
	raw["from_date"] = from_date.isoformat()
	raw["to_date"] = to_date.isoformat()
	return raw, from_date, to_date, day


def _fetch_period_report_rows(raw_filters: dict, *, user: str, to_date: date):
	"""
	One permission-aware fetch for period reports.

	Drops from_date so tasks created before the selected range remain available
	for Active/Overdue-at-period-end (current-status snapshot). Keeps to_date so
	creation is capped at the report end.
	"""
	normalized = normalize_filters(raw_filters)
	normalized.pop("from_date", None)
	normalized["to_date"] = to_date.isoformat()
	return get_task_rows(
		normalized,
		user=user,
		fields=PERIOD_REPORT_FIELDS,
		order_by="creation asc",
		limit_page_length=50000,
	)


def _find_period_for_date(periods_by_key: dict, kind: str, day: date):
	if kind == "week":
		key = week_start_monday(day).isoformat()
	else:
		key = f"{day.year:04d}-{day.month:02d}"
	return periods_by_key.get(key)


def aggregate_period_stats(
	rows,
	periods: list[dict],
	*,
	from_date: date,
	to_date: date,
	kind: str,
) -> list[dict]:
	"""
	Single-pass aggregation into pre-built periods (including empty zeros).

	kind: \"week\" | \"month\"
	"""
	stats_by_key = {p["key"]: _empty_period_stats() for p in periods}
	periods_by_key = {p["key"]: p for p in periods}

	for row in rows or []:
		status = (_row_get(row, "status") or "").strip()
		created = _as_date(_row_get(row, "creation"))
		completed_on = _as_date(_row_get(row, "completed_on"))
		due = _as_date(_row_get(row, "due_date"))

		if created and from_date <= created <= to_date:
			period = _find_period_for_date(periods_by_key, kind, created)
			if period:
				activity_start, activity_end = _period_activity_window(
					period, from_date, to_date
				)
				if activity_start <= created <= activity_end:
					stats_by_key[period["key"]]["tasks_created"] += 1

		if (
			completed_on
			and from_date <= completed_on <= to_date
			and status in COMPLETED_ONLY_STATUSES
		):
			period = _find_period_for_date(periods_by_key, kind, completed_on)
			if period:
				activity_start, activity_end = _period_activity_window(
					period, from_date, to_date
				)
				if activity_start <= completed_on <= activity_end:
					st = stats_by_key[period["key"]]
					if status == "Completed":
						st["completed"] += 1
					else:
						st["closed"] += 1
					result = classify_completion_result(completed_on, due)
					if result == "On Time":
						st["on_time"] += 1
					elif result == "Late":
						st["late"] += 1
					cd = completion_days(_row_get(row, "creation"), completed_on)
					if cd is not None:
						st["completion_days_sum"] += cd
						st["completion_days_n"] += 1
					dd = delay_days(completed_on, due)
					if dd is not None:
						st["delay_days_sum"] += dd
						st["delay_days_n"] += 1

		# Current-status snapshot for every period that had started by then.
		if created and status in ACTIVE_STATUSES:
			for period in periods:
				effective_end = _period_effective_end(period, to_date)
				if created > effective_end:
					continue
				st = stats_by_key[period["key"]]
				st["active_at_end"] += 1
				if due and due < effective_end:
					st["overdue_at_end"] += 1

	data = []
	for period in periods:
		st = stats_by_key[period["key"]]
		done = st["completed"] + st["closed"]
		data.append(
			{
				"period_label": period["label"],
				"period_start": period["start"],
				"period_end": period["end"],
				"tasks_created": st["tasks_created"],
				"completed": st["completed"],
				"closed": st["closed"],
				"completed_closed_total": done,
				"active_at_end": st["active_at_end"],
				"overdue_at_end": st["overdue_at_end"],
				"on_time_completed": st["on_time"],
				"late_completed": st["late"],
				"completion_pct": _completion_pct(done, st["tasks_created"]),
				"avg_completion_days": _avg(
					st["completion_days_sum"], st["completion_days_n"]
				),
				"avg_delay_days": _avg(st["delay_days_sum"], st["delay_days_n"]),
			}
		)
	return data


def build_period_report_summary(
	data: list[dict],
	rows,
	*,
	from_date: date,
	to_date: date,
) -> list[dict]:
	"""
	Report-level summary without summing Active/Overdue across periods
	(those would double-count). Active/Overdue = current-status snapshot as of
	to_date among tasks created on/before to_date.
	"""
	total_created = sum(r["tasks_created"] for r in data)
	total_done = sum(r["completed_closed_total"] for r in data)
	on_time = sum(r["on_time_completed"] for r in data)
	late = sum(r["late_completed"] for r in data)

	active = overdue = 0
	completion_sum = completion_n = 0
	delay_sum = delay_n = 0
	for row in rows or []:
		status = (_row_get(row, "status") or "").strip()
		created = _as_date(_row_get(row, "creation"))
		completed_on = _as_date(_row_get(row, "completed_on"))
		due = _as_date(_row_get(row, "due_date"))

		if created and created <= to_date and status in ACTIVE_STATUSES:
			active += 1
			if due and due < to_date:
				overdue += 1

		if (
			completed_on
			and from_date <= completed_on <= to_date
			and status in COMPLETED_ONLY_STATUSES
		):
			cd = completion_days(_row_get(row, "creation"), completed_on)
			if cd is not None:
				completion_sum += cd
				completion_n += 1
			dd = delay_days(completed_on, due)
			if dd is not None:
				delay_sum += dd
				delay_n += 1

	return _summary_items(
		[
			("Total Created", total_created),
			("Total Completed/Closed", total_done),
			("Active", active),
			("Overdue", overdue),
			("On-Time", on_time),
			("Late", late),
			(
				"Overall Completion %",
				_completion_pct(total_done, total_created),
				"Percent",
			),
			("Average Completion Days", _avg(completion_sum, completion_n), "Float"),
			("Average Delay Days", _avg(delay_sum, delay_n), "Float"),
		]
	)


def _period_summary_columns(*, label_field: str, label_title: str, start_title: str, end_title: str):
	return [
		{"label": label_title, "fieldname": label_field, "fieldtype": "Data", "width": 200},
		{"label": start_title, "fieldname": "period_start", "fieldtype": "Date", "width": 110},
		{"label": end_title, "fieldname": "period_end", "fieldtype": "Date", "width": 110},
		{"label": "Tasks Created", "fieldname": "tasks_created", "fieldtype": "Int", "width": 110},
		{"label": "Completed", "fieldname": "completed", "fieldtype": "Int", "width": 100},
		{"label": "Closed", "fieldname": "closed", "fieldtype": "Int", "width": 80},
		{
			"label": "Completed/Closed Total",
			"fieldname": "completed_closed_total",
			"fieldtype": "Int",
			"width": 150,
		},
		{
			"label": "Active at Period End",
			"fieldname": "active_at_end",
			"fieldtype": "Int",
			"width": 140,
		},
		{
			"label": "Overdue at Period End",
			"fieldname": "overdue_at_end",
			"fieldtype": "Int",
			"width": 150,
		},
		{
			"label": "On-Time Completed",
			"fieldname": "on_time_completed",
			"fieldtype": "Int",
			"width": 130,
		},
		{
			"label": "Late Completed",
			"fieldname": "late_completed",
			"fieldtype": "Int",
			"width": 120,
		},
		{
			"label": "Completion %",
			"fieldname": "completion_pct",
			"fieldtype": "Percent",
			"width": 110,
		},
		{
			"label": "Average Completion Days",
			"fieldname": "avg_completion_days",
			"fieldtype": "Float",
			"width": 150,
		},
		{
			"label": "Average Delay Days",
			"fieldname": "avg_delay_days",
			"fieldtype": "Float",
			"width": 140,
		},
	]


def weekly_task_summary_columns():
	return _period_summary_columns(
		label_field="week",
		label_title="Week",
		start_title="Week Start",
		end_title="Week End",
	)


def monthly_task_summary_columns():
	return _period_summary_columns(
		label_field="month",
		label_title="Month",
		start_title="Month Start",
		end_title="Month End",
	)


def _map_period_rows(data: list[dict], *, label_field: str) -> list[dict]:
	mapped = []
	for row in data:
		item = dict(row)
		item[label_field] = item.pop("period_label")
		mapped.append(item)
	return mapped


def execute_weekly_task_summary_report(filters=None, *, user=None, today=None):
	user = user or frappe.session.user
	raw, from_date, to_date, _day = _resolve_summary_range(filters, today=today)
	periods = generate_week_periods(from_date, to_date)
	rows = _fetch_period_report_rows(raw, user=user, to_date=to_date)
	data = aggregate_period_stats(
		rows,
		periods,
		from_date=from_date,
		to_date=to_date,
		kind="week",
	)
	mapped = _map_period_rows(data, label_field="week")
	summary = build_period_report_summary(
		data, rows, from_date=from_date, to_date=to_date
	)
	return weekly_task_summary_columns(), mapped, None, None, summary


def execute_monthly_task_summary_report(filters=None, *, user=None, today=None):
	user = user or frappe.session.user
	raw, from_date, to_date, _day = _resolve_summary_range(filters, today=today)
	periods = generate_month_periods(from_date, to_date)
	rows = _fetch_period_report_rows(raw, user=user, to_date=to_date)
	data = aggregate_period_stats(
		rows,
		periods,
		from_date=from_date,
		to_date=to_date,
		kind="month",
	)
	mapped = _map_period_rows(data, label_field="month")
	summary = build_period_report_summary(
		data, rows, from_date=from_date, to_date=to_date
	)
	return monthly_task_summary_columns(), mapped, None, None, summary
