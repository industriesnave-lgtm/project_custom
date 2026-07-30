import frappe
from frappe.utils import add_days, cint, flt, now_datetime, nowdate

from project_custom.nave_task_recurrence import normalize_support_required
from project_custom.nave_task_utils import (
	CONVERSATION_UPDATE_TYPES,
	DIRECTOR_ROLE,
	INTERNAL_NOTE_TYPE,
	MANAGER_ROLE,
	compute_is_overdue,
	get_display_role,
	normalize_progress,
	to_plain_text,
	user_can_access_task,
	user_can_manage_task,
	user_can_submit_progress_update,
)
from project_custom.permissions.nave_task import user_can_see_internal_notes


TASK_LIST_FIELDS = [
	"name",
	"subject",
	"description",
	"category",
	"priority",
	"status",
	"progress",
	"assigned_to",
	"assigned_employee",
	"assigned_by",
	"owner",
	"department",
	"company",
	"project",
	"site",
	"start_date",
	"due_date",
	"is_overdue",
	"is_recurring",
	"recurrence_active",
	"recurrence_frequency",
	"recurrence_start_date",
	"recurrence_end_date",
	"next_creation_date",
	"last_generated_date",
	"recurrence_due_after_days",
	"recurring_template",
	"generated_from",
	"recurrence_sequence",
	"recurrence_occurrence_date",
	"latest_update",
	"pending_reason",
	"support_required",
	"modified",
	"creation",
]

UPDATE_LIST_FIELDS = [
	"name",
	"task",
	"update_by",
	"employee",
	"updated_on",
	"update_type",
	"status",
	"progress",
	"update_text",
	"pending_reason",
	"support_required",
	"attachment",
	"creation",
]

ACTIVE_STATUSES = ("Open", "Working", "Pending")


def is_admin(user=None):
	user = user or frappe.session.user
	roles = frappe.get_roles(user)
	return user == "Administrator" or "System Manager" in roles


def is_task_director(user=None):
	user = user or frappe.session.user
	return DIRECTOR_ROLE in frappe.get_roles(user)


def is_task_manager(user=None):
	user = user or frappe.session.user
	return MANAGER_ROLE in frappe.get_roles(user)


def require_login():
	if frappe.session.user == "Guest":
		frappe.throw("Please log in.", frappe.PermissionError)


def get_employee(user=None):
	user = user or frappe.session.user
	return frappe.db.get_value(
		"Employee",
		{
			"user_id": user,
			"status": "Active",
		},
		["name", "department", "employee_name"],
		as_dict=True,
	)


def get_user_department(user=None):
	employee = get_employee(user)
	return employee.department if employee else None


def get_user_full_name(user=None):
	user = user or frappe.session.user
	return (
		frappe.db.get_value("User", user, "full_name")
		or frappe.db.get_value("User", user, "first_name")
		or user
	)


def can_access_task_doc(task, user=None):
	user = user or frappe.session.user
	return user_can_access_task(
		user=user,
		assigned_to=task.assigned_to,
		owner=getattr(task, "owner", None),
		assigned_by=task.assigned_by,
		department=task.department,
		is_admin=is_admin(user),
		is_director=is_task_director(user),
		is_manager=is_task_manager(user),
		user_department=get_user_department(user),
	)


def can_manage_task_doc(task, user=None):
	user = user or frappe.session.user
	return user_can_manage_task(
		user=user,
		owner=getattr(task, "owner", None),
		assigned_by=task.assigned_by,
		department=task.department,
		is_admin=is_admin(user),
		is_director=is_task_director(user),
		is_manager=is_task_manager(user),
		user_department=get_user_department(user),
	)


def can_submit_progress_on_task(task, user=None):
	user = user or frappe.session.user
	return user_can_submit_progress_update(
		user=user,
		assigned_to=task.assigned_to,
		is_admin=is_admin(user),
		is_director=is_task_director(user),
		is_manager=is_task_manager(user),
		department=task.department,
		user_department=get_user_department(user),
	)


