# Copyright (c) 2026, Nave Industries and contributors
# License: MIT. See LICENSE
"""
Persistent alert-cycle engine for project-wise unbilled expense (V1).

Reuses Step 3 calculation snapshots. No email or in-app notify in this module.
"""

from __future__ import annotations

from typing import Any

import frappe
from frappe.utils import cint, flt, getdate, now_datetime, nowdate

from project_custom.project_unbilled_alert import (
	DEFAULT_THRESHOLD,
	get_all_projects_for_evaluation,
	get_project_unbilled_snapshot,
)

ALERT_DOCTYPE = "NAVE Project Unbilled Alert"
SETTINGS_DOCTYPE = "NAVE Project Unbilled Alert Settings"
ACTIVE_ALERT_STATUSES = ("Pending", "Alerted")
DEFAULT_AGEING_DAYS = 5


def load_unbilled_alert_settings() -> dict[str, Any]:
	"""Load settings once per batch. Safe defaults if Single is missing."""
	try:
		doc = frappe.get_single(SETTINGS_DOCTYPE)
	except Exception:
		return {
			"enabled": 0,
			"threshold_amount": DEFAULT_THRESHOLD,
			"ageing_days": DEFAULT_AGEING_DAYS,
			"director_emails": "",
			"send_email": 0,
			"create_in_app_notification": 0,
		}

	return {
		"enabled": cint(doc.get("enabled")),
		"threshold_amount": flt(
			doc.get("threshold_amount")
			if doc.get("threshold_amount") not in (None, "")
			else DEFAULT_THRESHOLD
		),
		"ageing_days": cint(doc.get("ageing_days") or DEFAULT_AGEING_DAYS),
		"director_emails": doc.get("director_emails") or "",
		"send_email": cint(doc.get("send_email")),
		"create_in_app_notification": cint(doc.get("create_in_app_notification")),
	}


def calculate_ageing_days(threshold_crossed_on, today=None) -> int | None:
	"""Calendar-day age: crossed date = day 0, next calendar day = day 1."""
	if threshold_crossed_on in (None, ""):
		return None
	crossed = getdate(threshold_crossed_on)
	as_of = getdate(today or nowdate())
	return (as_of - crossed).days


def is_cycle_alert_eligible(cycle, today=None, ageing_threshold: int | None = None) -> bool:
	"""
	Eligibility for Director alert (Step 5 will send).
	Does not send anything.
	"""
	if not cycle:
		return False

	status = cycle.get("alert_status") if isinstance(cycle, dict) else cycle.alert_status
	alert_sent = cint(
		cycle.get("alert_sent") if isinstance(cycle, dict) else cycle.alert_sent
	)
	unbilled = flt(
		cycle.get("current_unbilled_amount")
		if isinstance(cycle, dict)
		else cycle.current_unbilled_amount
	)
	threshold = flt(
		cycle.get("threshold_amount")
		if isinstance(cycle, dict)
		else cycle.threshold_amount
	)
	crossed_on = (
		cycle.get("threshold_crossed_on")
		if isinstance(cycle, dict)
		else cycle.threshold_crossed_on
	)

	if status != "Pending":
		return False
	if alert_sent:
		return False
	if unbilled <= threshold:
		return False

	if ageing_threshold is None:
		ageing_threshold = DEFAULT_AGEING_DAYS
		try:
			ageing_threshold = cint(
				frappe.db.get_single_value(SETTINGS_DOCTYPE, "ageing_days")
				or DEFAULT_AGEING_DAYS
			)
		except Exception:
			pass

	age = calculate_ageing_days(crossed_on, today=today)
	if age is None:
		return False
	return age >= cint(ageing_threshold)


