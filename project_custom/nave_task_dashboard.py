"""NAVE Task Dashboard backend (Phase 4 — Batches 8A/8B).

Builds KPI cards, compact lists, widgets, and metadata on top of
nave_task_reporting. Does not implement UI. Reports must not call this
module; this module may reuse reporting helpers and shared completion
calculations.

Row safeguard: summary aggregation uses get_task_rows limit_page_length=5000
(same default as the reporting service). If exactly 5000 rows are returned,
counts may be truncated for very large result sets — documented for later
caching/pagination batches.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import frappe

from project_custom.nave_task_reporting import (
	_as_date,
	_as_str_list,
	_row_get,
	build_summary_from_rows,
	get_task_rows,
	normalize_filters,
)
from project_custom.nave_task_script_reports import (
	_avg,
	_completion_pct,
	_user_is_manager_level,
	classify_completion_result,
	completion_days,
	days_overdue,
	delay_days,
)
from project_custom.nave_task_utils import ACTIVE_STATUSES, is_terminal_status


ALLOWED_STATUSES = (
	"Open",
	"Working",
	"Pending",
	"Completed",
	"Closed",
	"Cancelled",
)

ALLOWED_PRIORITIES = ("Low", "Medium", "High", "Urgent")

DASHBOARD_FILTER_KEYS = frozenset(
	{
		"assigned_to",
		"department",
		"project",
		"priority",
		"status",
		"from_date",
		"to_date",
		"due_date_from",
		"due_date_to",
	}
)

SUPPORTED_LIST_TYPES = (
	"overdue",
	"due_today",
	"due_tomorrow",
	"high_priority",
	"recently_updated",
	"completed_today",
)

DEFAULT_LIST_LIMIT = 10
MAX_LIST_LIMIT = 50
SUMMARY_ROW_LIMIT = 5000

# Batch 8B widget surface (stricter than generic list API max).
DEFAULT_WIDGET_LIMIT = 10
MAX_WIDGET_LIMIT = 25

SUPPORTED_WIDGET_TYPES = (
	"due_today",
	"due_tomorrow",
	"overdue",
	"high_priority",
	"recently_updated",
)

KPI_CARD_KEYS = (
	"total",
	"active",
	"open",
	"working",
	"pending",
	"completed",
	"closed",
	"overdue",
	"due_today",
	"due_tomorrow",
	"high_priority",
	"completed_today",
)

KPI_CARD_LABELS = {
	"total": "Total",
	"active": "Active",
	"open": "Open",
	"working": "Working",
	"pending": "Pending",
	"completed": "Completed",
	"closed": "Closed",
	"overdue": "Overdue",
	"due_today": "Due Today",
	"due_tomorrow": "Due Tomorrow",
	"high_priority": "High Priority",
	"completed_today": "Completed Today",
}

WIDGET_ITEM_FIELDS = (
	"name",
	"title",
	"assigned_to",
	"status",
	"priority",
	"due_date",
	"project",
	"department",
	"modified",
	"overdue_days",
)

WIDGET_TYPES_WITH_OVERDUE_DAYS = frozenset(
	{"overdue", "due_today", "due_tomorrow", "high_priority"}
)

DASHBOARD_LIST_FIELDS = (
	"name",
	"subject",
	"assigned_to",
	"status",
	"priority",
	"due_date",
	"completed_on",
	"project",
	"department",
	"modified",
	"creation",
	"is_overdue",
)

SUMMARY_FIELDS = (
	"name",
	"subject",
	"assigned_to",
	"status",
	"priority",
	"due_date",
	"completed_on",
	"project",
	"department",
	"modified",
	"creation",
	"is_overdue",
)

PRIORITY_RANK = {"Urgent": 0, "High": 1, "Medium": 2, "Low": 3}

LIST_EXPOSED_FIELDS = (
	"name",
	"subject",
	"title",
	"assigned_to",
	"status",
	"priority",
	"due_date",
	"completed_on",
	"project",
	"department",
	"modified",
	"overdue_days",
)


def _throw_validation(message: str) -> None:
	exc = getattr(frappe, "ValidationError", None) or Exception
	frappe.throw(message, exc)


def _throw_permission(message: str) -> None:
	exc = getattr(frappe, "PermissionError", None) or Exception
	frappe.throw(message, exc)


def _parse_raw_filters(filters) -> dict:
	if filters is None or filters == "":
		return {}
	if isinstance(filters, str):
		parse_json = getattr(frappe, "parse_json", None)
		if callable(parse_json):
			filters = parse_json(filters) or {}
		else:
			import json

			filters = json.loads(filters) if filters.strip() else {}
	if not isinstance(filters, dict):
		_throw_validation("Dashboard filters must be a dictionary.")
	return dict(filters)


def _today(today=None) -> date:
	if today is None:
		from frappe.utils import getdate, nowdate

		return getdate(nowdate())
	parsed = _as_date(today)
	return parsed or date.today()


def _now_iso() -> str:
	try:
		from frappe.utils import now_datetime

		value = now_datetime()
		return str(value)
	except Exception:
		return datetime.utcnow().isoformat(sep=" ", timespec="seconds")


def clamp_list_limit(limit=None) -> int:
	"""Default 10; clamp to [1, MAX_LIST_LIMIT]; invalid → default."""
	if limit is None or limit == "":
		return DEFAULT_LIST_LIMIT
	try:
		value = int(limit)
	except (TypeError, ValueError):
		return DEFAULT_LIST_LIMIT
	if value < 1:
		return DEFAULT_LIST_LIMIT
	return min(value, MAX_LIST_LIMIT)


def normalize_dashboard_filters(raw=None) -> dict:
	"""
	Normalize and validate dashboard filters.

	Unknown keys are ignored. Invalid status/priority and inverted date ranges
	raise ValidationError. Does not grant access — get_task_rows enforces
	permissions server-side.
	"""
	raw = _parse_raw_filters(raw)
	# Keep only known keys before shared normalization.
	trimmed = {k: v for k, v in raw.items() if k in DASHBOARD_FILTER_KEYS and v not in (None, "")}

	statuses = _as_str_list(trimmed.get("status"))
	for status in statuses:
		if status not in ALLOWED_STATUSES:
			_throw_validation(f"Invalid status: {status}")

	priorities = _as_str_list(trimmed.get("priority"))
	for priority in priorities:
		if priority not in ALLOWED_PRIORITIES:
			_throw_validation(f"Invalid priority: {priority}")

	from_date = _as_date(trimmed.get("from_date"))
	to_date = _as_date(trimmed.get("to_date"))
	if from_date and to_date and from_date > to_date:
		_throw_validation("From Date cannot be after To Date.")

	due_from = _as_date(trimmed.get("due_date_from"))
	due_to = _as_date(trimmed.get("due_date_to"))
	if due_from and due_to and due_from > due_to:
		_throw_validation("Due From cannot be after Due To.")

	# Reuse reporting normalizer for stable key shapes.
	return normalize_filters(trimmed)


def _priority_rank(priority) -> int:
	return PRIORITY_RANK.get((priority or "").strip(), 99)


def _compact_task_row(row, *, today: date, include_overdue_days: bool = False) -> dict:
	subject = _row_get(row, "subject")
	status = _row_get(row, "status")
	due_date = _row_get(row, "due_date")
	item = {
		"name": _row_get(row, "name"),
		"subject": subject,
		"title": subject,
		"assigned_to": _row_get(row, "assigned_to"),
		"status": status,
		"priority": _row_get(row, "priority"),
		"due_date": due_date,
		"completed_on": _row_get(row, "completed_on"),
		"project": _row_get(row, "project"),
		"department": _row_get(row, "department"),
		"modified": _row_get(row, "modified"),
	}
	if include_overdue_days:
		item["overdue_days"] = days_overdue(due_date, status, today)
	else:
		item["overdue_days"] = None
	# Ensure only approved keys.
	return {key: item.get(key) for key in LIST_EXPOSED_FIELDS}


def build_dashboard_cards(rows, *, today=None) -> dict:
	"""KPI card values from one permission-filtered row set."""
	day = _today(today)
	base = build_summary_from_rows(rows, today=day)
	completed_today = 0
	for row in rows or []:
		status = (_row_get(row, "status") or "").strip()
		if status not in ("Completed", "Closed"):
			continue
		completed_on = _as_date(_row_get(row, "completed_on"))
		if completed_on == day:
			completed_today += 1

	return {
		"total": base["total"],
		"open": base["open"],
		"working": base["working"],
		"pending": base["pending"],
		"completed": base["completed"],
		"closed": base["closed"],
		"active": base["open"] + base["working"] + base["pending"],
		"overdue": base["overdue"],
		"due_today": base["due_today"],
		"due_tomorrow": base["due_tomorrow"],
		"high_priority": base["high_priority"],
		"completed_today": completed_today,
	}


def build_dashboard_completion(rows, *, today=None) -> dict:
	"""Completion metrics reusing report completion helpers."""
	_ = today  # reserved for future as-of snapshots
	completed_closed = 0
	on_time = late = 0
	completion_sum = completion_n = 0
	delay_sum = delay_n = 0
	total = len(rows or [])

	for row in rows or []:
		status = (_row_get(row, "status") or "").strip()
		if status not in ("Completed", "Closed"):
			continue
		completed_closed += 1
		completed_on = _row_get(row, "completed_on")
		due_date = _row_get(row, "due_date")
		result = classify_completion_result(completed_on, due_date)
		if result == "On Time":
			on_time += 1
		elif result == "Late":
			late += 1
		cd = completion_days(_row_get(row, "creation"), completed_on)
		if cd is not None:
			completion_sum += cd
			completion_n += 1
		dd = delay_days(completed_on, due_date)
		if dd is not None:
			delay_sum += dd
			delay_n += 1

	return {
		"completed_closed": completed_closed,
		"completion_percentage": _completion_pct(completed_closed, total),
		"on_time": on_time,
		"late": late,
		"average_completion_days": _avg(completion_sum, completion_n),
		"average_delay_days": _avg(delay_sum, delay_n),
	}


def get_dashboard_summary(filters=None, *, user=None, today=None) -> dict:
	"""Permission-aware dashboard KPI payload (one fetch + one aggregation)."""
	user = user or getattr(getattr(frappe, "session", None), "user", None)
	day = _today(today)
	normalized = normalize_dashboard_filters(filters)
	rows = get_task_rows(
		normalized,
		user=user,
		fields=SUMMARY_FIELDS,
		order_by="modified desc",
		limit_page_length=SUMMARY_ROW_LIMIT,
	)
	truncated = len(rows) >= SUMMARY_ROW_LIMIT
	return {
		"filters": normalized,
		"generated_at": _now_iso(),
		"cards": build_dashboard_cards(rows, today=day),
		"completion": build_dashboard_completion(rows, today=day),
		"meta": {
			"row_limit": SUMMARY_ROW_LIMIT,
			"row_count": len(rows),
			"possibly_truncated": truncated,
		},
	}


def _list_type_query(
	list_type: str,
	normalized: dict,
	*,
	today: date,
) -> tuple[dict, str]:
	"""Return (filters, order_by). List-type conditions applied at DB where practical."""
	filters = dict(normalized)
	tomorrow = today + timedelta(days=1)
	today_s = today.isoformat()
	tomorrow_s = tomorrow.isoformat()
	yesterday_s = (today - timedelta(days=1)).isoformat()

	if list_type == "overdue":
		filters["status"] = list(ACTIVE_STATUSES)
		filters["due_date_to"] = yesterday_s
		order_by = "due_date asc, modified desc"
	elif list_type == "due_today":
		filters["status"] = list(ACTIVE_STATUSES)
		filters["due_date_from"] = today_s
		filters["due_date_to"] = today_s
		order_by = "creation asc"
	elif list_type == "due_tomorrow":
		filters["status"] = list(ACTIVE_STATUSES)
		filters["due_date_from"] = tomorrow_s
		filters["due_date_to"] = tomorrow_s
		order_by = "creation asc"
	elif list_type == "high_priority":
		filters["priority"] = "High"
		order_by = "due_date asc, modified desc"
	elif list_type == "recently_updated":
		order_by = "modified desc"
	elif list_type == "completed_today":
		filters["status"] = ["Completed", "Closed"]
		filters["completed_from"] = today_s
		filters["completed_to"] = today_s
		order_by = "completed_on desc"
	else:
		_throw_validation(f"Unsupported list type: {list_type}")

	return filters, order_by


def _fetch_list_rows(filters: dict, *, user: str, order_by: str, limit: int) -> list:
	return get_task_rows(
		filters,
		user=user,
		fields=DASHBOARD_LIST_FIELDS,
		order_by=order_by,
		limit_page_length=limit,
	) or []


def _sort_list_rows(rows: list, list_type: str, *, today: date) -> list:
	if list_type == "overdue":
		return sorted(
			rows,
			key=lambda r: (
				_as_date(_row_get(r, "due_date")) or date.max,
				_priority_rank(_row_get(r, "priority")),
				str(_row_get(r, "name") or ""),
			),
		)
	if list_type in ("due_today", "due_tomorrow"):
		return sorted(
			rows,
			key=lambda r: (
				_priority_rank(_row_get(r, "priority")),
				str(_row_get(r, "creation") or ""),
				str(_row_get(r, "name") or ""),
			),
		)
	if list_type == "high_priority":

		def high_key(r):
			status = _row_get(r, "status")
			due = _as_date(_row_get(r, "due_date"))
			is_od = (not is_terminal_status(status)) and due is not None and due < today
			due_ord = due.toordinal() if due else 10**9
			# Latest modified first among equals: invert string via reverse sort key
			modified = str(_row_get(r, "modified") or "")
			return (0 if is_od else 1, due_ord, tuple(-ord(c) for c in modified))

		return sorted(rows, key=high_key)
	if list_type == "recently_updated":
		return sorted(
			rows,
			key=lambda r: str(_row_get(r, "modified") or ""),
			reverse=True,
		)
	if list_type == "completed_today":
		return sorted(
			rows,
			key=lambda r: str(_row_get(r, "completed_on") or ""),
			reverse=True,
		)
	return rows


def get_dashboard_list(
	list_type,
	filters=None,
	limit=None,
	*,
	user=None,
	today=None,
) -> dict:
	"""Permission-aware compact task list for dashboard widgets."""
	user = user or getattr(getattr(frappe, "session", None), "user", None)
	day = _today(today)
	list_type = (list_type or "").strip()
	if list_type not in SUPPORTED_LIST_TYPES:
		_throw_validation(f"Unsupported list type: {list_type}")

	capped = clamp_list_limit(limit)
	normalized = normalize_dashboard_filters(filters)
	query_filters, order_by = _list_type_query(list_type, normalized, today=day)
	rows = _fetch_list_rows(
		query_filters, user=user, order_by=order_by, limit=capped
	)
	rows = _sort_list_rows(rows, list_type, today=day)[:capped]
	include_od = list_type in ("overdue", "high_priority", "due_today", "due_tomorrow")
	data = [
		_compact_task_row(row, today=day, include_overdue_days=include_od)
		for row in rows
	]
	return {
		"list_type": list_type,
		"filters": normalized,
		"limit": capped,
		"generated_at": _now_iso(),
		"data": data,
	}


def clamp_widget_limit(limit=None) -> int:
	"""Default 10; hard max 25; invalid → default."""
	if limit is None or limit == "":
		return DEFAULT_WIDGET_LIMIT
	try:
		value = int(limit)
	except (TypeError, ValueError):
		return DEFAULT_WIDGET_LIMIT
	if value < 1:
		return DEFAULT_WIDGET_LIMIT
	return min(value, MAX_WIDGET_LIMIT)


def _shape_widget_item(row: dict, *, widget_type: str) -> dict:
	"""Trim list rows to widget fields only (no descriptions/attachments)."""
	item = {
		"name": row.get("name"),
		"title": row.get("title") or row.get("subject"),
		"assigned_to": row.get("assigned_to"),
		"status": row.get("status"),
		"priority": row.get("priority"),
		"due_date": row.get("due_date"),
		"project": row.get("project"),
		"department": row.get("department"),
		"modified": row.get("modified"),
	}
	if widget_type in WIDGET_TYPES_WITH_OVERDUE_DAYS:
		item["overdue_days"] = row.get("overdue_days")
	return item


def get_dashboard_kpi_cards(filters=None, *, user=None, today=None) -> dict:
	"""
	Widget-ready KPI cards.

	Reuses get_dashboard_summary — no separate aggregation.
	"""
	summary = get_dashboard_summary(filters, user=user, today=today)
	raw_cards = summary.get("cards") or {}
	cards = {key: int(raw_cards.get(key) or 0) for key in KPI_CARD_KEYS}
	card_list = [
		{"key": key, "label": KPI_CARD_LABELS[key], "value": cards[key]}
		for key in KPI_CARD_KEYS
	]
	return {
		"filters": summary.get("filters") or {},
		"generated_at": summary.get("generated_at") or _now_iso(),
		"cards": cards,
		"card_list": card_list,
		"meta": summary.get("meta") or {},
	}


def get_dashboard_widget(
	widget_type,
	filters=None,
	limit=None,
	*,
	user=None,
	today=None,
) -> dict:
	"""
	Widget-ready task list for one dashboard panel.

	Reuses get_dashboard_list with widget limit cap (max 25).
	"""
	widget_type = (widget_type or "").strip()
	if widget_type not in SUPPORTED_WIDGET_TYPES:
		_throw_validation(f"Unsupported widget type: {widget_type}")

	capped = clamp_widget_limit(limit)
	payload = get_dashboard_list(
		widget_type,
		filters=filters,
		limit=capped,
		user=user,
		today=today,
	)
	items = [
		_shape_widget_item(row, widget_type=widget_type)
		for row in (payload.get("data") or [])
	]
	return {
		"widget": widget_type,
		"filters": payload.get("filters") or {},
		"limit": capped,
		"generated_at": payload.get("generated_at") or _now_iso(),
		"items": items,
		"count": len(items),
	}



def get_dashboard_metadata(*, user=None, today=None) -> dict:
	"""UI metadata only — no hidden users, departments, or permission SQL."""
	user = user or getattr(getattr(frappe, "session", None), "user", None)
	day = _today(today)
	manager_level = False
	if user and user != "Guest":
		try:
			manager_level = _user_is_manager_level(user)
		except Exception:
			manager_level = False

	return {
		"generated_at": _now_iso(),
		"generated_date": day.isoformat(),
		"current_user": user,
		"manager_level_access": bool(manager_level),
		"statuses": list(ALLOWED_STATUSES),
		"priorities": list(ALLOWED_PRIORITIES),
		"list_types": list(SUPPORTED_LIST_TYPES),
		"widget_types": list(SUPPORTED_WIDGET_TYPES),
		"default_list_limit": DEFAULT_LIST_LIMIT,
		"max_list_limit": MAX_LIST_LIMIT,
		"default_widget_limit": DEFAULT_WIDGET_LIMIT,
		"max_widget_limit": MAX_WIDGET_LIMIT,
		"summary_row_limit": SUMMARY_ROW_LIMIT,
		"kpi_card_keys": list(KPI_CARD_KEYS),
		"default_filters": {
			"assigned_to": None,
			"department": None,
			"project": None,
			"priority": None,
			"status": None,
			"from_date": None,
			"to_date": None,
			"due_date_from": None,
			"due_date_to": None,
		},
		"notes": {
			"permissions": "Server-side NAVE Task permissions are authoritative.",
			"high_priority": "High priority counts and lists use priority=High only.",
			"summary_row_limit": (
				f"Summary aggregates at most {SUMMARY_ROW_LIMIT} visible tasks "
				"per request (reporting service safeguard)."
			),
			"widgets": (
				f"Widget lists default to {DEFAULT_WIDGET_LIMIT} rows "
				f"(hard max {MAX_WIDGET_LIMIT})."
			),
		},
	}