def get_task_for_user(task_name, user=None):
	user = user or frappe.session.user
	task = frappe.get_doc("NAVE Task", task_name)

	if can_access_task_doc(task, user):
		return task

	frappe.throw(
		"You are not permitted to access this task.",
		frappe.PermissionError,
	)


def enrich_timeline_item(row, task=None):
	item = dict(row)
	sender = item.get("update_by") or ""
	employee_name = None
	if item.get("employee"):
		employee_name = frappe.db.get_value(
			"Employee",
			item.get("employee"),
			"employee_name",
		) or item.get("employee")

	is_creator = False
	if task is not None:
		is_creator = sender in (
			getattr(task, "owner", None),
			getattr(task, "assigned_by", None),
		)

	item["update_text"] = to_plain_text(item.get("update_text"))
	item["pending_reason"] = to_plain_text(item.get("pending_reason"))
	item["update_type"] = item.get("update_type") or "Progress Update"
	item["sender_user_id"] = sender
	item["sender_full_name"] = get_user_full_name(sender) if sender else ""
	item["employee_name"] = employee_name
	item["display_role"] = get_display_role(
		is_admin=is_admin(sender) if sender else False,
		is_director=is_task_director(sender) if sender else False,
		is_manager=is_task_manager(sender) if sender else False,
		is_creator=is_creator,
	)
	item["datetime"] = item.get("updated_on") or item.get("creation")
	return item



def serialize_task(task_row):
	if hasattr(task_row, "as_dict"):
		row = task_row.as_dict()
	else:
		row = dict(task_row)

	payload = {field: row.get(field) for field in TASK_LIST_FIELDS}
	payload["description"] = to_plain_text(payload.get("description"))
	payload["latest_update"] = to_plain_text(payload.get("latest_update"))
	payload["is_overdue"] = cint(payload.get("is_overdue"))
	payload["progress"] = flt(payload.get("progress"))
	return payload


def _parse_page(page, page_length):
	page = max(cint(page) or 1, 1)
	page_length = min(max(cint(page_length) or 20, 1), 100)
	return page, page_length, (page - 1) * page_length


def _as_filter_list(filters):
	"""Normalize dict or list filters into a Frappe filter list."""
	if isinstance(filters, list):
		return filters

	result = []
	for key, value in (filters or {}).items():
		result.append([key, "=", value])
	return result


RECENTLY_UPDATED_DAYS = 7


def recently_updated_modified_after(today=None):
	"""Cutoff datetime string matching get_dashboard_counts recently_updated."""
	today = today or nowdate()
	cutoff = add_days(today, -RECENTLY_UPDATED_DAYS)
	return f"{cutoff} 00:00:00"


def _normalize_modified_after(modified_after):
	value = (modified_after or "").strip()
	if not value:
		return None
	if " " not in value:
		return f"{value} 00:00:00"
	return value


def _apply_common_filters(
	filters,
	*,
	status=None,
	priority=None,
	project=None,
	assigned_user=None,
	due_date=None,
	due_before=None,
	due_after=None,
	modified_after=None,
	search=None,
):
	filters = _as_filter_list(filters)

	if status:
		filters.append(["status", "=", status])
	if priority:
		filters.append(["priority", "=", priority])
	if project:
		filters.append(["project", "=", project])
	if assigned_user:
		filters.append(["assigned_to", "=", assigned_user])
	if due_date:
		filters.append(["due_date", "=", due_date])
	if due_before:
		filters.append(["due_date", "<=", due_before])
	if due_after:
		filters.append(["due_date", ">=", due_after])
	normalized_modified = _normalize_modified_after(modified_after)
	if normalized_modified:
		filters.append(["modified", ">=", normalized_modified])
	if search:
		term = f"%{(search or '').strip()}%"
		if term != "%%":
			filters.append(["subject", "like", term])
	return filters


def _permission_aware_count(doctype, filters=None, or_filters=None):
	return len(
		frappe.get_list(
			doctype,
			filters=filters or {},
			or_filters=or_filters,
			fields=["name"],
			limit_page_length=10000,
			ignore_permissions=False,
		)
	)


