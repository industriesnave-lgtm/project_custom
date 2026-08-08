# Copyright (c) 2026, Nave Industries and contributors
# License: MIT. See LICENSE
"""
Batch Director email + optional in-app Notification Log for unbilled alerts (V1).

Marks alert_sent only after a successful enabled delivery channel.
"""

from __future__ import annotations

import re
from typing import Any

import frappe
from frappe.utils import (
	cint,
	escape_html,
	flt,
	fmt_money,
	formatdate,
	getdate,
	now_datetime,
	nowdate,
	validate_email_address,
)

from project_custom.project_unbilled_alert_cycle import (
	ALERT_DOCTYPE,
	DEFAULT_AGEING_DAYS,
	calculate_ageing_days,
	is_cycle_alert_eligible,
	load_unbilled_alert_settings,
)

INR = "INR"
IN_APP_SUBJECT = "Project Unbilled Expense Alert"


def parse_director_recipient_emails(raw) -> dict[str, list[str]]:
	"""
	Parse Settings.director_emails for delivery.
	Invalid addresses are skipped (not thrown) so one bad address does not abort others.
	"""
	valid: list[str] = []
	invalid: list[str] = []
	seen: set[str] = set()

	if not raw:
		return {"valid": valid, "invalid": invalid}

	parts = re.split(r"[,;\n]+", str(raw))
	for part in parts:
		email = (part or "").strip()
		if not email:
			continue
		checked = validate_email_address(email, throw=False)
		if not checked:
			invalid.append(email)
			continue
		key = checked.lower()
		if key in seen:
			continue
		seen.add(key)
		valid.append(checked)
	return {"valid": valid, "invalid": invalid}


def _cycle_field(cycle, key, default=None):
	if isinstance(cycle, dict):
		return cycle.get(key, default)
	return getattr(cycle, key, default)


def _sort_eligible_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
	def key(r):
		age = cint(r.get("ageing_days") or 0)
		unbilled = flt(r.get("current_unbilled_amount"))
		project = r.get("project") or ""
		return (-age, -unbilled, project)

	return sorted(rows or [], key=key)


def collect_eligible_unsent_cycles(
	settings: dict[str, Any] | None = None,
	*,
	today=None,
) -> list[dict[str, Any]]:
	"""DB-fetch Pending/unsent cycles and keep only currently eligible ones."""
	settings = settings or load_unbilled_alert_settings()
	ageing_threshold = cint(settings.get("ageing_days") or DEFAULT_AGEING_DAYS)
	as_of = getdate(today or nowdate())

	rows = frappe.get_all(
		ALERT_DOCTYPE,
		filters={
			"alert_status": "Pending",
			"alert_sent": 0,
		},
		fields=[
			"name",
			"project",
			"project_name",
			"company",
			"customer",
			"cycle_no",
			"current_unbilled_amount",
			"threshold_amount",
			"threshold_crossed_on",
			"ageing_days",
			"last_sales_invoice_date",
			"project_status",
			"alert_status",
			"alert_sent",
			"resolved_on",
		],
		order_by="project asc",
	)

	eligible: list[dict[str, Any]] = []
	for row in rows or []:
		if row.get("resolved_on"):
			continue
		# Recheck from DB (authoritative).
		fresh = frappe.db.get_value(
			ALERT_DOCTYPE,
			row.get("name"),
			[
				"name",
				"project",
				"project_name",
				"company",
				"customer",
				"cycle_no",
				"current_unbilled_amount",
				"threshold_amount",
				"threshold_crossed_on",
				"ageing_days",
				"last_sales_invoice_date",
				"project_status",
				"alert_status",
				"alert_sent",
				"resolved_on",
			],
			as_dict=True,
		)
		if not fresh or fresh.get("resolved_on"):
			continue
		if cint(fresh.get("alert_sent")) or fresh.get("alert_status") != "Pending":
			continue

		age = calculate_ageing_days(fresh.get("threshold_crossed_on"), today=as_of)
		fresh["ageing_days"] = age
		if not is_cycle_alert_eligible(
			fresh, today=as_of, ageing_threshold=ageing_threshold
		):
			continue
		eligible.append(fresh)

	return _sort_eligible_rows(eligible)


def build_unbilled_alert_email_subject(report_date=None) -> str:
	d = formatdate(getdate(report_date or nowdate()), "dd MMM yyyy")
	return f"Project-wise Unbilled Expense Alert – {d}"


def _fmt_inr(amount) -> str:
	try:
		return fmt_money(flt(amount), currency=INR)
	except Exception:
		return f"₹ {flt(amount):,.2f}"


