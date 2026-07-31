import frappe

from project_custom.nave_task_utils import (
	DIRECTOR_ROLE,
	INTERNAL_NOTE_TYPE,
	MANAGER_ROLE,
	build_task_permission_condition,
	can_access_internal_notes,
	user_can_access_task,
)


def _roles(user):
	return frappe.get_roles(user)


def _is_admin(user):
	roles = _roles(user)
	return user == "Administrator" or "System Manager" in roles


def _is_director(user):
	return DIRECTOR_ROLE in _roles(user)


def _is_manager(user):
	return MANAGER_ROLE in _roles(user)


def _employee_department(user):
	return frappe.db.get_value(
		"Employee",
		{"user_id": user, "status": "Active"},
		"department",
	)


def user_can_see_internal_notes(user=None):
	user = user or frappe.session.user
	return can_access_internal_notes(
		is_admin=_is_admin(user),
		is_director=_is_director(user),
		is_manager=_is_manager(user),
	)


def get_task_query_conditions(user=None):
	user = user or frappe.session.user
	return build_task_permission_condition(
		user,
		is_admin=_is_admin(user),
		is_director=_is_director(user),
		is_manager=_is_manager(user),
		department=_employee_department(user),
		escape=frappe.db.escape,
	)


def has_task_permission(doc, user=None, permission_type=None):
	user = user or frappe.session.user
	return user_can_access_task(
		user=user,
		assigned_to=getattr(doc, "assigned_to", None),
		owner=getattr(doc, "owner", None),
		assigned_by=getattr(doc, "assigned_by", None),
		department=getattr(doc, "department", None),
		is_admin=_is_admin(user),
		is_director=_is_director(user),
		is_manager=_is_manager(user),
		user_department=_employee_department(user),
	)


def get_update_query_conditions(user=None):
	user = user or frappe.session.user

	if not user or user == "Guest":
		return "1=0"

	task_condition = get_task_query_conditions(user)
	parts = []

	if task_condition:
		parts.append(
			f"""
			EXISTS (
				SELECT 1
				FROM `tabNAVE Task`
				WHERE `tabNAVE Task`.`name` = `tabNAVE Task Update`.`task`
				AND ({task_condition})
			)
			"""
		)

	if not user_can_see_internal_notes(user):
		escaped_type = frappe.db.escape(INTERNAL_NOTE_TYPE)
		parts.append(
			f"IFNULL(`tabNAVE Task Update`.`update_type`, '') != {escaped_type}"
		)

	if not parts:
		return ""

	return " AND ".join(f"({part.strip()})" for part in parts)


def has_update_permission(doc, user=None, permission_type=None):
	user = user or frappe.session.user

	if not getattr(doc, "task", None):
		return False

	if (
		getattr(doc, "update_type", None) == INTERNAL_NOTE_TYPE
		and not user_can_see_internal_notes(user)
	):
		return False

	task = frappe.get_doc("NAVE Task", doc.task)
	return has_task_permission(task, user, permission_type)
