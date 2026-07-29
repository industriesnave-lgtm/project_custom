"""Scheduler-safe recurring NAVE Task generation."""

from __future__ import annotations

import frappe
from frappe.utils import cint, getdate, now_datetime, nowdate

from project_custom.nave_task_recurrence import (
	_as_date,
	build_generated_subject,
	calculate_due_date,
	next_occurrence_date,
	should_stop_recurrence,
)


TEMPLATE_COPY_FIELDS = (
	"description",
	"category",
	"priority",
	"assigned_to",
	"assigned_employee",
	"department",
	"company",
	"project",
	"site",
)


def _log(message: str):
	frappe.logger("nave_tasks_recurrence").info(message)


def occurrence_already_generated(template_name: str, occurrence_date) -> bool:
	occurrence = _as_date(occurrence_date)
	if not occurrence:
		return False
	return bool(
		frappe.db.exists(
			"NAVE Task",
			{
				"generated_from": template_name,
				"recurrence_occurrence_date": occurrence.isoformat(),
			},
		)
	)


def next_sequence_for_template(template_name: str) -> int:
	current = frappe.db.sql(
		"""
		SELECT COALESCE(MAX(recurrence_sequence), 0)
		FROM `tabNAVE Task`
		WHERE generated_from = %s
		""",
		template_name,
	)[0][0]
	return cint(current) + 1


def _create_recurrence_history(task_name: str, text: str, status: str = "Open", progress=0):
	"""Permanent history entry; caller must already have permission/context."""
	employee = frappe.db.get_value(
		"Employee",
		{"user_id": frappe.session.user, "status": "Active"},
		"name",
	)
	doc = frappe.get_doc(
		{
			"doctype": "NAVE Task Update",
			"task": task_name,
			"update_by": frappe.session.user if frappe.session.user != "Guest" else "Administrator",
			"employee": employee,
			"updated_on": now_datetime(),
			"update_type": "Recurrence Event",
			"status": status,
			"progress": progress or 0,
			"update_text": text,
		}
	)
	doc.insert(ignore_permissions=True)
	return doc


def create_generated_task(template, occurrence_date, *, source: str = "scheduler"):
	"""
	Create one generated instance for a template occurrence.
	Idempotent: returns existing task name if occurrence already exists.
	"""
	occurrence = _as_date(occurrence_date)
	if not occurrence:
		frappe.throw("Invalid occurrence date.")

	if occurrence_already_generated(template.name, occurrence):
		existing = frappe.db.get_value(
			"NAVE Task",
			{
				"generated_from": template.name,
				"recurrence_occurrence_date": occurrence.isoformat(),
			},
			"name",
		)
		return {"ok": True, "created": False, "task": existing, "duplicate": True}

	if should_stop_recurrence(
		is_recurring=template.is_recurring,
		recurrence_active=template.recurrence_active,
		status=template.status,
		recurrence_end_date=template.recurrence_end_date,
		occurrence=occurrence,
	):
		return {"ok": False, "created": False, "stopped": True}

	sequence = next_sequence_for_template(template.name)
	due_date = calculate_due_date(occurrence, template.recurrence_due_after_days)

	payload = {
		"doctype": "NAVE Task",
		"subject": build_generated_subject(template.subject, occurrence, sequence),
		"status": "Open",
		"progress": 0,
		"is_overdue": 0,
		"is_recurring": 0,
		"recurrence_active": 0,
		"start_date": occurrence.isoformat(),
		"due_date": due_date.isoformat(),
		"generated_from": template.name,
		"recurring_template": template.name,
		"recurrence_sequence": sequence,
		"recurrence_occurrence_date": occurrence.isoformat(),
		"assigned_by": template.assigned_by or template.owner,
		"owner": template.owner,
	}
	for field in TEMPLATE_COPY_FIELDS:
		payload[field] = template.get(field)

	# Insert as system/job context while preserving original creator on owner/assigned_by.
	generated = frappe.get_doc(payload)
	generated.flags.ignore_permissions = True
	generated.insert(ignore_permissions=True)

	# Ensure owner remains the template creator for creator-visibility rules.
	if template.owner and generated.owner != template.owner:
		frappe.db.set_value(
			"NAVE Task",
			generated.name,
			"owner",
			template.owner,
			update_modified=False,
		)

	_create_recurrence_history(
		generated.name,
		f"Generated from recurring template {template.name} for {occurrence.isoformat()} ({source}).",
		status="Open",
		progress=0,
	)
	_create_recurrence_history(
		template.name,
		f"Recurring task generated: {generated.name} for {occurrence.isoformat()} ({source}).",
		status=template.status,
		progress=template.progress,
	)

	return {
		"ok": True,
		"created": True,
		"task": generated.name,
		"occurrence_date": occurrence.isoformat(),
		"sequence": sequence,
	}


