"""NAVE Task overdue escalation (Batch 6).

Runs after assignee due/overdue reminders in the existing daily job
`project_custom.api.nave_task.run_daily_nave_task_jobs`.

Milestones (exact overdue age only):
- 3 days → eligible same-department NAVE Task Managers
- 7 days → eligible same-department NAVE Task Directors

Assignee keeps Batch 5 overdue reminders. Escalation is not sent to the
assignee unless they independently qualify as manager/director.

Idempotency (no new DocType):
1. frappe.local set for the current run
2. frappe.cache key including task, recipient, escalation level, milestone
3. Durable Notification Log match on user + task + exact escalation subject

Manager (3) and director (7) keys do not conflict.

Limitations:
- Cache may be lost on Redis flush; Notification Log covers successful sends.
- If cache is marked but Notification Log insert fails, same-day retry is
  suppressed (missed escalation for that recipient).
- System Managers / Administrators are not mass-notified (not department-mapped
  operational recipients in existing completion notify logic).
"""

from __future__ import annotations

from datetime import date

import frappe

from project_custom.nave_task_notifications import (
	DIRECTOR_ROLE,
	MANAGER_ROLE,
	_escape_html,
	_log_failure,
	_task_creator,
	_task_title,
	get_eligible_department_role_users,
	send_task_reminder_to_user,
)
from project_custom.nave_task_reminders import (
	ACTIVE_REMINDER_STATUSES,
	_cache_get,
	_cache_set,
	_today,
	notification_log_exists_today,
	overdue_age_days,
)


ESCALATION_MANAGER_3 = "manager_3"
ESCALATION_DIRECTOR_7 = "director_7"

MANAGER_OVERDUE_DAYS = 3
DIRECTOR_OVERDUE_DAYS = 7

SUBJECT_TEMPLATES = {
	ESCALATION_MANAGER_3: "Task Escalation — 3 Days Overdue: {title}",
	ESCALATION_DIRECTOR_7: "Task Escalation — 7 Days Overdue: {title}",
}

ACTION_LABELS = {
	ESCALATION_MANAGER_3: "Manager escalation (3 days overdue)",
	ESCALATION_DIRECTOR_7: "Director escalation (7 days overdue)",
}

ACTION_REQUESTS = {
	ESCALATION_MANAGER_3: (
		"Please review the delay and coordinate with the assignee for completion."
	),
	ESCALATION_DIRECTOR_7: (
		"This task remains significantly overdue. Please review and take corrective action."
	),
}

_ESCALATION_CACHE_TTL_SECONDS = 90 * 24 * 60 * 60


def classify_escalation(due_date, today) -> str | None:
	"""Return escalation level only at exact 3- or 7-day overdue milestones."""
	age = overdue_age_days(due_date, today)
	if age == MANAGER_OVERDUE_DAYS:
		return ESCALATION_MANAGER_3
	if age == DIRECTOR_OVERDUE_DAYS:
		return ESCALATION_DIRECTOR_7
	return None


def escalation_subject(level: str, task) -> str:
	return SUBJECT_TEMPLATES[level].format(title=_task_title(task))


def resolve_escalation_recipients(task, level: str) -> list[str]:
	"""
	Department-scoped managers or directors with task access.
	Assignee is included only if they independently hold the role + dept match.
	"""
	if level == ESCALATION_MANAGER_3:
		return get_eligible_department_role_users(task, (MANAGER_ROLE,))
	if level == ESCALATION_DIRECTOR_7:
		return get_eligible_department_role_users(task, (DIRECTOR_ROLE,))
	return []


def _idempotency_key(task_name: str, recipient: str, level: str, milestone: int) -> str:
	return f"nave_task_escalation|{task_name}|{recipient}|{level}|milestone:{milestone}"


def _local_sent_store():
	local = getattr(frappe, "local", None)
	if local is None:
		local = type("_Local", (), {})()
		frappe.local = local
	store = getattr(local, "nave_task_escalations_sent", None)
	if store is None:
		store = set()
		local.nave_task_escalations_sent = store
	return store


def _milestone_for_level(level: str) -> int:
	if level == ESCALATION_MANAGER_3:
		return MANAGER_OVERDUE_DAYS
	return DIRECTOR_OVERDUE_DAYS