def _list_tasks(
	filters,
	*,
	page=1,
	page_length=20,
	order_by="is_overdue desc, due_date asc, modified desc",
	or_filters=None,
):
	page, page_length, start = _parse_page(page, page_length)

	rows = frappe.get_list(
		"NAVE Task",
		filters=filters,
		or_filters=or_filters,
		fields=TASK_LIST_FIELDS,
		order_by=order_by,
		limit_start=start,
		limit_page_length=page_length,
		ignore_permissions=False,
	)
	total = _permission_aware_count("NAVE Task", filters, or_filters)

	return {
		"page": page,
		"page_length": page_length,
		"total": total,
		"data": [serialize_task(row) for row in rows],
	}


@frappe.whitelist()
def has_app_permission():
	return frappe.session.user != "Guest"


@frappe.whitelist()
def get_my_tasks(
	page=1,
	page_length=20,
	status=None,
	priority=None,
	project=None,
	due_date=None,
	due_before=None,
	due_after=None,
	modified_after=None,
	search=None,
):
	"""Tasks assigned to the current user."""
	require_login()
	filters = _apply_common_filters(
		{"assigned_to": frappe.session.user},
		status=status,
		priority=priority,
		project=project,
		due_date=due_date,
		due_before=due_before,
		due_after=due_after,
		modified_after=modified_after,
		search=search,
	)
	return _list_tasks(filters, page=page, page_length=page_length)


@frappe.whitelist()
def get_tasks_created_by_me(
	page=1,
	page_length=20,
	status=None,
	priority=None,
	project=None,
	assigned_user=None,
	due_date=None,
	due_before=None,
	due_after=None,
	modified_after=None,
	search=None,
):
	"""Tasks created by the current user (owner or assigned_by)."""
	require_login()
	user = frappe.session.user
	filters = _apply_common_filters(
		{},
		status=status,
		priority=priority,
		project=project,
		assigned_user=assigned_user,
		due_date=due_date,
		due_before=due_before,
		due_after=due_after,
		modified_after=modified_after,
		search=search,
	)
	or_filters = [
		["owner", "=", user],
		["assigned_by", "=", user],
	]
	return _list_tasks(
		filters,
		page=page,
		page_length=page_length,
		or_filters=or_filters,
	)


@frappe.whitelist()
def get_all_tasks(
	page=1,
	page_length=20,
	status=None,
	priority=None,
	project=None,
	assigned_user=None,
	creator=None,
	due_date=None,
	due_before=None,
	due_after=None,
	modified_after=None,
	search=None,
):
	"""All tasks visible to the current user via permission hooks."""
	require_login()
	or_filters = None
	filters = _apply_common_filters(
		{},
		status=status,
		priority=priority,
		project=project,
		assigned_user=assigned_user,
		due_date=due_date,
		due_before=due_before,
		due_after=due_after,
		modified_after=modified_after,
		search=search,
	)
	if creator:
		or_filters = [
			["owner", "=", creator],
			["assigned_by", "=", creator],
		]
	return _list_tasks(
		filters,
		page=page,
		page_length=page_length,
		or_filters=or_filters,
	)


@frappe.whitelist()
def get_overdue_tasks(
	page=1,
	page_length=20,
	status=None,
	priority=None,
	project=None,
	assigned_user=None,
	creator=None,
	search=None,
):
	require_login()
	or_filters = None
	filters = _apply_common_filters(
		{"is_overdue": 1},
		status=status,
		priority=priority,
		project=project,
		assigned_user=assigned_user,
		search=search,
	)
	if creator:
		or_filters = [
			["owner", "=", creator],
			["assigned_by", "=", creator],
		]
	return _list_tasks(
		filters,
		page=page,
		page_length=page_length,
		or_filters=or_filters,
		order_by="due_date asc, modified desc",
	)


