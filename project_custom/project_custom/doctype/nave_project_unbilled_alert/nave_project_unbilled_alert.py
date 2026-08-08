# Copyright (c) 2026, Nave Industries and contributors
# License: MIT. See LICENSE

import frappe
from frappe.model.document import Document


ACTIVE_ALERT_STATUSES = ("Pending", "Alerted")


class NAVEProjectUnbilledAlert(Document):
	def validate(self):
		if not self.cycle_no or self.cycle_no < 1:
			frappe.throw("Cycle No must be at least 1.")

		if self.alert_status in ACTIVE_ALERT_STATUSES and not self.resolved_on:
			_assert_single_active_cycle(self)


def _assert_single_active_cycle(doc):
	"""At most one Pending/Alerted unresolved cycle per project + company."""
	existing = frappe.db.sql(
		"""
		SELECT name
		FROM `tabNAVE Project Unbilled Alert`
		WHERE project = %s
			AND company = %s
			AND alert_status IN ('Pending', 'Alerted')
			AND IFNULL(resolved_on, '') = ''
			AND name != %s
		LIMIT 1
		""",
		(doc.project, doc.company, doc.name or ""),
	)
	if existing:
		frappe.throw(
			f"Project {doc.project} ({doc.company}) already has an active "
			f"unbilled alert cycle ({existing[0][0]})."
		)
