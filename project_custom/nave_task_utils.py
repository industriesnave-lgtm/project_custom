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

# Exact Department.name values that require elevated create/assign and that
# conversation participation alone must not unlock for list/read access.
# Match is exact (case-sensitive to Frappe Department name), never substring.
# Extend this set deliberately when a site adds restricted departments.
RESTRICTED_DEPARTMENTS = frozenset(
	{
		"HR",
		"Human Resources",
		"Accounts",
		"Finance",
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


def is_restricted_department(department_name: str | None) -> bool:
	"""
	True only when department_name exactly equals an entry in RESTRICTED_DEPARTMENTS.

	Does not use keyword / substring heuristics. Empty or unknown departments
	are not treated as restricted.
	"""
	name = (department_name or "").strip()
	if not name:
		return False
	return name in RESTRICTED_DEPARTMENTS


def normalize_department_name(department_name: str | None) -> str:
	return (department_name or "").strip()

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

# Timeline types written only by trusted server paths (APIs, hooks, scheduler).
# Direct DocType / resource-API inserts must not forge these.
PRIVILEGED_SYSTEM_UPDATE_TYPES = frozenset(
	{
		"System",
		"Reassignment",
		"Status Change",
		"Close",
		"Recurrence Event",
	}
)

PROGRESS_CHIP_TYPES = frozenset(
	{
		"Progress Update",
		"Completion Update",
		"Status Change",
		"Close",
		"Reassignment",
	}
)


def format_conversation_time(value, *, now=None) -> str:
	"""
	Compact chat timestamp.
	Examples: Today 7:15 PM · Yesterday 5:22 PM · 28 Jul 6:30 PM
	Never includes milliseconds or raw ISO dumps.
	"""
	from datetime import datetime, timedelta

	if value in (None, ""):
		return ""

	if hasattr(value, "hour"):
		dt = value
	else:
		text = str(value).strip()
		if not text:
			return ""
		# Drop microseconds / trailing Z.
		text = text.replace("T", " ").replace("Z", "")
		if "." in text:
			text = text.split(".", 1)[0]
		parsed = None
		for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
			try:
				parsed = datetime.strptime(text, fmt)
				break
			except ValueError:
				continue
		if parsed is None:
			return text[:16]
		dt = parsed

	if now is None:
		now = datetime.now()
	elif not hasattr(now, "hour"):
		now = datetime.strptime(str(now)[:19], "%Y-%m-%d %H:%M:%S")

	time_part = dt.strftime("%I:%M %p").lstrip("0")
	d0 = now.date()
	d1 = dt.date()
	if d1 == d0:
		return f"Today {time_part}"
	if d1 == d0 - timedelta(days=1):
		return f"Yesterday {time_part}"
	if d1.year == d0.year:
		return f"{dt.day} {dt.strftime('%b')} {time_part}"
	return f"{dt.day} {dt.strftime('%b %Y')} {time_part}"


def parse_seen_receipts(raw) -> dict:
	"""Return {user_id: iso_datetime_str} from stored JSON/text."""
	import json

	if not raw:
		return {}
	if isinstance(raw, dict):
		return {str(k): str(v) for k, v in raw.items() if k and v}
	try:
		data = json.loads(raw) if isinstance(raw, str) else {}
	except (TypeError, ValueError):
		return {}
	if not isinstance(data, dict):
		return {}
	return {str(k): str(v) for k, v in data.items() if k and v}


def dump_seen_receipts(receipts: dict) -> str:
	import json

	return json.dumps(parse_seen_receipts(receipts), sort_keys=True)


def attachment_kind(path: str | None) -> str:
	"""Return photo|pdf|excel|video|file|empty for compact previews."""
	if not path:
		return "empty"
	lower = str(path).lower().split("?", 1)[0]
	if lower.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp")):
		return "photo"
	if lower.endswith(".pdf"):
		return "pdf"
	if lower.endswith((".xls", ".xlsx", ".csv", ".ods")):
		return "excel"
	if lower.endswith((".mp4", ".webm", ".mov", ".m4v", ".avi")):
		return "video"
	return "file"


def build_progress_chip(update_type: str | None, status: str | None, progress) -> str | None:
	"""Compact chip text like 'Working • 50%' for progress-like events."""
	utype = update_type or ""
	if utype == "Reassignment":
		return "Reassigned"
	if utype == "Close":
		return "Closed"
	if utype not in ("Progress Update", "Completion Update", "Status Change"):
		return None
	label = status or utype
	try:
		pct = int(float(progress or 0))
	except (TypeError, ValueError):
		pct = 0
	return f"{label} • {pct}%"


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
	- Managers with department: assignee OR own department OR creator OR
	  participant (participant never unlocks RESTRICTED_DEPARTMENTS)
	- Everyone else: assignee OR creator OR participant on non-restricted tasks
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
	participant_exists = (
		"EXISTS ("
		"SELECT 1 FROM `tabNAVE Task Update` "
		"WHERE `tabNAVE Task Update`.`task` = `tabNAVE Task`.`name` "
		f"AND `tabNAVE Task Update`.`update_by` = {escaped_user}"
		")"
	)
	# Participation alone must not expose restricted-department tasks.
	if RESTRICTED_DEPARTMENTS:
		restricted_sql = ", ".join(escape(name) for name in sorted(RESTRICTED_DEPARTMENTS))
		non_restricted = (
			f"(IFNULL(`tabNAVE Task`.`department`, '') NOT IN ({restricted_sql}))"
		)
		participant_clause = f"({participant_exists} AND {non_restricted})"
	else:
		participant_clause = f"({participant_exists})"

	if is_manager and department:
		escaped_department = escape(department)
		return (
			f"({assignee_clause} "
			f"OR `tabNAVE Task`.`department` = {escaped_department} "
			f"OR {creator_clause} "
			f"OR {participant_clause})"
		)

	return f"({assignee_clause} OR {creator_clause} OR {participant_clause})"


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
	is_participant: bool = False,
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
	# Participants inherit conversation access only outside restricted departments.
	if is_participant and not is_restricted_department(department):
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


# ---------------------------------------------------------------------------
# Status workflow (shared source of truth for form, APIs, and UI)
# ---------------------------------------------------------------------------

STATUS_TRANSITIONS = {
	"Open": frozenset({"Working"}),
	"Working": frozenset({"Pending", "Completed"}),
	"Pending": frozenset({"Working", "Completed"}),
	"Completed": frozenset({"Closed", "Working"}),
	"Closed": frozenset({"Working"}),
}

MANAGER_ONLY_TRANSITIONS = frozenset(
	{
		("Completed", "Working"),
		("Closed", "Working"),
	}
)


def is_manager_level_user(*, is_admin: bool, is_director: bool, is_manager: bool) -> bool:
	"""NAVE Task Manager, Director, System Manager, or Administrator."""
	return bool(is_admin or is_director or is_manager)


def get_allowed_next_statuses(
	current: str | None,
	*,
	is_manager_level: bool,
	can_close: bool = False,
) -> list[str]:
	"""
	Allowed next statuses including the current status (same-status updates).
	Manager-only reopen transitions are omitted when is_manager_level is False.
	Completed → Closed is included only when can_close is True.
	"""
	current = current or "Open"
	allowed = set(STATUS_TRANSITIONS.get(current, frozenset()))
	if not is_manager_level:
		allowed = {
			status
			for status in allowed
			if (current, status) not in MANAGER_ONLY_TRANSITIONS
		}
	if not can_close:
		allowed.discard("Closed")
	ordered = [current]
	for status in ("Open", "Working", "Pending", "Completed", "Closed", "Cancelled"):
		if status in allowed and status != current:
			ordered.append(status)
	return ordered


def is_status_transition_allowed(
	old_status: str | None,
	new_status: str | None,
	*,
	is_manager_level: bool,
) -> bool:
	if not new_status:
		return False
	# New documents / missing previous status: allow default Open (and Open→Working bump).
	if not old_status:
		return new_status in ("Open", "Working")
	if old_status == new_status:
		return True
	allowed = STATUS_TRANSITIONS.get(old_status, frozenset())
	if new_status not in allowed:
		return False
	if (old_status, new_status) in MANAGER_ONLY_TRANSITIONS and not is_manager_level:
		return False
	return True


def validate_status_transition(
	old_status: str | None,
	new_status: str | None,
	*,
	is_manager_level: bool,
) -> None:
	if is_status_transition_allowed(
		old_status,
		new_status,
		is_manager_level=is_manager_level,
	):
		return
	old_display = old_status or "—"
	new_display = new_status or "—"
	raise ValueError(f"Cannot change status from {old_display} to {new_display}.")


def build_completion_field_updates(
	*,
	existing_completed_on=None,
	remarks=None,
	attachment=None,
	now=None,
) -> dict:
	"""
	Fields to apply when marking a task Completed.
	Does not overwrite completed_on if already set while remaining Completed.
	"""
	updates = {
		"status": "Completed",
		"progress": 100,
	}
	if not existing_completed_on:
		updates["completed_on"] = now
	remarks_text = (remarks or "").strip() if remarks is not None else None
	if remarks_text:
		updates["completion_remarks"] = remarks_text
	attachment_value = (attachment or "").strip() if attachment is not None else None
	if attachment_value:
		updates["completion_attachment"] = attachment_value
	return updates


def build_reopen_field_updates() -> dict:
	"""Reopen to Working; clear completed_on; keep remarks/attachment history."""
	return {
		"status": "Working",
		"completed_on": None,
	}


def is_reopen_transition(old_status: str | None, new_status: str | None) -> bool:
	return (old_status, new_status) in MANAGER_ONLY_TRANSITIONS


def is_completion_transition(old_status: str | None, new_status: str | None) -> bool:
	return new_status == "Completed" and old_status != "Completed"
