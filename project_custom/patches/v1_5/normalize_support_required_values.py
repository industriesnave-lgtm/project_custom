import frappe

from project_custom.nave_task_recurrence import normalize_support_required


def execute():
	"""Normalize Check-like support_required values without changing field type."""
	if not frappe.db.table_exists("NAVE Task"):
		return
	if not frappe.db.has_column("NAVE Task", "support_required"):
		return

	rows = frappe.db.sql(
		"""
		SELECT name, support_required
		FROM `tabNAVE Task`
		WHERE support_required IS NOT NULL AND support_required != ''
		""",
		as_dict=True,
	)
	for row in rows:
		normalized = normalize_support_required(row.support_required)
		if normalized != row.support_required:
			frappe.db.set_value(
				"NAVE Task",
				row.name,
				"support_required",
				normalized,
				update_modified=False,
			)

	if frappe.db.table_exists("NAVE Task Update") and frappe.db.has_column(
		"NAVE Task Update", "support_required"
	):
		updates = frappe.db.sql(
			"""
			SELECT name, support_required
			FROM `tabNAVE Task Update`
			WHERE support_required IS NOT NULL AND support_required != ''
			""",
			as_dict=True,
		)
		for row in updates:
			normalized = normalize_support_required(row.support_required)
			if normalized != row.support_required:
				frappe.db.set_value(
					"NAVE Task Update",
					row.name,
					"support_required",
					normalized,
					update_modified=False,
				)