def get_active_cycle(project: str, company: str) -> dict[str, Any] | None:
	"""DB-authoritative active cycle: Pending/Alerted and unresolved."""
	if not project or not company:
		return None

	rows = frappe.db.sql(
		"""
		SELECT
			name, project, company, customer, cycle_no,
			current_expense_amount, current_billed_amount, current_unbilled_amount,
			threshold_amount, threshold_crossed_on, ageing_days,
			last_sales_invoice_date, project_status, alert_status,
			alert_sent, alert_sent_on, resolved_on, last_evaluated_on, skip_reason
		FROM `tabNAVE Project Unbilled Alert`
		WHERE project = %s
			AND company = %s
			AND alert_status IN ('Pending', 'Alerted')
			AND IFNULL(resolved_on, '') = ''
		ORDER BY cycle_no DESC
		LIMIT 1
		""",
		(project, company),
		as_dict=True,
	)
	return rows[0] if rows else None


def get_next_cycle_no(project: str, company: str) -> int:
	row = frappe.db.sql(
		"""
		SELECT COALESCE(MAX(cycle_no), 0)
		FROM `tabNAVE Project Unbilled Alert`
		WHERE project = %s AND company = %s
		""",
		(project, company),
	)
	return cint(row[0][0] if row else 0) + 1


def _empty_summary() -> dict[str, Any]:
	return {
		"evaluated": 0,
		"opened": 0,
		"refreshed": 0,
		"resolved": 0,
		"eligible_for_alert": 0,
		"alerts_sent": 0,
		"skipped": 0,
		"errors": [],
		"noop": 0,
	}


def _apply_snapshot_amounts(doc, snapshot: dict[str, Any], settings: dict[str, Any], today=None):
	"""Shared field updates for open / refresh / resolve current values."""
	doc.customer = snapshot.get("customer")
	doc.project_status = snapshot.get("project_status")
	doc.current_expense_amount = flt(snapshot.get("expense_amount"))
	doc.current_billed_amount = flt(snapshot.get("billed_amount"))
	doc.current_unbilled_amount = flt(snapshot.get("unbilled_amount"))
	doc.threshold_amount = flt(settings.get("threshold_amount") or DEFAULT_THRESHOLD)
	doc.last_sales_invoice_date = snapshot.get("last_sales_invoice_date")
	doc.last_evaluated_on = now_datetime()
	doc.ageing_days = calculate_ageing_days(doc.threshold_crossed_on, today=today)


def refresh_cycle(
	cycle_name: str,
	snapshot: dict[str, Any],
	settings: dict[str, Any],
	*,
	today=None,
) -> dict[str, Any]:
	"""Refresh amounts on an active cycle; preserve alert_sent / cycle_no."""
	doc = frappe.get_doc(ALERT_DOCTYPE, cycle_name)

	# Ledger-derived crossed date may move with backdated txs.
	crossed = snapshot.get("threshold_crossed_on")
	if crossed:
		doc.threshold_crossed_on = crossed

	_apply_snapshot_amounts(doc, snapshot, settings, today=today)
	doc.skip_reason = None
	doc.save()
	return doc.as_dict()


def resolve_cycle(
	cycle_name: str,
	snapshot: dict[str, Any],
	settings: dict[str, Any],
	*,
	today=None,
) -> dict[str, Any]:
	"""Mark cycle Resolved; preserve crossed date and alert_sent history."""
	doc = frappe.get_doc(ALERT_DOCTYPE, cycle_name)
	# Do not clear historical threshold_crossed_on when falling below threshold.
	_apply_snapshot_amounts(doc, snapshot, settings, today=today)
	doc.alert_status = "Resolved"
	doc.resolved_on = now_datetime()
	doc.skip_reason = None
	doc.save()
	return doc.as_dict()


