"""Pure helpers for NAVE Tasks (permissions, overdue, plain text, conversation)."""

from __future__ import annotations

import re
from html import unescape

TERMINAL_STATUSES = ("Completed", "Closed", "Cancelled")
ACTIVE_STATUSES = ("Open", "Working", "Pending")

MANAGER_ROLE = "NAVE Task Manager"
DIRECTOR_ROLE = "NAVE Task Director"
EMPLOYEE_ROLE = "Employee"
SYSTEM_MANAGER_ROLE = "System Manager"

# Roles allowed to open the NAVE Tasks app/page and call its whitelisted APIs.
# Document-level visibility still applies after this gate.
NAVE_TASK_APP_ROLES = frozenset(
	{
		EMPLOYEE_ROLE,
		MANAGER_ROLE,
		DIRECTOR_ROLE,
		SYSTEM_MANAGER_ROLE,
	}
)


def user_has_nave_task_app_access(user: str | None, roles) -> bool:
	"""
	App/page/API gate only. Does not grant document access by itself.
	Administrator is always allowed; Guest is never allowed.
	"""
	if not user or user == "Guest":
		return False
	if user == "Administrator":
		return True
	return bool(set(roles or []) & NAVE_TASK_APP_ROLES)

UPDATE_TYPES = (
	"Progress Update",
	"Reply",
	"Reassignment",
	"Status Change",
	"Close",
	"System",
	"Recurrence Event",
	"Clarification Required",
	"Completion Update",
	"Manager Instruction",
	"Internal Note",
)

CONVERSATION_UPDATE_TYPES = (
	"Reply",
	"Progress Update",
	"Clarification Required",
	"Completion Update",
	"Manager Instruction",
	"Internal Note",
)

INTERNAL_NOTE_TYPE = "Internal Note"

TRACKED_FIELD_LABELS = {
	"assigned_to": "Assigned To",
	"status": "Status",
	"progress": "Progress",
	"priority": "Priority",
	"due_date": "Due Date",
}


def is_terminal_status(status: str | None) -> bool:
	return (status or "") in TERMINAL_STATUSES


def compute_is_overdue(due_date, status, today) -> int:
	"""Return 1 when due_date is before today and status is not terminal."""
	if not due_date:
		return 0
	if is_terminal_status(status):
		return 0
	try:
		due = due_date if hasattr(due_date, "year") else _parse_date(str(due_date))
		today_date = today if hasattr(today, "year") else _parse_date(str(today))
	except ValueError:
		return 0
	return int(due < today_date)


def _parse_date(value: str):
	from datetime import datetime

	value = (value or "").strip()
	if not value:
		raise ValueError("empty date")
	if " " in value:
		value = value.split(" ", 1)[0]
	return datetime.strptime(value, "%Y-%m-%d").date()


def to_plain_text(value: str | None) -> str:
	"""Strip HTML to plain text without changing the stored description field."""
	if not value:
		return ""
	text = unescape(str(value))
	text = re.sub(r"(?i)<br\s*/?>", "\n", text)
	text = re.sub(r"(?i)</p\s*>", "\n", text)
	text = re.sub(r"(?i)</div\s*>", "\n", text)
	text = re.sub(r"<[^>]+>", "", text)
	text = re.sub(r"[ \t]+\n", "\n", text)
	text = re.sub(r"\n{3,}", "\n\n", text)
	return text.strip()


def is_elevated_viewer(*, is_admin: bool, is_director: bool) -> bool:
	return bool(is_admin or is_director)


def can_access_internal_notes(*, is_admin: bool, is_director: bool, is_manager: bool) -> bool:
	return bool(is_admin or is_director or is_manager)


def build_task_permission_condition(
	user: str,
	*,
	is_admin: bool,
	is_director: bool,
	is_manager: bool,
	department: str | None,
	escape,
) -> str:
	"""
	SQL fragment for NAVE Task list/query permissions.

	- Admins / Directors / System Managers: no restriction
	- Managers with department: assignee OR department OR creator
	- Everyone else: assignee OR creator only
	"""
	if not user or user == "Guest":
		return "1=0"

	if is_elevated_viewer(is_admin=is_admin, is_director=is_director):
		return ""

	escaped_user = escape(user)
	creator_clause = (
		f"(`tabNAVE Task`.`owner` = {escaped_user} "
		f"OR `tabNAVE Task`.`assigned_by` = {escaped_user})"
	)
	assignee_clause = f"`tabNAVE Task`.`assigned_to` = {escaped_user}"

	if is_manager and department:
		escaped_department = escape(department)
		return (
			f"({assignee_clause} "
			f"OR `tabNAVE Task`.`department` = {escaped_department} "
			f"OR {creator_clause})"
		)

	return f"({assignee_clause} OR {creator_clause})"


def user_can_access_task(
	*,
	user: str,
	assigned_to: str | None,
	owner: str | None,
	assigned_by: str | None,
	department: str | None,
	is_admin: bool,
	is_director: bool = False,
	is_manager: bool,
	user_department: str | None,
) -> bool:
	if not user or user == "Guest":
		return False
	if is_elevated_viewer(is_admin=is_admin, is_director=is_director):
		return True
	if assigned_to == user:
		return True
	if owner == user or assigned_by == user:
		return True
	if is_manager and user_department and department == user_department:
		return True
	return False


def user_can_manage_task(
	*,
	user: str,
	owner: str | None,
	assigned_by: str | None,
	department: str | None,
	is_admin: bool,
	is_director: bool = False,
	is_manager: bool,
	user_department: str | None,
) -> bool:
	"""Creator, director, department manager, or system admin may reassign/close."""
	if not user or user == "Guest":
		return False
	if is_elevated_viewer(is_admin=is_admin, is_director=is_director):
		return True
	if owner == user or assigned_by == user:
		return True
	if is_manager and user_department and department == user_department:
		return True
	return False


def user_can_submit_progress_update(
	*,
	user: str,
	assigned_to: str | None,
	is_admin: bool,
	is_director: bool = False,
	is_manager: bool,
	department: str | None,
	user_department: str | None,
) -> bool:
	"""Employees may update only assigned tasks; managers/directors may update more broadly."""
	if not user or user == "Guest":
		return False
	if is_elevated_viewer(is_admin=is_admin, is_director=is_director):
		return True
	if assigned_to == user:
		return True
	if is_manager and user_department and department == user_department:
		return True
	return False


def normalize_progress(status: str | None, progress) -> float:
	value = float(progress or 0)
	if value < 0 or value > 100:
		raise ValueError("Progress must be between 0 and 100.")
	if status == "Completed":
		return 100.0
	return value


def get_display_role(
	*,
	is_admin: bool,
	is_director: bool,
	is_manager: bool,
	is_creator: bool = False,
) -> str:
	if is_admin:
		return "Admin"
	if is_director:
		return "Director"
	if is_manager:
		return "Manager"
	if is_creator:
		return "Creator"
	return "Employee"


def format_field_change_message(fieldname: str, old_value, new_value) -> str:
	label = TRACKED_FIELD_LABELS.get(fieldname, fieldname)
	old_display = old_value if old_value not in (None, "") else "—"
	new_display = new_value if new_value not in (None, "") else "—"
	return f"{label} changed from {old_display} to {new_display}."


def values_differ(old_value, new_value, *, fieldname: str) -> bool:
	if fieldname == "progress":
		try:
			return float(old_value or 0) != float(new_value or 0)
		except (TypeError, ValueError):
			return str(old_value or "") != str(new_value or "")
	if fieldname == "due_date":
		return str(old_value or "") != str(new_value or "")
	return (old_value or "") != (new_value or "")
