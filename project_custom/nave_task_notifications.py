"""Centralized NAVE Task notifications (Batch 4 + Batch 5 reminders).

Events covered: assignment, reassignment, completion, reopen, close.
Reminders (Batch 5): due tomorrow, due today, overdue — see nave_task_reminders.py.

In-app: Frappe Notification Log.
Email: queued frappe.sendmail (custom templates). Email failures are logged and
never roll back a successful task update.

User preference DocType is not added in this batch. Sensible defaults apply
(enabled users with task access). Per-user Notification Settings for in-app
are respected when available. A dedicated NAVE Task preference DocType can be
added in a later batch.

Duplicate prevention:
- Per-request event keys on frappe.local (API + Document hook)
- Per-recipient dedupe within an event
- Skip when status/assignee did not meaningfully change
- Reminder daily idempotency: Notification Log + cache (see reminders module)
"""

from __future__ import annotations

import re

import frappe

from project_custom.nave_task_utils import (
	DIRECTOR_ROLE,
	MANAGER_ROLE,
	is_completion_transition,
	is_reopen_transition,
)
from project_custom.permissions.nave_task import has_task_permission


EVENT_ASSIGNED = "assigned"
EVENT_REASSIGNED = "reassigned"
EVENT_COMPLETED = "completed"
EVENT_REOPENED = "reopened"
EVENT_CLOSED = "closed"

# Variant keys for reassignment recipient groups (dedupe independently).
VARIANT_NEW_ASSIGNEE = "new"
VARIANT_PREVIOUS_ASSIGNEE = "previous"

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _escape_html(value):
	"""Stub-safe escape; unit tests install a minimal frappe.utils module."""
	fn = getattr(frappe.utils, "escape_html", None)
	if callable(fn):
		return fn(value)
	text = "" if value is None else str(value)
	return (
		text.replace("&", "&amp;")
		.replace("<", "&lt;")
		.replace(">", "&gt;")
		.replace('"', "&quot;")
	)


def _get_url_to_form(doctype, name):
	"""Stub-safe Desk URL; never hardcode the site domain."""
	fn = getattr(frappe.utils, "get_url_to_form", None)
	if callable(fn):
		return fn(doctype, name)
	get_url = getattr(frappe.utils, "get_url", None)
	path = f"/app/{(doctype or '').lower().replace(' ', '-')}/{name}"
	if callable(get_url):
		return get_url(path)
	return path


def notify_nave_task_event(
	task,
	event: str,
	*,
	actor: str | None = None,
	previous_assignee: str | None = None,
) -> None:
	"""
	Single entry point for NAVE Task notifications.
	Never raises to the caller — failures are logged.
	"""
	try:
		_dispatch(task, event, actor=actor, previous_assignee=previous_assignee)
	except Exception:
		_log_failure("NAVE Task notification dispatch failed", task, event)


def notify_status_change(
	task,
	previous_status: str | None,
	new_status: str | None,
	*,
	actor: str | None = None,
) -> None:
	"""Map a status transition to the matching notification event."""
	if not new_status or previous_status == new_status:
		return
	if is_completion_transition(previous_status, new_status):
		notify_nave_task_event(task, EVENT_COMPLETED, actor=actor)
	elif is_reopen_transition(previous_status, new_status):
		notify_nave_task_event(task, EVENT_REOPENED, actor=actor)
	elif new_status == "Closed":
		notify_nave_task_event(task, EVENT_CLOSED, actor=actor)


def notify_document_update(doc) -> None:
	"""Form-save path: detect assignee / status changes after Document.on_update."""
	if getattr(doc, "flags", None) is not None and getattr(
		doc.flags, "skip_nave_task_notifications", False
	):
		return
	if getattr(frappe.flags, "in_migrate", False) or getattr(
		frappe.flags, "in_install", False
	) or getattr(frappe.flags, "in_patch", False):
		return

	before = doc.get_doc_before_save() if hasattr(doc, "get_doc_before_save") else None
	if not before:
		return

	previous_assignee = _doc_value(before, "assigned_to")
	if previous_assignee != getattr(doc, "assigned_to", None) and getattr(doc, "assigned_to", None):
		notify_nave_task_event(
			doc,
			EVENT_REASSIGNED,
			previous_assignee=previous_assignee,
		)

	previous_status = _doc_value(before, "status")
	if previous_status != getattr(doc, "status", None):
		notify_status_change(doc, previous_status, doc.status)


def notify_document_insert(doc) -> None:
	"""Form/create path: new task assignment."""
	if getattr(doc, "flags", None) is not None and getattr(
		doc.flags, "skip_nave_task_notifications", False
	):
		return
	if getattr(frappe.flags, "in_migrate", False) or getattr(
		frappe.flags, "in_install", False
	) or getattr(frappe.flags, "in_patch", False):
		return
	notify_nave_task_event(doc, EVENT_ASSIGNED)


