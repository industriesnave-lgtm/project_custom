# Copyright (c) 2026, Nave Industries and contributors
# License: MIT. See LICENSE

import re

import frappe
from frappe.model.document import Document
from frappe.utils import cint, flt, validate_email_address


class NAVEProjectUnbilledAlertSettings(Document):
	def validate(self):
		self.threshold_amount = flt(self.threshold_amount)
		if self.threshold_amount < 0:
			frappe.throw("Threshold Amount cannot be negative.")

		self.ageing_days = cint(self.ageing_days)
		if self.ageing_days < 1:
			frappe.throw("Ageing Days must be at least 1.")

		self.director_emails = normalize_director_emails(self.director_emails)


def normalize_director_emails(raw):
	"""Split on commas/semicolons/newlines; validate; return newline-joined unique emails."""
	if not raw:
		return ""

	parts = re.split(r"[,;\n]+", str(raw))
	seen = set()
	cleaned = []
	for part in parts:
		email = (part or "").strip()
		if not email:
			continue
		validate_email_address(email, throw=True)
		key = email.lower()
		if key in seen:
			continue
		seen.add(key)
		cleaned.append(email)
	return "\n".join(cleaned)


def get_director_email_list(settings=None):
	"""Return list of director emails from settings (or the Single)."""
	if settings is None:
		settings = frappe.get_single("NAVE Project Unbilled Alert Settings")
	raw = getattr(settings, "director_emails", None) or ""
	if not raw:
		return []
	return [line.strip() for line in str(raw).splitlines() if line.strip()]