@frappe.whitelist()
def get_task_updates_list(
	page=1,
	page_length=20,
	task=None,
	update_type=None,
	status=None,
	update_by=None,
):
	"""Paginated NAVE Task Update list scoped by permission hooks."""
	require_login()
	page, page_length, start = _parse_page(page, page_length)
	filters = {}
	if task:
		filters["task"] = task
	if update_type:
		if update_type == INTERNAL_NOTE_TYPE and not user_can_see_internal_notes():
			frappe.throw(
				"You are not permitted to view Internal Notes.",
				frappe.PermissionError,
			)
		filters["update_type"] = update_type
	elif not user_can_see_internal_notes():
		filters["update_type"] = ["!=", INTERNAL_NOTE_TYPE]
	if status:
		filters["status"] = status
	if update_by:
		filters["update_by"] = update_by

	rows = frappe.get_list(
		"NAVE Task Update",
		filters=filters,
		fields=UPDATE_LIST_FIELDS,
		order_by="updated_on desc",
		limit_start=start,
		limit_page_length=page_length,
		ignore_permissions=False,
	)
	total = _permission_aware_count("NAVE Task Update", filters)

	return {
		"page": page,
		"page_length": page_length,
		"total": total,
		"data": [enrich_timeline_item(row) for row in rows],
	}


@frappe.whitelist()
def get_dashboard_counts():
	"""Permission-aware dashboard counters for the current user."""
	require_login()
	today = nowdate()
	week = add_days(today, 7)
	recent_modified_after = recently_updated_modified_after(today)

	return {
		"open": _permission_aware_count("NAVE Task", {"status": "Open"}),
		"working": _permission_aware_count("NAVE Task", {"status": "Working"}),
		"pending": _permission_aware_count("NAVE Task", {"status": "Pending"}),
		"overdue": _permission_aware_count("NAVE Task", {"is_overdue": 1}),
		"completed": _permission_aware_count("NAVE Task", {"status": "Completed"}),
		"due_today": _permission_aware_count(
			"NAVE Task",
			{
				"due_date": today,
				"status": ["in", list(ACTIVE_STATUSES)],
			},
		),
		"due_within_7_days": _permission_aware_count(
			"NAVE Task",
			[
				["due_date", ">=", today],
				["due_date", "<=", week],
				["status", "in", list(ACTIVE_STATUSES)],
			],
		),
		"recently_updated": _permission_aware_count(
			"NAVE Task",
			[["modified", ">=", recent_modified_after]],
		),
		"recently_updated_modified_after": recent_modified_after,
	}


@frappe.whitelist()
def get_task_timeline(task_name):
	"""Permanent chronological timeline for one task."""
	require_login()
	task = get_task_for_user(task_name)

	filters = {"task": task.name}
	if not user_can_see_internal_notes():
		filters["update_type"] = ["!=", INTERNAL_NOTE_TYPE]

	rows = frappe.get_list(
		"NAVE Task Update",
		filters=filters,
		fields=UPDATE_LIST_FIELDS,
		order_by="updated_on asc, creation asc",
		limit_page_length=1000,
		ignore_permissions=False,
	)

	# Extra hard filter for Internal Notes (defense in depth).
	timeline = []
	for row in rows:
		if row.get("update_type") == INTERNAL_NOTE_TYPE and not user_can_see_internal_notes():
			continue
		timeline.append(enrich_timeline_item(row, task))

	return {
		"task": serialize_task(task),
		"timeline": timeline,
		"can_post_internal_note": user_can_see_internal_notes(),
		"allowed_update_types": list(
			t
			for t in CONVERSATION_UPDATE_TYPES
			if t != INTERNAL_NOTE_TYPE or user_can_see_internal_notes()
		),
	}


def _create_history_entry(
	task,
	*,
	update_type,
	update_text,
	status=None,
	progress=None,
	pending_reason=None,
	support_required=None,
	attachment=None,
):
	employee = get_employee()
	doc = frappe.get_doc(
		{
			"doctype": "NAVE Task Update",
			"task": task.name,
			"update_by": frappe.session.user,
			"employee": employee.name if employee else None,
			"updated_on": now_datetime(),
			"update_type": update_type,
			"status": status or task.status,
			"progress": flt(progress if progress is not None else task.progress),
			"update_text": (update_text or "").strip(),
			"pending_reason": (pending_reason or "").strip(),
			"support_required": support_required
			if support_required is not None
			else task.support_required,
			"attachment": attachment,
		}
	)
	doc.insert(ignore_permissions=True)
	return doc