def advance_template_after_generation(template, occurrence_date):
	occurrence = _as_date(occurrence_date)
	frequency = template.recurrence_frequency
	nxt = next_occurrence_date(frequency, occurrence)

	end = _as_date(template.recurrence_end_date)
	updates = {
		"last_generated_date": occurrence.isoformat(),
		"next_creation_date": nxt.isoformat(),
	}

	if end and nxt > end:
		updates["recurrence_active"] = 0
		_create_recurrence_history(
			template.name,
			f"Recurrence ended after {occurrence.isoformat()} (end date {end.isoformat()}).",
			status=template.status,
			progress=template.progress,
		)

	for field, value in updates.items():
		frappe.db.set_value("NAVE Task", template.name, field, value, update_modified=False)

	return updates


def process_template(template_name: str, *, today=None, force_occurrence=None, source="scheduler"):
	"""
	Generate all due occurrences for one template up to today (inclusive).
	force_occurrence: generate exactly one occurrence date (Generate Now).
	"""
	template = frappe.get_doc("NAVE Task", template_name)
	today_date = _as_date(today) or _as_date(nowdate())
	created = []
	skipped = []

	if force_occurrence:
		occurrence = _as_date(force_occurrence)
		result = create_generated_task(template, occurrence, source=source)
		if result.get("created"):
			advance_template_after_generation(template, occurrence)
			created.append(result)
		else:
			skipped.append(result)
		return {"template": template_name, "created": created, "skipped": skipped}

	if should_stop_recurrence(
		is_recurring=template.is_recurring,
		recurrence_active=template.recurrence_active,
		status=template.status,
		recurrence_end_date=template.recurrence_end_date,
		occurrence=today_date,
	):
		return {"template": template_name, "created": [], "skipped": [{"stopped": True}]}

	cursor = _as_date(template.next_creation_date) or _as_date(template.recurrence_start_date)
	if not cursor:
		return {"template": template_name, "created": [], "skipped": [{"missing_next": True}]}

	# Guard against runaway loops.
	safety = 0
	while cursor <= today_date and safety < 366:
		safety += 1
		if should_stop_recurrence(
			is_recurring=template.is_recurring,
			recurrence_active=template.recurrence_active,
			status=template.status,
			recurrence_end_date=template.recurrence_end_date,
			occurrence=cursor,
		):
			break

		result = create_generated_task(template, cursor, source=source)
		if result.get("created"):
			created.append(result)
		else:
			skipped.append(result)

		updates = advance_template_after_generation(template, cursor)
		template.next_creation_date = updates.get("next_creation_date")
		template.last_generated_date = updates.get("last_generated_date")
		if "recurrence_active" in updates:
			template.recurrence_active = updates["recurrence_active"]
			break

		cursor = _as_date(template.next_creation_date)
		if not cursor:
			break

	return {"template": template_name, "created": created, "skipped": skipped}


def generate_due_recurring_tasks(today=None):
	"""Daily scheduler entry: process all active recurring templates independently."""
	today_date = _as_date(today) or _as_date(nowdate())
	templates = frappe.get_all(
		"NAVE Task",
		filters={
			"is_recurring": 1,
			"recurrence_active": 1,
			"status": ["not in", ["Closed", "Cancelled"]],
			"next_creation_date": ["<=", today_date.isoformat()],
		},
		pluck="name",
		limit_page_length=5000,
	)

	summary = {"checked": len(templates), "created": 0, "errors": [], "results": []}
	for name in templates:
		try:
			result = process_template(name, today=today_date, source="scheduler")
			summary["created"] += len(result.get("created") or [])
			summary["results"].append(result)
		except Exception:
			frappe.log_error(
				title=f"NAVE Tasks recurrence failed for {name}",
				message=frappe.get_traceback(),
			)
			summary["errors"].append(name)
			_log(f"Failed recurring generation for {name}")

	_log(
		f"Recurrence run complete. templates={summary['checked']} "
		f"created={summary['created']} errors={len(summary['errors'])}"
	)
	return summary
