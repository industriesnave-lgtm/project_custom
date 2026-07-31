import frappe
from frappe.utils import add_days, cint, flt, now_datetime, nowdate

from project_custom.nave_task_notifications import (
	EVENT_ASSIGNED,
	EVENT_MESSAGE,
	EVENT_REASSIGNED,
	notify_nave_task_event,
	notify_status_change,
)
from project_custom.nave_task_recurrence import normalize_support_required
from project_custom.nave_task_utils import (
	CONVERSATION_UPDATE_TYPES,
	DIRECTOR_ROLE,
	INTERNAL_NOTE_TYPE,
	MANAGER_ROLE,
	NAVE_TASK_APP_ROLES,
	attachment_kind,
	build_completion_field_updates,
	build_progress_chip,
	build_reopen_field_updates,
	compute_is_overdue,
	dump_seen_receipts,
	format_conversation_time,
	get_allowed_next_statuses,
	get_display_role,
	is_manager_level_user,
	is_restricted_department,
	is_reopen_transition,
	normalize_progress,
	parse_seen_receipts,
	to_plain_text,
	user_can_access_task,
	user_can_manage_task,
	user_can_submit_progress_update,
	user_has_nave_task_app_access,
	validate_status_transition,
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
	"completed_on",
	"completion_remarks",
	"completion_attachment",
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

UPDATE_OPTIONAL_FIELDS = ("parent_update", "seen_receipts")


def _update_list_fields():
	"""Include conversation columns when present (pre-migrate safe)."""
	fields = list(UPDATE_LIST_FIELDS)
	has_column = getattr(frappe.db, "has_column", None)
	for fieldname in UPDATE_OPTIONAL_FIELDS:
		try:
			if callable(has_column) and has_column("NAVE Task Update", fieldname):
				fields.append(fieldname)
			elif not callable(has_column):
				fields.append(fieldname)
		except Exception:
			pass
	return fields

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


def session_is_manager_level(user=None):
	user = user or frappe.session.user
	return is_manager_level_user(
		is_admin=is_admin(user),
		is_director=is_task_director(user),
		is_manager=is_task_manager(user),
	)


def require_login():
	if frappe.session.user == "Guest":
		frappe.throw("Please log in.", frappe.PermissionError)


def require_nave_task_app_role(user=None):
	"""App-role gate. Does not replace document-level permission checks."""
	user = user or frappe.session.user
	if not user_has_nave_task_app_access(user, frappe.get_roles(user)):
		frappe.throw(
			"You do not have permission to access NAVE Tasks.",
			frappe.PermissionError,
		)


def require_nave_task_access():
	"""Shared guard for all whitelisted NAVE Task APIs (login + app role)."""
	require_login()
	require_nave_task_app_role()


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
	if not employee:
		return None
	if isinstance(employee, dict):
		return employee.get("department")
	return getattr(employee, "department", None)


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


def enrich_timeline_item(row, task=None, *, viewer=None, parent_lookup=None):
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

	viewer = viewer or frappe.session.user
	receipts = parse_seen_receipts(item.get("seen_receipts"))
	seen_by_others = {
		user_id: ts for user_id, ts in receipts.items() if user_id and user_id != sender
	}
	seen_on = None
	if seen_by_others:
		seen_on = sorted(seen_by_others.values())[0]

	parent_update = item.get("parent_update")
	parent_snippet = None
	parent_sender_name = None
	if parent_update and parent_lookup and parent_update in parent_lookup:
		parent_row = parent_lookup[parent_update]
		if hasattr(parent_row, "get"):
			parent_text = parent_row.get("update_text")
			parent_sender = parent_row.get("update_by") or ""
		else:
			parent_text = getattr(parent_row, "update_text", None)
			parent_sender = getattr(parent_row, "update_by", "") or ""
		parent_snippet = to_plain_text(parent_text)
		if len(parent_snippet) > 120:
			parent_snippet = parent_snippet[:117] + "…"
		parent_sender_name = get_user_full_name(parent_sender) if parent_sender else ""

	raw_dt = item.get("updated_on") or item.get("creation")
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
	item["datetime"] = raw_dt
	item["display_time"] = format_conversation_time(raw_dt)
	item["is_mine"] = bool(sender and sender == viewer)
	item["parent_update"] = parent_update
	item["parent_snippet"] = parent_snippet
	item["parent_sender_name"] = parent_sender_name
	item["progress_chip"] = build_progress_chip(
		item.get("update_type"),
		item.get("status"),
		item.get("progress"),
	)
	item["attachment_kind"] = attachment_kind(item.get("attachment"))
	item["seen_by_me"] = viewer in receipts
	item["seen"] = bool(seen_by_others)
	item["seen_on"] = seen_on
	item["seen_display"] = format_conversation_time(seen_on) if seen_on else ""
	item["delivery_state"] = "seen" if seen_by_others else "sent"
	return item


def build_conversation_timeline(rows, task=None, viewer=None):
	"""
	Enrich flat rows into chronological roots with nested replies.
	Newest remains at the bottom (input order must be ascending).
	"""
	viewer = viewer or frappe.session.user
	by_name = {row.get("name"): row for row in rows if row.get("name")}
	enriched = [
		enrich_timeline_item(row, task, viewer=viewer, parent_lookup=by_name) for row in rows
	]
	children = {}
	roots = []
	for item in enriched:
		parent = item.get("parent_update")
		if parent and parent in by_name:
			children.setdefault(parent, []).append(item)
		else:
			# Orphaned parent references still render as roots.
			item["parent_update"] = parent if parent else None
			if parent and parent not in by_name:
				item["parent_snippet"] = item.get("parent_snippet")
			roots.append(item)

	for root in roots:
		root["replies"] = children.get(root.get("name"), [])
	return roots



def serialize_task(task_row):
	# frappe._dict implements __getattr__ so hasattr(..., "as_dict") is True even
	# when the key is missing (returns None). Calling that None crashes All Tasks.
	as_dict = getattr(task_row, "as_dict", None)
	if callable(as_dict):
		row = as_dict()
	elif isinstance(task_row, dict):
		row = dict(task_row)
	else:
		row = dict(task_row)

	payload = {field: row.get(field) for field in TASK_LIST_FIELDS}
	payload["description"] = to_plain_text(payload.get("description"))
	payload["latest_update"] = to_plain_text(payload.get("latest_update"))
	payload["is_overdue"] = cint(payload.get("is_overdue"))
	payload["progress"] = flt(payload.get("progress"))
	assignee = payload.get("assigned_to")
	payload["assigned_to_name"] = get_user_full_name(assignee) if assignee else ""
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
	user = frappe.session.user
	if user == "Guest":
		return False
	return user_has_nave_task_app_access(user, frappe.get_roles(user))


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
	require_nave_task_access()
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
	require_nave_task_access()
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
	require_nave_task_access()
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
	require_nave_task_access()
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
	"""
	One card per task: latest visible update for each permitted task.
	Conversation history stays inside the task detail view.
	"""
	require_nave_task_access()
	page, page_length, start = _parse_page(page, page_length)

	task_filters = _as_filter_list({})
	if task:
		task_filters.append(["name", "=", task])
	# Tasks with recorded activity (latest_update is maintained by conversation APIs).
	task_filters.append(["latest_update", "!=", ""])

	tasks = frappe.get_list(
		"NAVE Task",
		filters=task_filters,
		fields=[
			"name",
			"subject",
			"status",
			"priority",
			"latest_update",
			"modified",
			"assigned_to",
			"assigned_by",
			"owner",
			"department",
			"progress",
		],
		order_by="modified desc",
		limit_start=start,
		limit_page_length=page_length,
		ignore_permissions=False,
	)
	total = _permission_aware_count("NAVE Task", task_filters)

	data = []
	for task_row in tasks:
		task_name = (
			task_row.get("name")
			if isinstance(task_row, dict)
			else getattr(task_row, "name", None)
		)
		task_subject = (
			task_row.get("subject")
			if isinstance(task_row, dict)
			else getattr(task_row, "subject", None)
		)
		task_latest = (
			task_row.get("latest_update")
			if isinstance(task_row, dict)
			else getattr(task_row, "latest_update", None)
		)
		task_modified = (
			task_row.get("modified")
			if isinstance(task_row, dict)
			else getattr(task_row, "modified", None)
		)
		task_status = (
			task_row.get("status")
			if isinstance(task_row, dict)
			else getattr(task_row, "status", None)
		)
		task_progress = (
			task_row.get("progress")
			if isinstance(task_row, dict)
			else getattr(task_row, "progress", None)
		)
		update_filters = {"task": task_name}
		if update_type:
			if update_type == INTERNAL_NOTE_TYPE and not user_can_see_internal_notes():
				frappe.throw(
					"You are not permitted to view Internal Notes.",
					frappe.PermissionError,
				)
			update_filters["update_type"] = update_type
		elif not user_can_see_internal_notes():
			update_filters["update_type"] = ["!=", INTERNAL_NOTE_TYPE]
		if status:
			update_filters["status"] = status
		if update_by:
			update_filters["update_by"] = update_by

		latest_rows = frappe.get_list(
			"NAVE Task Update",
			filters=update_filters,
			fields=_update_list_fields(),
			order_by="updated_on desc, creation desc",
			limit_page_length=1,
			ignore_permissions=False,
		)
		if latest_rows:
			item = enrich_timeline_item(latest_rows[0], task_row)
		else:
			item = {
				"task": task_name,
				"update_text": task_latest,
				"updated_on": task_modified,
				"update_by": None,
				"update_type": "Progress Update",
				"status": task_status,
				"progress": task_progress,
				"attachment": None,
			}
			item = enrich_timeline_item(item, task_row)
		item["task_subject"] = task_subject
		data.append(item)

	return {
		"page": page,
		"page_length": page_length,
		"total": total,
		"data": data,
	}


@frappe.whitelist()
def get_dashboard_counts():
	"""Permission-aware dashboard counters for the current user."""
	require_nave_task_access()
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
	require_nave_task_access()
	task = get_task_for_user(task_name)
	viewer = frappe.session.user

	filters = {"task": task.name}
	if not user_can_see_internal_notes():
		filters["update_type"] = ["!=", INTERNAL_NOTE_TYPE]

	rows = frappe.get_list(
		"NAVE Task Update",
		filters=filters,
		fields=_update_list_fields(),
		order_by="updated_on asc, creation asc",
		limit_page_length=1000,
		ignore_permissions=False,
	)

	# Extra hard filter for Internal Notes (defense in depth).
	flat = []
	for row in rows:
		if row.get("update_type") == INTERNAL_NOTE_TYPE and not user_can_see_internal_notes():
			continue
		flat.append(row)

	timeline = build_conversation_timeline(flat, task, viewer=viewer)
	# Flat enriched list kept for callers that still expect a linear feed.
	timeline_flat = [
		enrich_timeline_item(row, task, viewer=viewer, parent_lookup={r.get("name"): r for r in flat})
		for row in flat
	]

	allowed_types = _allowed_conversation_types_for_user(task, viewer)

	return {
		"task": serialize_task(task),
		"timeline": timeline,
		"timeline_flat": timeline_flat,
		"can_post_internal_note": user_can_see_internal_notes(),
		"allowed_update_types": allowed_types,
		"allowed_next_statuses": get_allowed_next_statuses(
			task.status,
			is_manager_level=session_is_manager_level() and can_manage_task_doc(task),
			can_close=can_manage_task_doc(task) and task.status == "Completed",
		),
		"can_close": can_manage_task_doc(task) and task.status == "Completed",
		"can_reopen": (
			can_manage_task_doc(task)
			and session_is_manager_level()
			and task.status in ("Completed", "Closed")
		),
	}


def _allowed_conversation_types_for_user(task, user=None):
	"""
	Creator and assignee both get Reply / Clarification.
	Progress/Completion stay assignee-or-manager gated (unchanged permission rules).
	"""
	user = user or frappe.session.user
	types = ["Reply", "Clarification Required"]
	if can_submit_progress_on_task(task, user):
		types.extend(["Progress Update", "Completion Update"])
	elif can_manage_task_doc(task, user):
		types.append("Completion Update")
	if is_admin(user) or is_task_director(user) or is_task_manager(user):
		types.append("Manager Instruction")
	if user_can_see_internal_notes(user):
		types.append(INTERNAL_NOTE_TYPE)
	# Preserve CONVERSATION_UPDATE_TYPES order when present.
	ordered = [t for t in CONVERSATION_UPDATE_TYPES if t in types]
	return ordered or types


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
	parent_update=None,
):
	employee = get_employee()
	employee_name = None
	if employee:
		employee_name = (
			employee.get("name")
			if isinstance(employee, dict)
			else getattr(employee, "name", None)
		)
	payload = {
		"doctype": "NAVE Task Update",
		"task": task.name,
		"update_by": frappe.session.user,
		"employee": employee_name,
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
	has_column = getattr(frappe.db, "has_column", None)
	if parent_update and (
		not callable(has_column) or has_column("NAVE Task Update", "parent_update")
	):
		payload["parent_update"] = parent_update
	if not callable(has_column) or has_column("NAVE Task Update", "seen_receipts"):
		payload["seen_receipts"] = dump_seen_receipts({})

	doc = frappe.get_doc(payload)
	doc.insert(ignore_permissions=True)
	return doc


def _apply_task_updates(task, updates, *, touch_modified=True):
	"""Apply field updates via db_set while skipping Document field-change logs."""
	if getattr(task, "flags", None) is not None:
		task.flags.skip_field_change_log = True
	items = list(updates.items())
	if not items:
		return
	for index, (field, value) in enumerate(items):
		is_last = index == len(items) - 1
		task.db_set(
			field,
			value,
			update_modified=touch_modified and is_last,
		)
		if hasattr(task, field):
			setattr(task, field, value)


def _assert_status_transition(task, new_status, user=None):
	user = user or frappe.session.user
	try:
		validate_status_transition(
			task.status,
			new_status,
			is_manager_level=session_is_manager_level(user),
		)
	except ValueError as exc:
		frappe.throw(str(exc), frappe.ValidationError)

	if is_reopen_transition(task.status, new_status) and not can_manage_task_doc(task, user):
		frappe.throw(
			"Only an authorized manager can reopen this task.",
			frappe.PermissionError,
		)


def _status_change_message(old_status, new_status):
	return f"Status changed from {old_status or '—'} to {new_status or '—'}."


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
	require_nave_task_access()
	user = frappe.session.user
	task = get_task_for_user(task_name, user)

	if not can_submit_progress_on_task(task, user):
		frappe.throw(
			"Only the assigned employee or an authorized manager can submit progress updates.",
			frappe.PermissionError,
		)

	_assert_task_not_closed_for_normal_update(task)
	_assert_status_transition(task, status, user)

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

	updates = {
		"status": status,
		"progress": progress,
		"latest_update": update_text.strip(),
		"pending_reason": (pending_reason or "").strip(),
		"is_overdue": compute_is_overdue(task.due_date, status, nowdate()),
	}
	if normalized_support is not None:
		updates["support_required"] = normalized_support

	if is_reopen_transition(previous_status, status):
		updates.update(build_reopen_field_updates())
		updates["progress"] = progress
	elif status == "Completed":
		updates.update(
			build_completion_field_updates(
				existing_completed_on=task.completed_on
				if previous_status == "Completed"
				else None,
				remarks=update_text,
				attachment=attachment,
				now=now_datetime(),
			)
		)

	update = _create_history_entry(
		task,
		update_type="Progress Update",
		update_text=update_text.strip(),
		status=updates["status"],
		progress=updates["progress"],
		pending_reason=pending_reason,
		support_required=updates.get("support_required", task.support_required),
		attachment=attachment,
	)

	_apply_task_updates(task, updates, touch_modified=True)

	if previous_status != updates["status"]:
		_create_history_entry(
			task,
			update_type="Status Change",
			update_text=_status_change_message(previous_status, updates["status"]),
			status=updates["status"],
			progress=updates["progress"],
		)
		notify_status_change(task, previous_status, updates["status"], actor=user)

	return {
		"ok": True,
		"task": task.name,
		"update": update.name,
		"status": updates["status"],
		"progress": updates["progress"],
	}


@frappe.whitelist()
def reply_to_task(task_name, message, attachment=None, parent_update=None):
	return post_task_message(
		task_name=task_name,
		message=message,
		update_type="Reply",
		attachment=attachment,
		parent_update=parent_update,
	)


@frappe.whitelist()
def post_task_message(
	task_name,
	message,
	update_type="Reply",
	attachment=None,
	progress=None,
	status=None,
	parent_update=None,
):
	"""
	Inline conversation composer endpoint.
	Supports Reply / Progress Update / Clarification Required /
	Completion Update / Manager Instruction / Internal Note.
	Optional parent_update creates a threaded reply under that message.
	"""
	require_nave_task_access()
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

	parent_name = (parent_update or "").strip() or None
	if parent_name:
		parent_row = frappe.db.get_value(
			"NAVE Task Update",
			parent_name,
			["name", "task", "update_text", "update_by"],
			as_dict=True,
		)
		if not parent_row or parent_row.task != task.name:
			frappe.throw("Invalid parent message for this task.", frappe.ValidationError)
		# Thread replies stay conversational; force Reply when nesting.
		if update_type not in ("Reply", "Clarification Required", INTERNAL_NOTE_TYPE):
			update_type = "Reply"

	new_status = task.status
	new_progress = flt(task.progress)
	field_updates = {}

	if update_type == "Progress Update":
		if not can_submit_progress_on_task(task, user):
			frappe.throw(
				"Only the assigned employee or an authorized manager can submit progress updates.",
				frappe.PermissionError,
			)
		if status:
			new_status = status
		if progress is not None:
			try:
				new_progress = normalize_progress(new_status, progress)
			except ValueError as exc:
				frappe.throw(str(exc))
		if new_status != task.status:
			_assert_status_transition(task, new_status, user)
		if is_reopen_transition(task.status, new_status):
			field_updates.update(build_reopen_field_updates())
			field_updates["progress"] = new_progress
		elif new_status == "Completed" and task.status != "Completed":
			field_updates.update(
				build_completion_field_updates(
					existing_completed_on=None,
					remarks=message,
					attachment=attachment,
					now=now_datetime(),
				)
			)
			new_progress = 100
		else:
			field_updates["status"] = new_status
			field_updates["progress"] = new_progress
	elif update_type == "Completion Update":
		if not can_submit_progress_on_task(task, user) and not can_manage_task_doc(task, user):
			frappe.throw(
				"You are not permitted to post a Completion Update on this task.",
				frappe.PermissionError,
			)
		_assert_status_transition(task, "Completed", user)
		field_updates.update(
			build_completion_field_updates(
				existing_completed_on=task.completed_on if task.status == "Completed" else None,
				remarks=message,
				attachment=attachment,
				now=now_datetime(),
			)
		)
		new_status = "Completed"
		new_progress = 100

	previous_status = task.status
	update = _create_history_entry(
		task,
		update_type=update_type,
		update_text=message.strip(),
		status=field_updates.get("status", new_status),
		progress=field_updates.get("progress", new_progress),
		attachment=attachment,
		parent_update=parent_name,
	)

	if field_updates:
		field_updates["is_overdue"] = compute_is_overdue(
			task.due_date,
			field_updates.get("status", new_status),
			nowdate(),
		)
		if update_type != INTERNAL_NOTE_TYPE:
			field_updates["latest_update"] = message.strip()
		_apply_task_updates(task, field_updates, touch_modified=True)
		if previous_status != field_updates.get("status", previous_status):
			_create_history_entry(
				task,
				update_type="Status Change",
				update_text=_status_change_message(
					previous_status,
					field_updates.get("status"),
				),
				status=field_updates.get("status"),
				progress=field_updates.get("progress", new_progress),
			)
			notify_status_change(
				task,
				previous_status,
				field_updates.get("status"),
				actor=user,
			)
			status_notified = True
		else:
			status_notified = False
	else:
		status_notified = False
		if update_type != INTERNAL_NOTE_TYPE:
			task.db_set("latest_update", message.strip(), update_modified=True)

	# In-app + email for conversation messages (Reply / Progress / etc.).
	# Status transitions already notify above; avoid a second ping for those.
	if update_type not in (INTERNAL_NOTE_TYPE, "System") and not status_notified:
		notify_nave_task_event(task, EVENT_MESSAGE, actor=user)

	final_status = field_updates.get("status", new_status)
	final_progress = field_updates.get("progress", new_progress)

	parent_lookup = {}
	if parent_name:
		parent_lookup[parent_name] = parent_row

	return {
		"ok": True,
		"task": task.name,
		"update": getattr(update, "name", None),
		"update_type": update_type,
		"parent_update": parent_name,
		"timeline_item": enrich_timeline_item(
			{
				"name": getattr(update, "name", None),
				"task": task.name,
				"update_by": getattr(update, "update_by", user),
				"employee": getattr(update, "employee", None),
				"updated_on": getattr(update, "updated_on", None),
				"update_type": getattr(update, "update_type", update_type),
				"status": getattr(update, "status", final_status),
				"progress": getattr(update, "progress", final_progress),
				"update_text": getattr(update, "update_text", message.strip()),
				"pending_reason": getattr(update, "pending_reason", None),
				"support_required": getattr(update, "support_required", None),
				"attachment": getattr(update, "attachment", attachment),
				"creation": getattr(update, "creation", None),
				"parent_update": parent_name,
				"seen_receipts": getattr(update, "seen_receipts", "{}"),
			},
			task,
			viewer=user,
			parent_lookup=parent_lookup,
		),
	}


@frappe.whitelist()
def mark_timeline_seen(task_name, update_names=None):
	"""
	Mark conversation messages as seen by the current user.
	Stores per-user seen timestamps on NAVE Task Update.seen_receipts.
	"""
	require_nave_task_access()
	user = frappe.session.user
	task = get_task_for_user(task_name, user)

	has_column = getattr(frappe.db, "has_column", None)
	if callable(has_column) and not has_column("NAVE Task Update", "seen_receipts"):
		return {"ok": True, "marked": 0, "skipped": "column_missing"}

	names = update_names
	if isinstance(names, str):
		try:
			names = frappe.parse_json(names)
		except Exception:
			names = [names] if names else None
	if not names:
		filters = {"task": task.name, "update_by": ["!=", user]}
		if not user_can_see_internal_notes():
			filters["update_type"] = ["!=", INTERNAL_NOTE_TYPE]
		names = frappe.get_list(
			"NAVE Task Update",
			filters=filters,
			pluck="name",
			limit_page_length=1000,
			ignore_permissions=False,
		)

	now = str(now_datetime())
	marked = 0
	for name in names or []:
		row = frappe.db.get_value(
			"NAVE Task Update",
			name,
			["name", "task", "update_by", "seen_receipts"],
			as_dict=True,
		)
		if not row or row.task != task.name:
			continue
		if row.update_by == user:
			continue
		receipts = parse_seen_receipts(row.seen_receipts)
		if user in receipts:
			continue
		receipts[user] = now
		frappe.db.set_value(
			"NAVE Task Update",
			name,
			"seen_receipts",
			dump_seen_receipts(receipts),
			update_modified=False,
		)
		marked += 1

	return {"ok": True, "marked": marked, "seen_on": now}


def _employee_profile(user):
	if not user:
		return None
	return frappe.db.get_value(
		"Employee",
		{"user_id": user, "status": "Active"},
		["name", "department", "company", "employee_name"],
		as_dict=True,
	)


def _emp_attr(emp, field):
	"""Read a field from Employee as_dict / _dict / object mocks."""
	if not emp:
		return None
	if isinstance(emp, dict):
		return emp.get(field)
	return getattr(emp, field, None)


def _assert_assignable_office_user(assignee, *, actor, actor_is_elevated, actor_is_manager, actor_department, actor_company):
	"""
	Server-side assignee validation for create/reassign-style assignment.
	Never trust the client for these checks.
	"""
	assignee = (assignee or "").strip()
	if not assignee:
		frappe.throw("Assign To is required.", frappe.ValidationError)

	user_row = frappe.db.get_value(
		"User",
		assignee,
		["name", "enabled", "user_type"],
		as_dict=True,
	)
	if not user_row:
		frappe.throw("Assigned user does not exist.", frappe.ValidationError)
	if not cint(_emp_attr(user_row, "enabled")):
		frappe.throw("Cannot assign tasks to a disabled user.", frappe.ValidationError)
	user_type = _emp_attr(user_row, "user_type")
	if user_type and user_type != "System User":
		frappe.throw("Can only assign tasks to office staff users.", frappe.ValidationError)

	roles = frappe.get_roles(assignee)
	if not user_has_nave_task_app_access(assignee, roles):
		frappe.throw(
			"Can only assign tasks to authorized office staff.",
			frappe.PermissionError,
		)

	assignee_emp = _employee_profile(assignee)
	assignee_department = _emp_attr(assignee_emp, "department")
	assignee_company = _emp_attr(assignee_emp, "company")

	if (
		not actor_is_elevated
		and actor_company
		and assignee_company
		and actor_company != assignee_company
	):
		frappe.throw(
			"Cannot assign tasks across companies.",
			frappe.PermissionError,
		)

	if is_restricted_department(assignee_department) and not actor_is_elevated:
		# Managers may assign within their own restricted department only.
		if not (
			actor_is_manager
			and actor_department
			and assignee_department
			and actor_department == assignee_department
		):
			frappe.throw(
				"You are not permitted to assign tasks in this restricted department.",
				frappe.PermissionError,
			)

	return {
		"user": assignee,
		"employee": assignee_emp,
		"department": assignee_department,
		"company": assignee_company,
	}


@frappe.whitelist()
def create_task(
	subject,
	assigned_to,
	priority,
	due_date,
	description=None,
	project=None,
	department=None,
	attachment=None,
	company=None,
):
	"""
	Create a NAVE Task from the dashboard for authorized office staff.
	Validates assignee and department rules on the server.
	"""
	require_nave_task_access()
	actor = frappe.session.user

	subject = (subject or "").strip()
	assigned_to = (assigned_to or "").strip()
	priority = (priority or "").strip()
	due_date = (due_date or "").strip()
	description = to_plain_text(description).strip() if description else ""
	project = (project or "").strip() or None
	department = (department or "").strip() or None
	attachment = (attachment or "").strip() or None
	company = (company or "").strip() or None

	if not subject:
		frappe.throw("Task Title is required.", frappe.ValidationError)
	if not assigned_to:
		frappe.throw("Assign To is required.", frappe.ValidationError)
	if not priority:
		frappe.throw("Priority is required.", frappe.ValidationError)
	if priority not in ("Low", "Medium", "High", "Urgent"):
		frappe.throw("Invalid priority.", frappe.ValidationError)
	if not due_date:
		frappe.throw("Due Date is required.", frappe.ValidationError)
	if not description:
		description = "-"

	actor_emp = _employee_profile(actor)
	actor_department = _emp_attr(actor_emp, "department")
	actor_company = _emp_attr(actor_emp, "company")
	actor_is_elevated = is_admin(actor) or is_task_director(actor)
	actor_is_manager = is_task_manager(actor)

	assignee_info = _assert_assignable_office_user(
		assigned_to,
		actor=actor,
		actor_is_elevated=actor_is_elevated,
		actor_is_manager=actor_is_manager,
		actor_department=actor_department,
		actor_company=actor_company,
	)

	# Explicit department override must also honor restricted-department rules.
	if department:
		if is_restricted_department(department) and not actor_is_elevated:
			if not (
				actor_is_manager
				and actor_department
				and actor_department == department
			):
				frappe.throw(
					"You are not permitted to create tasks for this restricted department.",
					frappe.PermissionError,
				)
	else:
		department = assignee_info.get("department")

	if not company:
		company = assignee_info.get("company") or actor_company
	if not company:
		# Last resort for Administrator / users without Employee records.
		company = frappe.db.get_single_value("Global Defaults", "default_company")
	if not company:
		frappe.throw(
			"Company could not be determined for this task. Set the assignee Employee company.",
			frappe.ValidationError,
		)

	if project:
		project_company = frappe.db.get_value("Project", project, "company")
		if project_company and project_company != company:
			frappe.throw(
				"Project belongs to a different company.",
				frappe.PermissionError,
			)

	payload = {
		"doctype": "NAVE Task",
		"subject": subject,
		"description": description,
		"assigned_to": assigned_to,
		"assigned_by": actor,
		"priority": priority,
		"due_date": due_date,
		"status": "Open",
		"progress": 0,
		"department": department,
		"company": company,
		"project": project,
		"start_date": nowdate(),
	}

	# Optional task-level attachment column (present after migrate).
	has_column = getattr(frappe.db, "has_column", None)
	if attachment and (
		not callable(has_column) or has_column("NAVE Task", "attachment")
	):
		payload["attachment"] = attachment

	# Employees lack DocType create; API validates then inserts with ignore_permissions.
	doc = frappe.get_doc(payload)
	doc.insert(ignore_permissions=True)

	# Ensure assignment notification (in-app + email). Deduped if after_insert already fired.
	notify_nave_task_event(doc, EVENT_ASSIGNED, actor=actor)

	# Keep attachment on the conversation timeline even without a task-level field.
	if attachment:
		_create_history_entry(
			doc,
			update_type="System",
			update_text="Attachment added at task creation.",
			status=doc.status,
			progress=doc.progress,
			attachment=attachment,
		)

	_create_history_entry(
		doc,
		update_type="System",
		update_text=f"Task created by {get_user_full_name(actor)}.",
		status=doc.status,
		progress=doc.progress,
	)

	return {
		"ok": True,
		"task": doc.name,
		"subject": doc.subject,
		"assigned_to": doc.assigned_to,
		"task_row": serialize_task(doc),
	}


@frappe.whitelist()
def reassign_task(task_name, assigned_to, note=None):
	require_nave_task_access()
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

	actor_emp = _employee_profile(user)
	_assert_assignable_office_user(
		assigned_to,
		actor=user,
		actor_is_elevated=is_admin(user) or is_task_director(user),
		actor_is_manager=is_task_manager(user),
		actor_department=_emp_attr(actor_emp, "department"),
		actor_company=_emp_attr(actor_emp, "company"),
	)

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
	notify_nave_task_event(
		task,
		EVENT_REASSIGNED,
		actor=user,
		previous_assignee=previous_assignee,
	)

	return {
		"ok": True,
		"task": task.name,
		"update": update.name,
		"assigned_to": assigned_to,
		"previous_assignee": previous_assignee,
	}


@frappe.whitelist()
def close_task(task_name, remarks=None):
	require_nave_task_access()
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

	_assert_status_transition(task, "Closed", user)

	previous_status = task.status
	remarks_text = (remarks or "").strip() or f"Task closed (was {previous_status})."

	_apply_task_updates(
		task,
		{
			"status": "Closed",
			"is_overdue": compute_is_overdue(task.due_date, "Closed", nowdate()),
			"latest_update": remarks_text,
		},
		touch_modified=True,
	)

	update = _create_history_entry(
		task,
		update_type="Close",
		update_text=remarks_text,
		status="Closed",
		progress=task.progress,
	)
	notify_status_change(task, previous_status, "Closed", actor=user)

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
	"""Combined daily job: overdue refresh + recurring generation + reminders + escalation.

	Order: assignee due/overdue reminders, then manager/director escalation milestones.
	Wall-clock time follows the Frappe daily scheduler (not a fixed 09:00 slot).
	"""
	overdue = refresh_overdue_flags()
	from project_custom.nave_task_generation import generate_due_recurring_tasks
	from project_custom.nave_task_escalation import send_nave_task_escalations
	from project_custom.nave_task_reminders import send_nave_task_due_reminders

	recurrence = generate_due_recurring_tasks()
	reminders = send_nave_task_due_reminders()
	escalations = send_nave_task_escalations()
	return {
		"ok": True,
		"overdue": overdue,
		"recurrence": recurrence,
		"reminders": reminders,
		"escalations": escalations,
	}


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
	require_nave_task_access()
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
	require_nave_task_access()
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
	require_nave_task_access()
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
	require_nave_task_access()
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
	require_nave_task_access()
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