def build_unbilled_alert_email_message(
	cycles: list[dict[str, Any]],
	*,
	report_date=None,
) -> str:
	"""Professional HTML email: summary + table. No internals/tracebacks."""
	as_of = getdate(report_date or nowdate())
	rows = _sort_eligible_rows(list(cycles or []))
	count = len(rows)
	total_unbilled = sum(flt(r.get("current_unbilled_amount")) for r in rows)
	date_label = escape_html(formatdate(as_of, "dd MMM yyyy"))

	parts = [
		"<p>The following projects have unbilled expense above the configured "
		"threshold and have aged to the alert window.</p>",
		"<p>",
		f"<b>Report date:</b> {date_label}<br>",
		f"<b>Alert-eligible projects:</b> {count}<br>",
		f"<b>Total unbilled amount:</b> {escape_html(_fmt_inr(total_unbilled))}",
		"</p>",
		"<table border='1' cellpadding='6' cellspacing='0' style='border-collapse:collapse;'>",
		"<thead><tr>",
		"<th>Project ID</th>",
		"<th>Project Name</th>",
		"<th>Customer</th>",
		"<th>Unbilled Expense Amount</th>",
		"<th>Threshold Crossed Date</th>",
		"<th>Ageing Days</th>",
		"<th>Last Sales Invoice Date</th>",
		"<th>Project Status</th>",
		"</tr></thead><tbody>",
	]

	for r in rows:
		crossed = r.get("threshold_crossed_on")
		last_si = r.get("last_sales_invoice_date")
		parts.append("<tr>")
		parts.append(f"<td>{escape_html(r.get('project') or '')}</td>")
		parts.append(f"<td>{escape_html(r.get('project_name') or '')}</td>")
		parts.append(f"<td>{escape_html(r.get('customer') or '')}</td>")
		parts.append(
			f"<td style='text-align:right'>{escape_html(_fmt_inr(r.get('current_unbilled_amount')))}</td>"
		)
		parts.append(
			f"<td>{escape_html(formatdate(crossed) if crossed else '')}</td>"
		)
		parts.append(f"<td style='text-align:right'>{cint(r.get('ageing_days'))}</td>")
		parts.append(
			f"<td>{escape_html(formatdate(last_si) if last_si else '')}</td>"
		)
		parts.append(f"<td>{escape_html(r.get('project_status') or '')}</td>")
		parts.append("</tr>")

	parts.append("</tbody></table>")
	parts.append(
		"<p style='color:#666;font-size:12px;'>This is an automated NAVE Project "
		"Unbilled Expense Alert. Please review billing for the listed projects.</p>"
	)
	return "".join(parts)


def _send_batch_email(*, recipients: list[str], subject: str, message: str) -> bool:
	if not recipients:
		return False
	frappe.sendmail(
		recipients=recipients,
		subject=subject,
		message=message,
		delayed=True,
		now=False,
		reference_doctype="NAVE Project Unbilled Alert Settings",
		reference_name="NAVE Project Unbilled Alert Settings",
	)
	return True


def _users_for_emails(emails: list[str]) -> list[dict[str, Any]]:
	"""Enabled Frappe Users whose email matches configured recipients."""
	if not emails:
		return []
	# Case-insensitive match via lower compare in Python after fetch.
	wanted = {e.lower() for e in emails}
	users = frappe.get_all(
		"User",
		filters={"enabled": 1},
		fields=["name", "email"],
	)
	matched = []
	seen_users: set[str] = set()
	for u in users or []:
		email = (u.get("email") or "").strip().lower()
		if not email or email not in wanted:
			continue
		if u["name"] in seen_users:
			continue
		seen_users.add(u["name"])
		matched.append(u)
	return matched


def create_in_app_unbilled_notifications(
	cycles: list[dict[str, Any]],
	recipient_emails: list[str],
) -> dict[str, Any]:
	"""
	One Notification Log per mapped enabled User (not per project).
	Returns {created, failed, errors}.
	"""
	result = {"created": 0, "failed": 0, "errors": []}
	users = _users_for_emails(recipient_emails)
	if not users:
		return result

	count = len(cycles or [])
	total_unbilled = sum(flt(c.get("current_unbilled_amount")) for c in (cycles or []))
	body = (
		f"{count} project(s) have unbilled expense above threshold. "
		f"Total unbilled: {_fmt_inr(total_unbilled)}."
	)

	previous_mute = bool(getattr(frappe.flags, "mute_emails", False))
	frappe.flags.mute_emails = True
	try:
		for user in users:
			try:
				doc = frappe.get_doc(
					{
						"doctype": "Notification Log",
						"for_user": user["name"],
						"subject": IN_APP_SUBJECT,
						"email_content": body,
						"type": "Alert",
						"document_type": "NAVE Project Unbilled Alert Settings",
						"document_name": "NAVE Project Unbilled Alert Settings",
					}
				)
				# System delivery to other users requires elevated insert.
				doc.insert(ignore_permissions=True)
				result["created"] += 1
			except Exception as exc:
				result["failed"] += 1
				result["errors"].append(
					{"user": user.get("name"), "error": str(exc)}
				)
				frappe.log_error(
					title="NAVE Unbilled Alert: in-app notification failed",
					message=f"User {user.get('name')}: {exc}",
				)
	finally:
		frappe.flags.mute_emails = previous_mute

	return result