def _assert_task_not_closed_for_normal_update(task):
	if task.status == "Closed" and not can_manage_task_doc(task):
		frappe.throw(
			"Closed tasks cannot be updated. Ask an authorized user to reopen the task.",
			frappe.ValidationError,
		)
	if task.status == "Cancelled":
		frappe.throw("Cancelled tasks cannot be updated.", frappe.ValidationError)


@frappe.whitelist()
def submit_update(
	task_name,
	status,
	progress,
	update_text,
	pending_reason=None,
	support_required=None,
	attachment=None,
):
	require_login()
	user = frappe.session.user
	task = get_task_for_user(task_name, user)

	if not can_submit_progress_on_task(task, user):
		frappe.throw(
			"Only the assigned employee or an authorized manager can submit progress updates.",
			frappe.PermissionError,
		)

	_assert_task_not_closed_for_normal_update(task)

	# Managers reopening a closed task may move it back to an active status.
	if task.status == "Closed" and status not in ("Open", "Working", "Pending", "Completed"):
		frappe.throw("Invalid reopen status for a closed task.")

	if status not in ("Open", "Working", "Pending", "Completed"):
		frappe.throw("Invalid task status.")

	try:
		progress = normalize_progress(status, progress)
	except ValueError as exc:
		frappe.throw(str(exc))

	if not (update_text or "").strip():
		frappe.throw("Please enter your progress update.")

	if status == "Pending" and not (pending_reason or "").strip():
		frappe.throw("Pending Reason is required.")

	previous_status = task.status
	normalized_support = (
		normalize_support_required(support_required)
		if support_required is not None
		else None
	)
	update = _create_history_entry(
		task,
		update_type="Progress Update",
		update_text=update_text.strip(),
		status=status,
		progress=progress,
		pending_reason=pending_reason,
		support_required=normalized_support
		if normalized_support is not None
		else task.support_required,
		attachment=attachment,
	)

	task.db_set("status", status, update_modified=False)
	task.db_set("progress", progress, update_modified=False)
	task.db_set("latest_update", update_text.strip(), update_modified=False)
	task.db_set(
		"pending_reason",
		(pending_reason or "").strip(),
		update_modified=False,
	)
	task.db_set(
		"is_overdue",
		compute_is_overdue(task.due_date, status, nowdate()),
		update_modified=False,
	)
	if normalized_support is not None:
		task.db_set("support_required", normalized_support, update_modified=True)
	else:
		task.db_set("latest_update", update_text.strip(), update_modified=True)

	if previous_status != status:
		_create_history_entry(
			task,
			update_type="Status Change",
			update_text=f"Status changed from {previous_status} to {status}.",
			status=status,
			progress=progress,
		)

	return {
		"ok": True,
		"task": task.name,
		"update": update.name,
		"status": status,
		"progress": progress,
	}


@frappe.whitelist()
def reply_to_task(task_name, message, attachment=None):
	return post_task_message(
		task_name=task_name,
		message=message,
		update_type="Reply",
		attachment=attachment,
	)


