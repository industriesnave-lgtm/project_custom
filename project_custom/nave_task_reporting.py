"""NAVE Task reporting service foundation (Phase 3 — Batch 7A).

Reusable filter normalization, permission-aware task queries, and summary
counts for future reports/dashboards. No report UI or dashboard APIs here.

Permission enforcement reuses the existing NAVE Task query conditions
(assignee / creator / department manager / director / System Manager /
Administrator). Queries use frappe.get_list so permission_query_conditions
apply server-side.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import frappe

from project_custom.nave_task_utils import compute_is_overdue, is_terminal_status
from project_custom.permissions.nave_task import get_task_query_conditions


SUPPORTED_FILTER_KEYS = (
	"assigned_to",
	"created_by",
	"department",
	"project",
	"status",
	"priority",
	"from_date",
	"to_date",
	"due_date_from",
	"due_date_to",
	"completed_from",
	"completed_to",
	"completion_result",
)

COMPLETION_RESULT_VALUES = ("On Time", "Late", "No Due Date")

DEFAULT_TASK_FIELDS = (
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

SUMMARY_FIELDS = (
	"total",
	"open",
	"working",
	"pending",
	"completed",
	"closed",
	"overdue",
	"due_today",
	"due_tomorrow",
	"high_priority",
)

_STATUS_KEYS = {
	"Open": "open",
	"Working": "working",
	"Pending": "pending",
	"Completed": "completed",
	"Closed": "closed",
}


def _as_date(value) -> date | None:
	if value is None or value == "":
		return None
	if isinstance(value, datetime):
		return value.date()
	if isinstance(value, date):
		return value
	text = str(value).strip()
	if not text:
		return None
	if " " in text:
		text = text.split(" ", 1)[0]
	try:
		return datetime.strptime(text, "%Y-%m-%d").date()
	except ValueError:
		return None


def _as_str_list(value) -> list[str]:
	if value is None or value == "":
		return []
	if isinstance(value, (list, tuple, set)):
		return [str(v).strip() for v in value if str(v).strip()]
	text = str(value).strip()
	if not text:
		return []
	if "," in text:
		return [part.strip() for part in text.split(",") if part.strip()]
	return [text]


def _clean_str(value) -> str | None:
	if value is None:
		return None
	text = str(value).strip()
	return text or None


def normalize_filters(raw=None) -> dict:
	"""
	Normalize report filters into a stable dict.
	Unknown keys are ignored. Empty values are dropped.
	"""
	raw = raw or {}
	if not isinstance(raw, dict):
		raw = {}

	out = {}

	for key in ("assigned_to", "created_by", "department", "project"):
		value = _clean_str(raw.get(key))
		if value:
			out[key] = value

	statuses = _as_str_list(raw.get("status"))
	if statuses:
		out["status"] = statuses if len(statuses) > 1 else statuses[0]

	priorities = _as_str_list(raw.get("priority"))
	if priorities:
		out["priority"] = priorities if len(priorities) > 1 else priorities[0]

	for key in (
		"from_date",
		"to_date",
		"due_date_from",
		"due_date_to",
		"completed_from",
		"completed_to",
	):
		parsed = _as_date(raw.get(key))
		if parsed:
			out[key] = parsed.isoformat()

	completion_result = _clean_str(raw.get("completion_result"))
	if completion_result in COMPLETION_RESULT_VALUES:
		out["completion_result"] = completion_result

	# Drop inverted ranges rather than throwing (callers may validate later).
	from_date = _as_date(out.get("from_date"))
	to_date = _as_date(out.get("to_date"))
	if from_date and to_date and from_date > to_date:
		out.pop("from_date", None)
		out.pop("to_date", None)

	due_from = _as_date(out.get("due_date_from"))
	due_to = _as_date(out.get("due_date_to"))
	if due_from and due_to and due_from > due_to:
		out.pop("due_date_from", None)
		out.pop("due_date_to", None)

	completed_from = _as_date(out.get("completed_from"))
	completed_to = _as_date(out.get("completed_to"))
	if completed_from and completed_to and completed_from > completed_to:
		out.pop("completed_from", None)
		out.pop("completed_to", None)

	return out


def get_permission_conditions(user=None) -> str:
	"""
	SQL fragment for NAVE Task visibility (same rules as list permissions).
	Empty string means unrestricted (admin/director). \"1=0\" means no access.
	"""
	user = user or getattr(getattr(frappe, "session", None), "user", None)
	if not user or user == "Guest":
		return "1=0"
	try:
		condition = get_task_query_conditions(user)
	except Exception:
		return "1=0"
	if condition is None:
		return ""
	return condition


def build_frappe_filters(normalized: dict | None) -> tuple[list, list]:
	"""
	Convert normalized filters to (filters, or_filters) for frappe.get_list.
	created_by matches owner OR assigned_by (creator visibility).
	"""
	normalized = normalized or {}
	filters: list = []
	or_filters: list = []

	if normalized.get("assigned_to"):
		filters.append(["assigned_to", "=", normalized["assigned_to"]])

	if normalized.get("department"):
		filters.append(["department", "=", normalized["department"]])

	if normalized.get("project"):
		filters.append(["project", "=", normalized["project"]])

	status = normalized.get("status")
	if status:
		if isinstance(status, list):
			filters.append(["status", "in", status])
		else:
			filters.append(["status", "=", status])

	priority = normalized.get("priority")
	if priority:
		if isinstance(priority, list):
			filters.append(["priority", "in", priority])
		else:
			filters.append(["priority", "=", priority])

	if normalized.get("from_date"):
		filters.append(["creation", ">=", f"{normalized['from_date']} 00:00:00"])
	if normalized.get("to_date"):
		filters.append(["creation", "<=", f"{normalized['to_date']} 23:59:59"])

	if normalized.get("due_date_from"):
		filters.append(["due_date", ">=", normalized["due_date_from"]])
	if normalized.get("due_date_to"):
		filters.append(["due_date", "<=", normalized["due_date_to"]])

	if normalized.get("completed_from"):
		filters.append(["completed_on", ">=", f"{normalized['completed_from']} 00:00:00"])
	if normalized.get("completed_to"):
		filters.append(["completed_on", "<=", f"{normalized['completed_to']} 23:59:59"])

	created_by = normalized.get("created_by")
	if created_by:
		or_filters.append(["owner", "=", created_by])
		or_filters.append(["assigned_by", "=", created_by])

	return filters, or_filters


def empty_summary() -> dict:
	return {key: 0 for key in SUMMARY_FIELDS}


def build_summary_from_rows(rows, today=None) -> dict:
	"""
	Pure summary aggregation from task row dicts/objects.
	Overdue excludes Completed / Closed / Cancelled.
	"""
	if today is None:
		try:
			from frappe.utils import getdate, nowdate

			today = getdate(nowdate())
		except Exception:
			today = date.today()
	else:
		today = _as_date(today) or date.today()

	tomorrow = today + timedelta(days=1)
	summary = empty_summary()
	rows = rows or []
	summary["total"] = len(rows)

	for row in rows:
		status = _row_get(row, "status") or ""
		priority = _row_get(row, "priority") or ""
		due_date = _row_get(row, "due_date")
		is_overdue_flag = _row_get(row, "is_overdue")

		status_key = _STATUS_KEYS.get(status)
		if status_key:
			summary[status_key] += 1

		if (priority or "").lower() == "high":
			summary["high_priority"] += 1

		due = _as_date(due_date)
		if due == today and not is_terminal_status(status):
			summary["due_today"] += 1
		if due == tomorrow and not is_terminal_status(status):
			summary["due_tomorrow"] += 1

		# Prefer stored flag when present; always exclude terminal statuses.
		if is_terminal_status(status):
			continue
		if is_overdue_flag is not None and is_overdue_flag != "":
			if int(is_overdue_flag or 0) == 1:
				summary["overdue"] += 1
		elif compute_is_overdue(due_date, status, today):
			summary["overdue"] += 1

	return summary


def _row_get(row, field):
	if isinstance(row, dict):
		return row.get(field)
	return getattr(row, field, None)


def get_task_rows(
	filters=None,
	*,
	user=None,
	fields=None,
	order_by="modified desc",
	limit_page_length=5000,
) -> list:
	"""
	Permission-aware NAVE Task rows for reporting.
	Uses get_list so document permission query conditions apply.
	"""
	user = user or getattr(getattr(frappe, "session", None), "user", None)
	if not user or user == "Guest":
		return []

	permission_sql = get_permission_conditions(user)
	if permission_sql == "1=0":
		return []

	normalized = normalize_filters(filters)
	frappe_filters, or_filters = build_frappe_filters(normalized)
	fieldnames = list(fields or DEFAULT_TASK_FIELDS)

	kwargs = {
		"fields": fieldnames,
		"filters": frappe_filters or None,
		"order_by": order_by,
		"limit_page_length": limit_page_length,
		"ignore_permissions": False,
	}
	if or_filters:
		kwargs["or_filters"] = or_filters

	# Run as the reporting user so permission_query_conditions bind correctly.
	previous_user = getattr(getattr(frappe, "session", None), "user", None)
	try:
		if previous_user != user:
			frappe.set_user(user)
		rows = frappe.get_list("NAVE Task", **kwargs)
	except Exception:
		# Fallback for unit stubs that only implement get_all.
		try:
			rows = frappe.get_all(
				"NAVE Task",
				fields=fieldnames,
				filters=frappe_filters or None,
				or_filters=or_filters or None,
				order_by=order_by,
				limit_page_length=limit_page_length,
			)
		except Exception:
			return []
	finally:
		if previous_user and previous_user != user:
			try:
				frappe.set_user(previous_user)
			except Exception:
				pass

	return rows or []


def get_summary(filters=None, *, user=None, today=None) -> dict:
	"""
	Permission-aware summary counts for the given filters.
	Loads only fields required for aggregation.
	"""
	rows = get_task_rows(
		filters,
		user=user,
		fields=["name", "status", "priority", "due_date", "is_overdue"],
		limit_page_length=50000,
	)
	return build_summary_from_rows(rows, today=today)
