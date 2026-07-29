"""Pure helpers for NAVE Tasks Phase 1 (permissions, overdue, plain text)."""

from __future__ import annotations

import re
from html import unescape

TERMINAL_STATUSES = ("Completed", "Closed", "Cancelled")
ACTIVE_STATUSES = ("Open", "Working", "Pending")
UPDATE_TYPES = (
	"Progress Update",
	"Reply",
	"Reassignment",
	"Status Change",
	"Close",
	"System",
)


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
	from datetime import date, datetime

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


def build_task_permission_condition(
	user: str,
	*,
	is_admin: bool,
	is_manager: bool,
	department: str | None,
	escape,
) -> str:
	"""
	SQL fragment for NAVE Task list/query permissions.

	- Admins/System Managers: no restriction
	- Managers with department: assignee OR department OR creator
	- Everyone else: assignee OR creator only
	"""
	if not user or user == "Guest":
		return "1=0"

	if is_admin:
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
	is_manager: bool,
	user_department: str | None,
) -> bool:
	if not user or user == "Guest":
		return False
	if is_admin:
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
	is_manager: bool,
	user_department: str | None,
) -> bool:
	"""Creator, department manager, or system admin may reassign/close."""
	if not user or user == "Guest":
		return False
	if is_admin:
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
	is_manager: bool,
	department: str | None,
	user_department: str | None,
) -> bool:
	"""Employees may update only assigned tasks; managers may update department tasks."""
	if not user or user == "Guest":
		return False
	if is_admin:
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