@frappe.whitelist()
def post_task_message(
	task_name,
	message,
	update_type="Reply",
	attachment=None,
	progress=None,
	status=None,
):
	"""
	Inline conversation composer endpoint.
	Supports Reply / Progress Update / Clarification Required /
	Completion Update / Manager Instruction / Internal Note.
	"""
	require_login()
	user = frappe.session.user
	task = get_task_for_user(task_name, user)

	update_type = (update_type or "Reply").strip()
	if update_type not in CONVERSATION_UPDATE_TYPES:
		frappe.throw("Invalid update type.")

	if update_type == INTERNAL_NOTE_TYPE and not user_can_see_internal_notes(user):
		frappe.throw(
			"Only NAVE Task Directors, Managers, and System Managers can create Internal Notes.",
			frappe.PermissionError,
		)

	if update_type == "Manager Instruction" and not (
		is_admin(user) or is_task_director(user) or is_task_manager(user)
	):
		frappe.throw(
			"Only managers, directors, and admins can post Manager Instructions.",
			frappe.PermissionError,
		)

	if not (message or "").strip():
		frappe.throw("Please enter a message.")

	if task.status == "Cancelled":
		frappe.throw("Cancelled tasks cannot accept conversation messages.")

	new_status = task.status
	new_progress = flt(task.progress)

	if update_type == "Progress Update" and can_submit_progress_on_task(task, user):
		if status:
			new_status = status
		if progress is not None:
			try:
				new_progress = normalize_progress(new_status, progress)
			except ValueError as exc:
				frappe.throw(str(exc))
	elif update_type == "Completion Update":
		if not can_submit_progress_on_task(task, user) and not can_manage_task_doc(task, user):
			frappe.throw(
				"You are not permitted to post a Completion Update on this task.",
				frappe.PermissionError,
			)
		new_status = "Completed"
		new_progress = 100

	update = _create_history_entry(
		task,
		update_type=update_type,
		update_text=message.strip(),
		status=new_status,
		progress=new_progress,
		attachment=attachment,
	)

	# Apply task field changes only for progress/completion conversation types.
	if update_type in ("Progress Update", "Completion Update") and (
		new_status != task.status or flt(new_progress) != flt(task.progress)
	):
		if getattr(task, "flags", None) is not None:
			task.flags.skip_field_change_log = True
		task.db_set("status", new_status, update_modified=False)
		task.db_set("progress", new_progress, update_modified=False)
		task.db_set(
			"is_overdue",
			compute_is_overdue(task.due_date, new_status, nowdate()),
			update_modified=False,
		)

	if update_type != INTERNAL_NOTE_TYPE:
		task.db_set("latest_update", message.strip(), update_modified=True)

	return {
		"ok": True,
		"task": task.name,
		"update": getattr(update, "name", None),
		"update_type": update_type,
		"timeline_item": enrich_timeline_item(
			{
				"name": getattr(update, "name", None),
				"task": task.name,
				"update_by": getattr(update, "update_by", user),
				"employee": getattr(update, "employee", None),
				"updated_on": getattr(update, "updated_on", None),
				"update_type": getattr(update, "update_type", update_type),
				"status": getattr(update, "status", new_status),
				"progress": getattr(update, "progress", new_progress),
				"update_text": getattr(update, "update_text", message.strip()),
				"pending_reason": getattr(update, "pending_reason", None),
				"support_required": getattr(update, "support_required", None),
				"attachment": getattr(update, "attachment", attachment),
				"creation": getattr(update, "creation", None),
			},
			task,
		),
	}


@frappe.whitelist()
def reassign_task(task_name, assigned_to, note=None):
	require_login()
	user = frappe.session.user
	# Actor is always the session user — never trust browser-supplied user IDs.
	task = get_task_for_user(task_name, user)

	if not can_manage_task_doc(task, user):
		frappe.throw(
			"Only the task creator or an authorized manager can reassign this task.",
			frappe.PermissionError,
		)

	assigned_to = (assigned_to or "").strip()
	if not assigned_to:
		frappe.throw("Please choose a user to reassign the task to.")

	if not frappe.db.exists("User", assigned_to):
		frappe.throw("Assigned user does not exist.")

	if task.status == "Cancelled":
		frappe.throw("Cancelled tasks cannot be reassigned.")

	previous_assignee = task.assigned_to
	if previous_assignee == assigned_to:
		frappe.throw("Task is already assigned to this user.")

	employee = frappe.db.get_value(
		"Employee",
		{"user_id": assigned_to, "status": "Active"},
		["name", "department", "company"],
		as_dict=True,
	)

	task.db_set("assigned_to", assigned_to, update_modified=False)
	if employee:
		task.db_set("assigned_employee", employee.name, update_modified=False)
		if employee.department:
			task.db_set("department", employee.department, update_modified=False)
	else:
		task.db_set("assigned_employee", None, update_modified=False)

	note_text = (note or "").strip()
	history_text = (
		f"Reassigned from {previous_assignee or 'Unassigned'} to {assigned_to}."
	)
	if note_text:
		history_text = f"{history_text}\n{note_text}"

	update = _create_history_entry(
		task,
		update_type="Reassignment",
		update_text=history_text,
		status=task.status,
		progress=task.progress,
	)
	task.db_set("latest_update", history_text, update_modified=True)

	task.reload()
	# db_set bypasses Document.on_update — sync ToDos explicitly for API reassign.
	task.sync_assignment_todos(previous_assignee=previous_assignee)

	return {
		"ok": True,
		"task": task.name,
		"update": update.name,
		"assigned_to": assigned_to,
		"previous_assignee": previous_assignee,
	}