def escalation_already_sent(
	*,
	task_name: str,
	recipient: str,
	level: str,
	subject: str,
	on_date: date,
) -> bool:
	milestone = _milestone_for_level(level)
	key = _idempotency_key(task_name, recipient, level, milestone)
	if key in _local_sent_store():
		return True
	if _cache_get(key):
		return True
	# Same-day durable check (scheduler reruns).
	if notification_log_exists_today(
		task_name=task_name,
		recipient=recipient,
		subject=subject,
		on_date=on_date,
	):
		return True
	# Any prior Notification Log with this exact escalation subject for the task.
	try:
		rows = frappe.get_all(
			"Notification Log",
			filters=[
				["for_user", "=", recipient],
				["document_type", "=", "NAVE Task"],
				["document_name", "=", task_name],
				["subject", "=", subject],
			],
			limit_page_length=1,
			pluck="name",
		)
		if rows:
			return True
	except Exception:
		pass
	return False


def mark_escalation_sent(
	*,
	task_name: str,
	recipient: str,
	level: str,
) -> None:
	milestone = _milestone_for_level(level)
	key = _idempotency_key(task_name, recipient, level, milestone)
	_local_sent_store().add(key)
	try:
		cache = frappe.cache()
		if hasattr(cache, "set_value"):
			cache.set_value(key, 1, expires_in_sec=_ESCALATION_CACHE_TTL_SECONDS)
		else:
			cache.set(key, 1, timeout=_ESCALATION_CACHE_TTL_SECONDS)
	except Exception:
		_cache_set(key, 1)


def _fetch_overdue_candidates(today: date):
	"""Active overdue tasks with assignee and due_date (due_date < today)."""
	return frappe.get_all(
		"NAVE Task",
		filters=[
			["status", "in", list(ACTIVE_REMINDER_STATUSES)],
			["due_date", "<", today.isoformat()],
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
	level = classify_escalation(task.due_date, today)
	if not level:
		stats["skipped_not_milestone"] += 1
		return

	if not getattr(task, "assigned_to", None):
		stats["skipped_no_assignee"] += 1
		return

	if not getattr(task, "due_date", None):
		stats["skipped_no_due"] += 1
		return

	recipients = resolve_escalation_recipients(task, level)
	if not recipients:
		stats["skipped_no_recipients"] += 1
		return

	subject = escalation_subject(level, task)
	age = overdue_age_days(task.due_date, today)
	creator = _task_creator(task) or "—"
	action_request = ACTION_REQUESTS[level]
	intro = (
		f"<p><b>{_escape_html(ACTION_LABELS[level])}</b></p>"
		f"<p>{_escape_html(action_request)}</p>"
		f"<p>Task <b>{_escape_html(_task_title(task))}</b> "
		f"({_escape_html(task.name)}) is {_escape_html(str(age))} days overdue.</p>"
	)
	extra_rows = [
		("Escalation level", ACTION_LABELS[level]),
		("Days overdue", str(age)),
		("Task creator", creator),
		("Action required", action_request),
	]

	for recipient in recipients:
		if escalation_already_sent(
			task_name=task.name,
			recipient=recipient,
			level=level,
			subject=subject,
			on_date=today,
		):
			stats["skipped_duplicate"] += 1
			continue

		mark_escalation_sent(
			task_name=task.name,
			recipient=recipient,
			level=level,
		)

		sent = send_task_reminder_to_user(
			task,
			user=recipient,
			subject=subject,
			action=ACTION_LABELS[level],
			intro=intro,
			extra_rows=extra_rows,
			actor="Administrator",
		)
		if sent:
			stats["sent"] += 1
			stats[f"sent_{level}"] += 1
		else:
			stats["skipped_recipient"] += 1


def send_nave_task_escalations(today=None) -> dict:
	"""
	Daily escalation entry point (callable from tests and the scheduler job).
	Does not modify task documents. Continues after per-task failures.
	"""
	day = _today(today)
	stats = {
		"ok": True,
		"today": day.isoformat(),
		"checked": 0,
		"sent": 0,
		"sent_manager_3": 0,
		"sent_director_7": 0,
		"skipped_not_milestone": 0,
		"skipped_no_assignee": 0,
		"skipped_no_due": 0,
		"skipped_no_recipients": 0,
		"skipped_duplicate": 0,
		"skipped_recipient": 0,
		"errors": 0,
	}

	try:
		tasks = _fetch_overdue_candidates(day)
	except Exception:
		_log_failure("NAVE Task escalation fetch failed", {"name": None}, "fetch")
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
				"NAVE Task escalation processing failed",
				task,
				classify_escalation(getattr(task, "due_date", None), day) or "unknown",
			)
			continue

	return stats
