"""Recurring NAVE Task date math and generation helpers."""

from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta

FREQUENCIES = ("Daily", "Weekly", "Monthly", "Yearly")


def _as_date(value) -> date | None:
	if value is None or value == "":
		return None
	if isinstance(value, datetime):
		return value.date()
	if isinstance(value, date):
		return value
	text = str(value).strip()
	if " " in text:
		text = text.split(" ", 1)[0]
	return datetime.strptime(text, "%Y-%m-%d").date()


def add_months(base: date, months: int) -> date:
	"""Advance by calendar months, clamping to month-end when needed."""
	month_index = base.month - 1 + months
	year = base.year + month_index // 12
	month = month_index % 12 + 1
	day = min(base.day, calendar.monthrange(year, month)[1])
	return date(year, month, day)


def add_years(base: date, years: int) -> date:
	"""Advance by years; Feb 29 becomes Feb 28 on non-leap years."""
	try:
		return base.replace(year=base.year + years)
	except ValueError:
		return base.replace(year=base.year + years, month=2, day=28)


def next_occurrence_date(frequency: str, current: date) -> date:
	frequency = (frequency or "").strip()
	if frequency == "Daily":
		return current + timedelta(days=1)
	if frequency == "Weekly":
		return current + timedelta(days=7)
	if frequency == "Monthly":
		return add_months(current, 1)
	if frequency == "Yearly":
		return add_years(current, 1)
	raise ValueError(f"Unsupported recurrence frequency: {frequency}")


def calculate_due_date(occurrence: date, due_after_days) -> date:
	days = int(due_after_days or 0)
	if days < 0:
		raise ValueError("recurrence_due_after_days must be zero or positive.")
	return occurrence + timedelta(days=days)


def should_stop_recurrence(
	*,
	is_recurring,
	recurrence_active,
	status: str | None,
	recurrence_end_date,
	occurrence: date,
) -> bool:
	if not int(is_recurring or 0):
		return True
	if not int(recurrence_active or 0):
		return True
	if (status or "") in ("Closed", "Cancelled"):
		return True
	end = _as_date(recurrence_end_date)
	if end and occurrence > end:
		return True
	return False


def normalize_support_required(value) -> str:
	"""
	Keep support_required as Small Text.
	Normalize Check-like UI values without changing the DocType field type.
	"""
	if value in (None, "", 0, "0", False, "No", "no", "false", "False", "off", "Off"):
		return ""
	if value in (1, "1", True, "Yes", "yes", "true", "True", "on", "On"):
		return "Yes"
	return str(value).strip()


def build_generated_subject(template_subject: str, occurrence: date, sequence: int) -> str:
	base = (template_subject or "Recurring Task").strip()
	return f"{base} ({occurrence.isoformat()} #{sequence})"


def validate_recurrence_config(doc_dict: dict) -> list[str]:
	errors: list[str] = []
	if not int(doc_dict.get("is_recurring") or 0):
		return errors

	freq = (doc_dict.get("recurrence_frequency") or "").strip()
	if freq not in FREQUENCIES:
		errors.append("Recurrence Frequency is required when Is Recurring is enabled.")

	start = _as_date(doc_dict.get("recurrence_start_date"))
	if not start:
		errors.append("Recurrence Start Date is required when Is Recurring is enabled.")

	end = _as_date(doc_dict.get("recurrence_end_date"))
	if start and end and end < start:
		errors.append("Recurrence End Date cannot be before Recurrence Start Date.")

	try:
		due_after = int(doc_dict.get("recurrence_due_after_days") or 0)
		if due_after < 0:
			errors.append("Recurrence Due After Days must be zero or positive.")
	except (TypeError, ValueError):
		errors.append("Recurrence Due After Days must be a whole number.")

	# Generated instances must not become active templates accidentally.
	if doc_dict.get("generated_from") and int(doc_dict.get("is_recurring") or 0):
		errors.append("Generated task instances cannot be recurring templates.")

	return errors


def initial_next_creation_date(doc_dict: dict, today: date | None = None) -> date | None:
	if not int(doc_dict.get("is_recurring") or 0):
		return None
	existing = _as_date(doc_dict.get("next_creation_date"))
	if existing:
		return existing
	start = _as_date(doc_dict.get("recurrence_start_date"))
	return start