@frappe.whitelist()
def close_task(task_name, remarks=None):
	require_login()
	user = frappe.session.user
	task = get_task_for_user(task_name, user)

	if not can_manage_task_doc(task, user):
		frappe.throw(
			"Only the task creator or an authorized manager can close this task.",
			frappe.PermissionError,
		)

	if task.status == "Closed":
		frappe.throw("Task is already closed.")

	if task.status == "Cancelled":
		frappe.throw("Cancelled tasks cannot be closed.")

	previous_status = task.status
	remarks_text = (remarks or "").strip() or f"Task closed (was {previous_status})."

	task.db_set("status", "Closed", update_modified=False)
	task.db_set(
		"is_overdue",
		compute_is_overdue(task.due_date, "Closed", nowdate()),
		update_modified=False,
	)
	task.db_set("latest_update", remarks_text, update_modified=True)

	update = _create_history_entry(
		task,
		update_type="Close",
		update_text=remarks_text,
		status="Closed",
		progress=task.progress,
	)

	return {
		"ok": True,
		"task": task.name,
		"update": update.name,
		"status": "Closed",
		"previous_status": previous_status,
	}


def refresh_overdue_flags():
	"""
	Daily scheduler entry point.
	Refreshes is_overdue without changing the real task status.
	"""
	today = nowdate()
	updated = 0

	tasks = frappe.get_all(
		"NAVE Task",
		fields=["name", "due_date", "status", "is_overdue"],
		limit_page_length=50000,
	)

	for task in tasks:
		new_flag = compute_is_overdue(task.due_date, task.status, today)
		if cint(task.is_overdue) != new_flag:
			frappe.db.set_value(
				"NAVE Task",
				task.name,
				"is_overdue",
				new_flag,
				update_modified=False,
			)
			updated += 1

	return {"ok": True, "updated": updated, "checked": len(tasks)}


def run_daily_nave_task_jobs():
	"""Combined daily job: overdue refresh + recurring generation."""
	overdue = refresh_overdue_flags()
	from project_custom.nave_task_generation import generate_due_recurring_tasks

	recurrence = generate_due_recurring_tasks()
	return {"ok": True, "overdue": overdue, "recurrence": recurrence}


RECURRING_LIST_FIELDS = [
	"name",
	"subject",
	"assigned_to",
	"assigned_employee",
	"assigned_by",
	"owner",
	"project",
	"department",
	"priority",
	"status",
	"is_recurring",
	"recurrence_active",
	"recurrence_frequency",
	"recurrence_start_date",
	"recurrence_end_date",
	"next_creation_date",
	"last_generated_date",
	"recurrence_due_after_days",
	"modified",
]


@frappe.whitelist()
def get_recurring_tasks(
	page=1,
	page_length=20,
	frequency=None,
	active=None,
	project=None,
	search=None,
):
	"""List recurring templates visible to the current user."""
	require_login()
	page, page_length, start = _parse_page(page, page_length)
	filters = [["is_recurring", "=", 1]]
	if frequency:
		filters.append(["recurrence_frequency", "=", frequency])
	if active in (0, 1, "0", "1"):
		filters.append(["recurrence_active", "=", cint(active)])
	if project:
		filters.append(["project", "=", project])
	if search:
		filters.append(["subject", "like", f"%{search.strip()}%"])

	rows = frappe.get_list(
		"NAVE Task",
		filters=filters,
		fields=RECURRING_LIST_FIELDS,
		order_by="next_creation_date asc, modified desc",
		limit_start=start,
		limit_page_length=page_length,
		ignore_permissions=False,
	)
	total = _permission_aware_count("NAVE Task", filters)
	return {
		"page": page,
		"page_length": page_length,
		"total": total,
		"data": rows,
	}