def _doc_value(doc, fieldname):
	if hasattr(doc, "get"):
		try:
			return doc.get(fieldname)
		except Exception:
			pass
	return getattr(doc, fieldname, None)


def _dispatch(task, event: str, *, actor: str | None, previous_assignee: str | None) -> None:
	if not task or not getattr(task, "name", None):
		return

	actor = actor or frappe.session.user

	if event == EVENT_ASSIGNED:
		if _event_already_handled(event, task.name, VARIANT_NEW_ASSIGNEE):
			return
		recipients = _assignment_recipients(task)
		_notify_recipients(
			task,
			event,
			recipients,
			actor=actor,
			action="New task assignment",
			subject_template="New Task Assigned: {title}",
			variant=VARIANT_NEW_ASSIGNEE,
		)
		return

	if event == EVENT_REASSIGNED:
		_dispatch_reassignment(task, actor=actor, previous_assignee=previous_assignee)
		return

	if event == EVENT_COMPLETED:
		if _event_already_handled(event, task.name):
			return
		recipients = _completion_recipients(task, actor=actor)
		_notify_recipients(
			task,
			event,
			recipients,
			actor=actor,
			action="Task completed",
			subject_template="Task Completed: {title}",
		)
		return

	if event == EVENT_REOPENED:
		if _event_already_handled(event, task.name):
			return
		recipients = _assignee_and_creator(task, actor=actor, exclude_actor=True)
		_notify_recipients(
			task,
			event,
			recipients,
			actor=actor,
			action="Task reopened",
			subject_template="Task Reopened: {title}",
		)
		return

	if event == EVENT_CLOSED:
		if _event_already_handled(event, task.name):
			return
		recipients = _assignee_and_creator(task, actor=actor, exclude_actor=True)
		_notify_recipients(
			task,
			event,
			recipients,
			actor=actor,
			action="Task closed",
			subject_template="Task Closed: {title}",
		)
		return


def _dispatch_reassignment(task, *, actor: str, previous_assignee: str | None) -> None:
	new_assignee = getattr(task, "assigned_to", None)
	if new_assignee and not _event_already_handled(EVENT_REASSIGNED, task.name, VARIANT_NEW_ASSIGNEE):
		_notify_recipients(
			task,
			EVENT_REASSIGNED,
			[new_assignee],
			actor=actor,
			action="Task reassigned to you",
			subject_template="Task Reassigned to You: {title}",
			variant=VARIANT_NEW_ASSIGNEE,
			exclude_actor=False,
		)

	if (
		previous_assignee
		and previous_assignee != new_assignee
		and not _event_already_handled(EVENT_REASSIGNED, task.name, VARIANT_PREVIOUS_ASSIGNEE)
	):
		_notify_recipients(
			task,
			EVENT_REASSIGNED,
			[previous_assignee],
			actor=actor,
			action="Task reassigned (you are no longer the assignee)",
			subject_template="Task Reassigned: {title}",
			variant=VARIANT_PREVIOUS_ASSIGNEE,
			message_override=(
				f"The task <b>{_escape_html(_task_title(task))}</b> "
				f"({_escape_html(task.name)}) has been reassigned from you to "
				f"<b>{_escape_html(new_assignee or 'Unassigned')}</b>."
			),
			exclude_actor=True,
		)


def _assignment_recipients(task) -> list[str]:
	assignee = getattr(task, "assigned_to", None)
	if not assignee:
		return []
	creator = _task_creator(task)
	# Do not notify when creator and assignee are the same user.
	if creator and assignee == creator:
		return []
	return [assignee]


def _assignee_and_creator(task, *, actor: str, exclude_actor: bool) -> list[str]:
	users: list[str] = []
	assignee = getattr(task, "assigned_to", None)
	creator = _task_creator(task)
	if assignee:
		users.append(assignee)
	if creator:
		users.append(creator)
	return _dedupe_users(users, actor=actor, exclude_actor=exclude_actor)


def _completion_recipients(task, *, actor: str) -> list[str]:
	users: list[str] = []
	creator = _task_creator(task)
	if creator:
		users.append(creator)
	owner = getattr(task, "owner", None)
	if owner:
		users.append(owner)
	assigned_by = getattr(task, "assigned_by", None)
	if assigned_by:
		users.append(assigned_by)
	users.extend(_eligible_managers_and_directors(task))
	return _dedupe_users(users, actor=actor, exclude_actor=True)


def _eligible_managers_and_directors(task) -> list[str]:
	"""
	Managers / directors who already have task access under NAVE permission rules.
	Department managers: same department. Directors: same department only
	(avoids notifying every director on every completion).
	"""
	return get_eligible_department_role_users(task, (MANAGER_ROLE, DIRECTOR_ROLE))