def open_cycle(
	snapshot: dict[str, Any],
	settings: dict[str, Any],
	*,
	today=None,
) -> dict[str, Any]:
	"""
	Create a Pending cycle with DB recheck to avoid duplicates.
	Does not invent threshold_crossed_on when ledger returns None.
	"""
	project = snapshot["project"]
	company = snapshot["company"]
	crossed = snapshot.get("threshold_crossed_on")
	if not crossed:
		frappe.log_error(
			title="NAVE Unbilled Alert: missing threshold_crossed_on",
			message=(
				f"Project {project} unbilled={snapshot.get('unbilled_amount')} "
				f"> threshold but ledger returned no threshold_crossed_on."
			),
		)
		return {
			"action": "error",
			"project": project,
			"company": company,
			"error": "missing_threshold_crossed_on",
			"message": (
				"Unbilled above threshold but threshold_crossed_on is missing; "
				"cycle not created."
			),
		}

	# Recheck immediately before insert (idempotency / concurrency).
	existing = get_active_cycle(project, company)
	if existing:
		refreshed = refresh_cycle(existing.get("name"), snapshot, settings, today=today)
		return {
			"action": "refreshed",
			"project": project,
			"company": company,
			"cycle": refreshed.get("name"),
			"cycle_no": refreshed.get("cycle_no"),
			"reason": "active_cycle_exists_on_recheck",
		}

	cycle_no = get_next_cycle_no(project, company)
	doc = frappe.get_doc(
		{
			"doctype": ALERT_DOCTYPE,
			"project": project,
			"company": company,
			"customer": snapshot.get("customer"),
			"cycle_no": cycle_no,
			"project_status": snapshot.get("project_status"),
			"alert_status": "Pending",
			"alert_sent": 0,
			"alert_sent_on": None,
			"resolved_on": None,
			"threshold_crossed_on": crossed,
			"threshold_amount": flt(settings.get("threshold_amount") or DEFAULT_THRESHOLD),
			"current_expense_amount": flt(snapshot.get("expense_amount")),
			"current_billed_amount": flt(snapshot.get("billed_amount")),
			"current_unbilled_amount": flt(snapshot.get("unbilled_amount")),
			"last_sales_invoice_date": snapshot.get("last_sales_invoice_date"),
			"last_evaluated_on": now_datetime(),
			"ageing_days": calculate_ageing_days(crossed, today=today),
		}
	)

	try:
		doc.insert()
	except Exception as exc:
		# Duplicate active-cycle race: recover by refreshing the winner.
		existing = get_active_cycle(project, company)
		if existing:
			refreshed = refresh_cycle(existing.get("name"), snapshot, settings, today=today)
			return {
				"action": "refreshed",
				"project": project,
				"company": company,
				"cycle": refreshed.get("name"),
				"cycle_no": refreshed.get("cycle_no"),
				"reason": "duplicate_insert_race_recovered",
				"error_detail": str(exc),
			}
		frappe.log_error(
			title="NAVE Unbilled Alert: open_cycle failed",
			message=f"Project {project}: {exc}",
		)
		return {
			"action": "error",
			"project": project,
			"company": company,
			"error": "open_cycle_failed",
			"message": str(exc),
		}

	return {
		"action": "opened",
		"project": project,
		"company": company,
		"cycle": doc.name,
		"cycle_no": doc.cycle_no,
	}