@frappe.whitelist()
def get_generated_tasks(template_name, page=1, page_length=20):
	require_login()
	template = get_task_for_user(template_name)
	page, page_length, start = _parse_page(page, page_length)
	filters = {"generated_from": template.name}
	rows = frappe.get_list(
		"NAVE Task",
		filters=filters,
		fields=TASK_LIST_FIELDS,
		order_by="recurrence_occurrence_date desc, creation desc",
		limit_start=start,
		limit_page_length=page_length,
		ignore_permissions=False,
	)
	total = _permission_aware_count("NAVE Task", filters)
	return {
		"page": page,
		"page_length": page_length,
		"total": total,
		"template": template.name,
		"data": [serialize_task(row) for row in rows],
	}


@frappe.whitelist()
def enable_recurring_task(task_name):
	require_login()
	user = frappe.session.user
	task = get_task_for_user(task_name, user)
	if not can_manage_task_doc(task, user):
		frappe.throw(
			"Only the task creator or an authorized manager can enable recurrence.",
			frappe.PermissionError,
		)
	if not cint(task.is_recurring):
		frappe.throw("This task is not a recurring template.")
	if task.status in ("Closed", "Cancelled"):
		frappe.throw("Closed or Cancelled templates cannot be enabled.")

	task.db_set("recurrence_active", 1, update_modified=True)
	from project_custom.nave_task_generation import _create_recurrence_history

	_create_recurrence_history(task.name, "Recurrence enabled.", status=task.status, progress=task.progress)
	return {"ok": True, "task": task.name, "recurrence_active": 1}


@frappe.whitelist()
def disable_recurring_task(task_name):
	require_login()
	user = frappe.session.user
	task = get_task_for_user(task_name, user)
	if not can_manage_task_doc(task, user):
		frappe.throw(
			"Only the task creator or an authorized manager can disable recurrence.",
			frappe.PermissionError,
		)
	if not cint(task.is_recurring):
		frappe.throw("This task is not a recurring template.")

	task.db_set("recurrence_active", 0, update_modified=True)
	from project_custom.nave_task_generation import _create_recurrence_history

	_create_recurrence_history(
		task.name,
		"Recurrence disabled. Previously generated tasks were preserved.",
		status=task.status,
		progress=task.progress,
	)
	return {"ok": True, "task": task.name, "recurrence_active": 0}


@frappe.whitelist()
def generate_recurring_task_now(task_name, occurrence_date=None):
	"""
	Manual Generate Now.
	Uses duplicate-prevention; defaults to next_creation_date or today.
	"""
	require_login()
	user = frappe.session.user
	task = get_task_for_user(task_name, user)
	if not can_manage_task_doc(task, user):
		frappe.throw(
			"Only the task creator or an authorized manager can generate recurring tasks.",
			frappe.PermissionError,
		)
	if not cint(task.is_recurring):
		frappe.throw("This task is not a recurring template.")
	if not cint(task.recurrence_active):
		frappe.throw("Recurrence is disabled for this template.")
	if task.status in ("Closed", "Cancelled"):
		frappe.throw("Closed or Cancelled templates cannot generate tasks.")

	from project_custom.nave_task_generation import (
		_create_recurrence_history,
		process_template,
	)
	from project_custom.nave_task_recurrence import _as_date

	occurrence = _as_date(occurrence_date) or _as_date(task.next_creation_date) or _as_date(nowdate())
	_create_recurrence_history(
		task.name,
		f"Manual Generate Now requested for {occurrence.isoformat()}.",
		status=task.status,
		progress=task.progress,
	)
	result = process_template(
		task.name,
		force_occurrence=occurrence,
		source="manual",
	)
	return {"ok": True, "task": task.name, "result": result}


# Backwards-compatible alias used by the existing page.
get_tasks = get_my_tasks