def get_eligible_department_role_users(task, roles) -> list[str]:
	"""
	Users holding any of the given roles, matching the task department, with
	task access under the existing NAVE permission model.
	Does not include System Managers / Administrators (avoids site-wide noise).
	"""
	department = getattr(task, "department", None)
	if not department:
		return []

	role_list = list(roles or [])
	candidates: list[str] = []
	for role in role_list:
		try:
			from frappe.utils.user import get_users_with_role

			candidates.extend(get_users_with_role(role) or [])
		except Exception:
			rows = frappe.get_all(
				"Has Role",
				filters={"role": role, "parenttype": "User"},
				pluck="parent",
			)
			candidates.extend(rows or [])

	eligible = []
	for user in _dedupe_users(candidates, actor=None, exclude_actor=False):
		user_department = frappe.db.get_value(
			"Employee",
			{"user_id": user, "status": "Active"},
			"department",
		)
		if user_department != department:
			continue
		if not recipient_may_access_task(task, user):
			continue
		eligible.append(user)
	return eligible


def _task_creator(task) -> str | None:
	return getattr(task, "assigned_by", None) or getattr(task, "owner", None)


def _task_title(task) -> str:
	return getattr(task, "subject", None) or task.name


def _dedupe_users(users, *, actor: str | None, exclude_actor: bool) -> list[str]:
	seen = set()
	result = []
	for user in users:
		if not user or user == "Guest":
			continue
		if exclude_actor and actor and user == actor:
			continue
		if user in seen:
			continue
		seen.add(user)
		result.append(user)
	return result


def _event_already_handled(event: str, task_name: str, variant: str = "") -> bool:
	local = _ensure_local()
	store = getattr(local, "nave_task_notifications_sent", None)
	if store is None:
		store = set()
		local.nave_task_notifications_sent = store
	key = (event, task_name, variant)
	if key in store:
		return True
	store.add(key)
	return False


def _ensure_local():
	local = getattr(frappe, "local", None)
	if local is None:
		# Lightweight namespace when frappe.local is unavailable (unit stubs).
		local = type("_Local", (), {})()
		frappe.local = local
	return local


def recipient_may_access_task(task, user: str) -> bool:
	"""Respect existing NAVE Task permission model before sharing details."""
	if not user or user == "Guest":
		return False
	try:
		return bool(has_task_permission(task, user))
	except Exception:
		return False


def _notify_recipients(
	task,
	event: str,
	recipients: list[str],
	*,
	actor: str,
	action: str,
	subject_template: str,
	variant: str = "",
	message_override: str | None = None,
	exclude_actor: bool = False,
) -> None:
	users = _dedupe_users(recipients, actor=actor, exclude_actor=exclude_actor)
	title = _task_title(task)
	subject = subject_template.format(title=title)
	desk_link = _get_url_to_form("NAVE Task", task.name)
	short_message = message_override or _default_short_message(task, action=action, actor=actor)
	email_body = _build_email_body(
		task,
		action=action,
		actor=actor,
		desk_link=desk_link,
		intro=message_override,
	)

	recipient_store = getattr(_ensure_local(), "nave_task_notification_recipients", None)
	if recipient_store is None:
		recipient_store = set()
		_ensure_local().nave_task_notification_recipients = recipient_store

	for user in users:
		recipient_key = (event, task.name, variant, user)
		if recipient_key in recipient_store:
			continue
		recipient_store.add(recipient_key)

		if not recipient_may_access_task(task, user):
			continue

		user_info = _get_user_info(user)
		if not user_info or not user_info.get("enabled"):
			continue

		if not _in_app_enabled(user):
			# Still attempt email when in-app is disabled; email gate is separate.
			pass
		else:
			_create_in_app_notification(
				user=user,
				subject=subject,
				message=short_message,
				task_name=task.name,
				actor=actor,
				link=desk_link,
			)

		_send_email_safely(
			user=user,
			email=user_info.get("email"),
			subject=subject,
			message=email_body,
			task_name=task.name,
		)


def _get_user_info(user: str) -> dict | None:
	row = frappe.db.get_value(
		"User",
		user,
		["name", "email", "enabled"],
		as_dict=True,
	)
	if not row:
		return None
	return row


def _in_app_enabled(user: str) -> bool:
	try:
		from frappe.desk.doctype.notification_settings.notification_settings import (
			is_notifications_enabled,
		)

		return bool(is_notifications_enabled(user))
	except Exception:
		return True


def _is_valid_email(email: str | None) -> bool:
	if not email or not isinstance(email, str):
		return False
	email = email.strip()
	if email.lower() in ("guest", "administrator"):
		# Administrator may still have a real email; only reject Guest.
		pass
	if email.lower() == "guest":
		return False
	return bool(_EMAIL_RE.match(email))


