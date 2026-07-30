"""NAVE Task due / overdue reminders (Batch 5).

Runs once daily via the existing Frappe scheduler hook
`project_custom.api.nave_task.run_daily_nave_task_jobs`. Exact wall-clock time
depends on the site's Frappe scheduler configuration — not a fixed 9:00 AM.

Reminder types:
- due_tomorrow: due_date == tomorrow → assignee
- due_today: due_date == today → assignee
- overdue: due_date < today, on odd overdue ages (1, 3, 5, ...) → assignee

Idempotency (no new DocType):
1. In-process set on frappe.local for the current run
2. frappe.cache key: nave_task_reminder|{task}|{user}|{type}|{date} (TTL ~36h)
3. Durable: existing Notification Log for same user + NAVE Task + exact subject
   with creation on the reminder date

Limitations:
- Cache alone can be lost on Redis flush; Notification Log covers that after a
  successful in-app create.
- If Notification Log insert fails after the cache mark, the same day will not
  retry (missed reminder until next eligible day for overdue).
- Subject string distinguishes reminder types for the same task/day.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import frappe

from project_custom.nave_task_notifications import (
	_escape_html,
	_log_failure,
	_task_title,
	send_task_reminder_to_user,
)


REMINDER_DUE_TOMORROW = "due_tomorrow"
REMINDER_DUE_TODAY = "due_today"
REMINDER_OVERDUE = "overdue"

ACTIVE_REMINDER_STATUSES = ("Open", "Working", "Pending")

SUBJECT_TEMPLATES = {
	REMINDER_DUE_TOMORROW: "Task Due Tomorrow: {title}",
	REMINDER_DUE_TODAY: "Task Due Today: {title}",
	REMINDER_OVERDUE: "Task Overdue: {title}",
}

ACTION_LABELS = {
	REMINDER_DUE_TOMORROW: "Due tomorrow reminder",
	REMINDER_DUE_TODAY: "Due today reminder",
	REMINDER_OVERDUE: "Overdue reminder",
}

_REMINDER_CACHE_TTL_SECONDS = 36 * 60 * 60


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


def _today(today=None) -> date:
	if today is None:
		from frappe.utils import getdate, nowdate

		return getdate(nowdate())
	parsed = _as_date(today)
	if parsed is None:
		raise ValueError(f"Invalid today value: {today!r}")
	return parsed


def overdue_age_days(due_date, today) -> int:
	"""Whole days past due. <= 0 means not overdue."""
	due = _as_date(due_date)
	day = _as_date(today) if not isinstance(today, date) else today
	if due is None or day is None:
		return 0
	return (day - due).days


def should_send_overdue_reminder(days_overdue: int) -> bool:
	"""
	Alternate-day overdue reminders by overdue age:
	1, 3, 5, ... send; 2, 4, 6, ... skip.
	"""
	return days_overdue >= 1 and days_overdue % 2 == 1


def classify_reminder(due_date, today) -> str | None:
	"""Return reminder type for an active task due_date relative to today."""
	due = _as_date(due_date)
	day = _as_date(today) if not isinstance(today, date) else today
	if due is None or day is None:
		return None
	delta = (due - day).days
	if delta == 1:
		return REMINDER_DUE_TOMORROW
	if delta == 0:
		return REMINDER_DUE_TODAY
	if delta < 0:
		if should_send_overdue_reminder(-delta):
			return REMINDER_OVERDUE
		return None
	return None


def reminder_subject(reminder_type: str, task) -> str:
	return SUBJECT_TEMPLATES[reminder_type].format(title=_task_title(task))


def _timing_label(reminder_type: str, due_date, today) -> str:
	age = overdue_age_days(due_date, today)
	if reminder_type == REMINDER_DUE_TOMORROW:
		return "1 day remaining"
	if reminder_type == REMINDER_DUE_TODAY:
		return "Due today (0 days remaining)"
	return f"{age} day{'s' if age != 1 else ''} overdue"


def _idempotency_key(task_name: str, recipient: str, reminder_type: str, on_date: date) -> str:
	return f"nave_task_reminder|{task_name}|{recipient}|{reminder_type}|{on_date.isoformat()}"


def _local_sent_store():
	local = getattr(frappe, "local", None)
	if local is None:
		local = type("_Local", (), {})()
		frappe.local = local
	store = getattr(local, "nave_task_reminders_sent", None)
	if store is None:
		store = set()
		local.nave_task_reminders_sent = store
	return store


def _cache_get(key: str):
	try:
		cache = frappe.cache()
		if hasattr(cache, "get_value"):
			return cache.get_value(key)
		return cache.get(key)
	except Exception:
		return None


def _cache_set(key: str, value=1):
	try:
		cache = frappe.cache()
		if hasattr(cache, "set_value"):
			cache.set_value(key, value, expires_in_sec=_REMINDER_CACHE_TTL_SECONDS)
		else:
			cache.set(key, value, timeout=_REMINDER_CACHE_TTL_SECONDS)
	except Exception:
		pass


def notification_log_exists_today(
	*,
	task_name: str,
	recipient: str,
	subject: str,
	on_date: date,
) -> bool:
	"""Durable same-day check via Notification Log (no custom DocType)."""
	start = f"{on_date.isoformat()} 00:00:00"
	end = f"{(on_date + timedelta(days=1)).isoformat()} 00:00:00"
	try:
		rows = frappe.get_all(
			"Notification Log",
			filters=[
				["for_user", "=", recipient],
				["document_type", "=", "NAVE Task"],
				["document_name", "=", task_name],
				["subject", "=", subject],
				["creation", ">=", start],
				["creation", "<", end],
			],
			limit_page_length=1,
			pluck="name",
		)
		return bool(rows)
	except Exception:
		return False


def reminder_already_sent(
	*,
	task_name: str,
	recipient: str,
	reminder_type: str,
	on_date: date,
	subject: str,
) -> bool:
	key = _idempotency_key(task_name, recipient, reminder_type, on_date)
	if key in _local_sent_store():
		return True
	if _cache_get(key):
		return True
	if notification_log_exists_today(
		task_name=task_name,
		recipient=recipient,
		subject=subject,
		on_date=on_date,
	):
		return True
	return False


def mark_reminder_sent(
	*,
	task_name: str,
	recipient: str,
	reminder_type: str,
	on_date: date,
) -> None:
	key = _idempotency_key(task_name, recipient, reminder_type, on_date)
	_local_sent_store().add(key)
	_cache_set(key, 1)


def _fetch_candidate_tasks(today: date):
	"""Active tasks with assignee whose due_date is tomorrow or earlier."""
	tomorrow = today + timedelta(days=1)
	return frappe.get_all(
		"NAVE Task",
		filters=[
			["status", "in", list(ACTIVE_REMINDER_STATUSES)],
			["due_date", "<=", tomorrow.isoformat()],
			["due_date", "is", "set"],
			["assigned_to", "is", "set"],
			["assigned_to", "!=", ""],
		],
		fields=[
			"name",
			"subject",
			"status",
			"assigned_to",
			"assigned_by",
			"owner",
			"priority",
			"due_date",
			"project",
			"department",
		],
		limit_page_length=50000,
	)


def _process_one_task(task, today: date, stats: dict) -> None:
	reminder_type = classify_reminder(task.due_date, today)
	if not reminder_type:
		stats["skipped_not_due"] += 1
		return

	recipient = getattr(task, "assigned_to", None)
	if not recipient:
		stats["skipped_no_assignee"] += 1
		return

	subject = reminder_subject(reminder_type, task)
	if reminder_already_sent(
		task_name=task.name,
		recipient=recipient,
		reminder_type=reminder_type,
		on_date=today,
		subject=subject,
	):
		stats["skipped_duplicate"] += 1
		return

	# Reserve the idempotency key before send to block concurrent/retry duplicates.
	mark_reminder_sent(
		task_name=task.name,
		recipient=recipient,
		reminder_type=reminder_type,
		on_date=today,
	)

	timing = _timing_label(reminder_type, task.due_date, today)
	intro = (
		f"<p>{_escape_html(ACTION_LABELS[reminder_type])}: "
		f"<b>{_escape_html(_task_title(task))}</b> "
		f"({_escape_html(task.name)}). {_escape_html(timing)}.</p>"
	)
	sent = send_task_reminder_to_user(
		task,
		user=recipient,
		subject=subject,
		action=ACTION_LABELS[reminder_type],
		intro=intro,
		extra_rows=[("Timing", timing)],
		actor="Administrator",
	)
	if sent:
		stats["sent"] += 1
		stats[f"sent_{reminder_type}"] += 1
	else:
		stats["skipped_recipient"] += 1


def send_nave_task_due_reminders(today=None) -> dict:
	"""
	Daily entry point. Callable directly from tests and the scheduler job.
	Failures for one task do not stop processing of remaining tasks.
	Does not modify task documents.
	"""
	day = _today(today)
	stats = {
		"ok": True,
		"today": day.isoformat(),
		"checked": 0,
		"sent": 0,
		"sent_due_tomorrow": 0,
		"sent_due_today": 0,
		"sent_overdue": 0,
		"skipped_not_due": 0,
		"skipped_no_assignee": 0,
		"skipped_duplicate": 0,
		"skipped_recipient": 0,
		"errors": 0,
	}

	try:
		tasks = _fetch_candidate_tasks(day)
	except Exception:
		_log_failure("NAVE Task reminder fetch failed", {"name": None}, "fetch")
		stats["ok"] = False
		stats["errors"] += 1
		return stats

	stats["checked"] = len(tasks)
	for task in tasks:
		try:
			_process_one_task(task, day, stats)
		except Exception:
			stats["errors"] += 1
			_log_failure(
				"NAVE Task reminder processing failed",
				task,
				classify_reminder(getattr(task, "due_date", None), day) or "unknown",
			)
			continue

	return stats