def mark_cycles_alerted(cycle_names: list[str]) -> dict[str, Any]:
	"""Persist alert_sent / Alerted after successful delivery. Returns count marked."""
	marked = 0
	errors: list[dict[str, Any]] = []
	now = now_datetime()

	for name in cycle_names or []:
		try:
			doc = frappe.get_doc(ALERT_DOCTYPE, name)
			# Final guard against concurrent send / resolve.
			if doc.alert_status != "Pending" or cint(doc.alert_sent) or doc.resolved_on:
				continue
			doc.alert_sent = 1
			doc.alert_sent_on = now
			doc.alert_status = "Alerted"
			doc.save()
			marked += 1
		except Exception as exc:
			errors.append({"cycle": name, "error": str(exc)})
			frappe.log_error(
				title="NAVE Unbilled Alert: mark alert_sent failed",
				message=f"Cycle {name}: {exc}",
			)

	return {"alerts_sent": marked, "errors": errors}


def send_unbilled_alert_batch(
	settings: dict[str, Any] | None = None,
	*,
	today=None,
	cycles: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
	"""
	Send one batched Director email (+ optional in-app) for eligible cycles.

	Delivery / alert_sent rules:
	- both channels disabled -> do not mark sent
	- no valid recipients -> do not mark sent
	- send_email enabled -> email must succeed to mark sent
	- send_email disabled + in-app enabled -> in-app success marks sent
	- email success + in-app failure -> mark sent; log in-app failure
	- email failure -> do not mark sent (retry next day)
	"""
	settings = settings or load_unbilled_alert_settings()
	out: dict[str, Any] = {
		"alerts_sent": 0,
		"email_sent": False,
		"in_app_created": 0,
		"eligible": 0,
		"skipped_reason": None,
		"errors": [],
	}

	send_email = cint(settings.get("send_email"))
	create_in_app = cint(settings.get("create_in_app_notification"))

	if not send_email and not create_in_app:
		out["skipped_reason"] = "both_channels_disabled"
		return out

	parsed = parse_director_recipient_emails(settings.get("director_emails"))
	for bad in parsed["invalid"]:
		out["errors"].append({"recipient": bad, "error": "invalid_email"})
	recipients = parsed["valid"]
	if not recipients:
		out["skipped_reason"] = "no_valid_recipients"
		frappe.log_error(
			title="NAVE Unbilled Alert: no valid recipients",
			message="director_emails empty or all invalid; alert_sent not updated.",
		)
		return out

	if cycles is None:
		cycles = collect_eligible_unsent_cycles(settings, today=today)
	else:
		# Caller-supplied list still re-filtered for safety.
		ageing_threshold = cint(settings.get("ageing_days") or DEFAULT_AGEING_DAYS)
		as_of = getdate(today or nowdate())
		filtered = []
		for c in cycles:
			age = calculate_ageing_days(_cycle_field(c, "threshold_crossed_on"), today=as_of)
			row = dict(c) if isinstance(c, dict) else dict(c.as_dict())
			row["ageing_days"] = age
			if is_cycle_alert_eligible(row, today=as_of, ageing_threshold=ageing_threshold):
				if cint(row.get("alert_sent")) == 0 and row.get("alert_status") == "Pending":
					if not row.get("resolved_on"):
						filtered.append(row)
		cycles = _sort_eligible_rows(filtered)

	out["eligible"] = len(cycles)
	if not cycles:
		out["skipped_reason"] = "no_eligible_cycles"
		return out

	subject = build_unbilled_alert_email_subject(today)
	message = build_unbilled_alert_email_message(cycles, report_date=today)

	email_ok = False
	in_app_ok = False

	if send_email:
		try:
			_send_batch_email(recipients=recipients, subject=subject, message=message)
			email_ok = True
			out["email_sent"] = True
		except Exception as exc:
			out["errors"].append({"channel": "email", "error": str(exc)})
			frappe.log_error(
				title="NAVE Unbilled Alert: batch email failed",
				message=str(exc),
			)

	if create_in_app:
		in_app = create_in_app_unbilled_notifications(cycles, recipients)
		out["in_app_created"] = in_app.get("created", 0)
		out["errors"].extend(in_app.get("errors") or [])
		in_app_ok = cint(in_app.get("created")) > 0

	# Delivery decision
	if send_email:
		delivery_ok = email_ok
	else:
		delivery_ok = in_app_ok

	if not delivery_ok:
		if send_email and not email_ok:
			out["skipped_reason"] = "email_send_failed"
		elif create_in_app and not in_app_ok:
			out["skipped_reason"] = "in_app_failed"
		return out

	names = [c.get("name") for c in cycles if c.get("name")]
	marked = mark_cycles_alerted(names)
	out["alerts_sent"] = marked.get("alerts_sent", 0)
	out["errors"].extend(marked.get("errors") or [])
	return out
