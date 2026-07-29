"""UI helpers for NAVE Tasks Phase 2 (mirrors client button/nav rules)."""

from __future__ import annotations

from project_custom.nave_task_utils import (
	user_can_access_task,
	user_can_manage_task,
	user_can_submit_progress_update,
)

VIEW_API_MAP = {
	"dashboard": "project_custom.api.nave_task.get_dashboard_counts",
	"my_tasks": "project_custom.api.nave_task.get_my_tasks",
	"created_by_me": "project_custom.api.nave_task.get_tasks_created_by_me",
	"all_tasks": "project_custom.api.nave_task.get_all_tasks",
	"overdue_tasks": "project_custom.api.nave_task.get_overdue_tasks",
	"task_updates": "project_custom.api.nave_task.get_task_updates_list",
	"recurring_tasks": None,
	"timeline": "project_custom.api.nave_task.get_task_timeline",
}

DASHBOARD_COUNTER_VIEWS = {
	"open": {"view": "all_tasks", "status": "Open"},
	"working": {"view": "all_tasks", "status": "Working"},
	"pending": {"view": "all_tasks", "status": "Pending"},
	"overdue": {"view": "overdue_tasks", "status": None},
	"completed": {"view": "all_tasks", "status": "Completed"},
	"due_today": {"view": "all_tasks", "due_preset": "today"},
	"due_within_7_days": {"view": "all_tasks", "due_preset": "week"},
	"recently_updated": {"view": "all_tasks", "due_preset": None},
}


def escape_html(value: str | None) -> str:
	text = "" if value is None else str(value)
	return (
		text.replace("&", "&amp;")
		.replace("<", "&lt;")
		.replace(">", "&gt;")
		.replace('"', "&quot;")
		.replace("'", "&#39;")
	)


def can_show_all_tasks_nav(*, is_admin: bool, is_manager: bool) -> bool:
	"""All Tasks is useful for everyone (server-scoped); always show when logged in."""
	return True


def get_task_action_visibility(
	*,
	user: str,
	task: dict,
	is_admin: bool,
	is_manager: bool,
	user_department: str | None,
) -> dict:
	status = task.get("status")
	can_view = user_can_access_task(
		user=user,
		assigned_to=task.get("assigned_to"),
		owner=task.get("owner"),
		assigned_by=task.get("assigned_by"),
		department=task.get("department"),
		is_admin=is_admin,
		is_manager=is_manager,
		user_department=user_department,
	)
	can_manage = user_can_manage_task(
		user=user,
		owner=task.get("owner"),
		assigned_by=task.get("assigned_by"),
		department=task.get("department"),
		is_admin=is_admin,
		is_manager=is_manager,
		user_department=user_department,
	)
	can_update = user_can_submit_progress_update(
		user=user,
		assigned_to=task.get("assigned_to"),
		is_admin=is_admin,
		is_manager=is_manager,
		department=task.get("department"),
		user_department=user_department,
	)

	closed = status == "Closed"
	cancelled = status == "Cancelled"

	return {
		"open_task": can_view,
		"view_updates": can_view,
		"reply": can_view and not cancelled,
		"submit_update": can_update and not cancelled and (not closed or can_manage),
		"reassign": can_manage and not cancelled,
		"close_task": can_manage and not closed and not cancelled,
	}


def sort_timeline_chronological(items: list[dict]) -> list[dict]:
	return sorted(
		items,
		key=lambda row: (
			str(row.get("updated_on") or ""),
			str(row.get("creation") or ""),
			str(row.get("name") or ""),
		),
	)