def evaluate_project_unbilled_alert(
	project: str,
	settings: dict[str, Any] | None = None,
	*,
	today=None,
) -> dict[str, Any]:
	"""
	Evaluate one project and open / refresh / resolve cycles.
	Callable even when settings.enabled is false (for tests / manual runs).
	"""
	settings = settings or load_unbilled_alert_settings()
	threshold = flt(settings.get("threshold_amount") or DEFAULT_THRESHOLD)
	snapshot = get_project_unbilled_snapshot(project, threshold=threshold)
	company = snapshot.get("company")
	active = get_active_cycle(project, company) if company else None

	result = {
		"project": project,
		"company": company,
		"action": "noop",
		"skipped": False,
		"eligible_for_alert": False,
		"snapshot": {
			"unbilled_amount": snapshot.get("unbilled_amount"),
			"threshold_amount": threshold,
			"threshold_crossed_on": snapshot.get("threshold_crossed_on"),
			"currency": snapshot.get("currency"),
			"skipped": snapshot.get("skipped"),
			"skip_reason": snapshot.get("skip_reason"),
		},
	}

	if snapshot.get("skipped"):
		result["action"] = "skipped"
		result["skipped"] = True
		result["skip_reason"] = snapshot.get("skip_reason")
		# Do not silently resolve active cycles for non-INR / bad currency data.
		if active:
			result["active_cycle"] = active.get("name")
			result["note"] = "active_cycle_left_untouched_due_to_skip"
		return result

	unbilled = flt(snapshot.get("unbilled_amount"))

	if unbilled <= threshold:
		if not active:
			result["action"] = "noop"
			return result
		resolved = resolve_cycle(active.get("name"), snapshot, settings, today=today)
		result["action"] = "resolved"
		result["cycle"] = resolved.get("name")
		result["cycle_no"] = resolved.get("cycle_no")
		return result

	# Above threshold
	if not active:
		opened = open_cycle(snapshot, settings, today=today)
		result.update(opened)
		if opened.get("action") == "opened":
			cycle_dict = {
				"alert_status": "Pending",
				"alert_sent": 0,
				"current_unbilled_amount": unbilled,
				"threshold_amount": threshold,
				"threshold_crossed_on": snapshot.get("threshold_crossed_on"),
			}
			result["eligible_for_alert"] = is_cycle_alert_eligible(
				cycle_dict,
				today=today,
				ageing_threshold=settings.get("ageing_days"),
			)
		elif opened.get("action") == "refreshed":
			active2 = get_active_cycle(project, company)
			if active2:
				result["eligible_for_alert"] = is_cycle_alert_eligible(
					active2,
					today=today,
					ageing_threshold=settings.get("ageing_days"),
				)
		return result

	refreshed = refresh_cycle(active.get("name"), snapshot, settings, today=today)
	result["action"] = "refreshed"
	result["cycle"] = refreshed.get("name")
	result["cycle_no"] = refreshed.get("cycle_no")
	result["eligible_for_alert"] = is_cycle_alert_eligible(
		refreshed,
		today=today,
		ageing_threshold=settings.get("ageing_days"),
	)
	return result


def evaluate_all_project_unbilled_alerts(
	settings: dict[str, Any] | None = None,
	*,
	today=None,
) -> dict[str, Any]:
	"""Evaluate every Project. One failure does not abort the batch."""
	settings = settings or load_unbilled_alert_settings()
	summary = _empty_summary()
	projects = get_all_projects_for_evaluation()

	for row in projects or []:
		name = row.get("name") if isinstance(row, dict) else row
		try:
			outcome = evaluate_project_unbilled_alert(name, settings=settings, today=today)
			summary["evaluated"] += 1
			action = outcome.get("action")
			if action == "opened":
				summary["opened"] += 1
			elif action == "refreshed":
				summary["refreshed"] += 1
			elif action == "resolved":
				summary["resolved"] += 1
			elif action == "skipped":
				summary["skipped"] += 1
			elif action == "noop":
				summary["noop"] += 1
			elif action == "error":
				summary["errors"].append(
					{
						"project": name,
						"error": outcome.get("error") or outcome.get("message"),
					}
				)
			if outcome.get("eligible_for_alert"):
				summary["eligible_for_alert"] += 1
		except Exception as exc:
			frappe.log_error(
				title="NAVE Unbilled Alert: project evaluation failed",
				message=f"Project {name}: {exc}",
			)
			summary["errors"].append({"project": name, "error": str(exc)})

	return summary


def run_project_unbilled_alert_daily() -> dict[str, Any]:
	"""
	Daily scheduler entrypoint.
	1) Evaluate all projects (open/refresh/resolve)
	2) Send one batched Director alert for newly eligible cycles
	"""
	settings = load_unbilled_alert_settings()
	if not settings.get("enabled"):
		summary = _empty_summary()
		summary["skipped_reason"] = "settings_disabled"
		return summary

	summary = evaluate_all_project_unbilled_alerts(settings=settings)

	from project_custom.project_unbilled_alert_notify import send_unbilled_alert_batch

	try:
		notify = send_unbilled_alert_batch(settings=settings)
		summary["alerts_sent"] = cint(notify.get("alerts_sent"))
		if notify.get("errors"):
			summary["errors"].extend(notify["errors"])
		if notify.get("skipped_reason"):
			summary["notify_skipped_reason"] = notify["skipped_reason"]
	except Exception as exc:
		frappe.log_error(
			title="NAVE Unbilled Alert: notify batch failed",
			message=str(exc),
		)
		summary["errors"].append({"channel": "notify", "error": str(exc)})

	return summary