def _create_in_app_notification(
	*,
	user: str,
	subject: str,
	message: str,
	task_name: str,
	actor: str,
	link: str,
) -> None:
	try:
		# Mute Frappe's default Notification Log email; we send a custom template.
		previous_mute = bool(getattr(frappe.flags, "mute_emails", False))
		frappe.flags.mute_emails = True
		try:
			doc = frappe.get_doc(
				{
					"doctype": "Notification Log",
					"for_user": user,
					"from_user": actor if actor and actor != "Guest" else None,
					"subject": subject,
					"email_content": message,
					"document_type": "NAVE Task",
					"document_name": task_name,
					"type": "Alert",
					"link": link,
				}
			)
			doc.insert(ignore_permissions=True)
		finally:
			frappe.flags.mute_emails = previous_mute
	except Exception:
		_log_failure(
			"NAVE Task in-app notification failed",
			{"name": task_name},
			subject,
		)


def _send_email_safely(
	*,
	user: str,
	email: str | None,
	subject: str,
	message: str,
	task_name: str,
) -> None:
	if user == "Guest":
		return
	if not _is_valid_email(email):
		return
	try:
		frappe.sendmail(
			recipients=[email],
			subject=subject,
			message=message,
			delayed=True,
			reference_doctype="NAVE Task",
			reference_name=task_name,
			now=False,
		)
	except Exception:
		# Never roll back the task transaction or expose SMTP details to the user.
		_log_failure(
			"NAVE Task notification email failed",
			{"name": task_name, "user": user},
			subject,
		)


def _default_short_message(task, *, action: str, actor: str) -> str:
	return (
		f"{_escape_html(action)}: <b>{_escape_html(_task_title(task))}</b> "
		f"({_escape_html(task.name)}) by {_escape_html(actor or 'System')}."
	)


def _build_email_body(
	task,
	*,
	action: str,
	actor: str,
	desk_link: str,
	intro: str | None = None,
	extra_rows: list[tuple[str, str]] | None = None,
) -> str:
	rows = [
		("Task title", _task_title(task)),
		("Task ID", task.name),
		("Current status", getattr(task, "status", None) or "—"),
		("Assigned user", getattr(task, "assigned_to", None) or "—"),
		("Priority", getattr(task, "priority", None) or "—"),
		("Due date", getattr(task, "due_date", None) or "—"),
		("Project", getattr(task, "project", None) or "—"),
		("Department", getattr(task, "department", None) or "—"),
		("Action performed", action),
		("Action performed by", actor or "System"),
	]
	if extra_rows:
		# Insert timing rows before action fields.
		rows = rows[:-2] + list(extra_rows) + rows[-2:]
	intro_html = intro or f"<p>{_escape_html(action)}.</p>"
	detail_rows = "".join(
		f"<tr><td style='padding:4px 12px 4px 0;vertical-align:top;'>"
		f"<b>{_escape_html(label)}</b></td>"
		f"<td style='padding:4px 0;'>{_escape_html(str(value))}</td></tr>"
		for label, value in rows
	)
	return f"""
		{intro_html}
		<table style="border-collapse:collapse;margin:12px 0;">{detail_rows}</table>
		<p><a href="{_escape_html(desk_link)}">Open NAVE Task in Desk</a></p>
	"""


def send_task_reminder_to_user(
	task,
	*,
	user: str,
	subject: str,
	action: str,
	intro: str,
	extra_rows: list[tuple[str, str]] | None = None,
	actor: str = "Administrator",
) -> bool:
	"""
	Send one reminder (in-app + email) to a single user.
	Returns True when delivery was attempted (user enabled + permitted).
	Does not raise; failures are logged.
	"""
	try:
		if not recipient_may_access_task(task, user):
			return False
		user_info = _get_user_info(user)
		if not user_info or not user_info.get("enabled"):
			return False

		desk_link = _get_url_to_form("NAVE Task", task.name)
		short_message = intro
		email_body = _build_email_body(
			task,
			action=action,
			actor=actor,
			desk_link=desk_link,
			intro=intro,
			extra_rows=extra_rows,
		)

		# Notification Log is the durable same-day idempotency marker for reminders.
		_create_in_app_notification(
			user=user,
			subject=subject,
			message=short_message,
			task_name=task.name,
			actor=actor,
			link=desk_link,
		)

		_send_email_safely(
			user=user,
			email=user_info.get("email"),
			subject=subject,
			message=email_body,
			task_name=task.name,
		)
		return True
	except Exception:
		_log_failure("NAVE Task reminder notify failed", task, subject)
		return False


def _log_failure(title: str, task, event) -> None:
	task_name = getattr(task, "name", None) or (task.get("name") if isinstance(task, dict) else None)
	try:
		frappe.log_error(
			title=title,
			message=f"task={task_name} event={event}\n{frappe.get_traceback()}",
		)
	except Exception:
		pass
