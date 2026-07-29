import frappe


def execute():
	"""
	Idempotent Phase 3 defaults for recurrence fields.
	Does not convert existing tasks into recurring templates.
	"""
	if not frappe.db.table_exists("NAVE Task"):
		return

	# Safe defaults only where columns exist and values are NULL.
	column_defaults = {
		"is_recurring": 0,
		"recurrence_active": 0,
		"recurrence_due_after_days": 0,
		"recurrence_sequence": 0,
	}

	for column, default in column_defaults.items():
		if not frappe.db.has_column("NAVE Task", column):
			continue
		frappe.db.sql(
			f"""
			UPDATE `tabNAVE Task`
			SET `{column}` = %s
			WHERE `{column}` IS NULL
			""",
			default,
		)

	# Ensure next_creation_date for already-valid active templates only.
	if frappe.db.has_column("NAVE Task", "next_creation_date") and frappe.db.has_column(
		"NAVE Task", "recurrence_start_date"
	):
		frappe.db.sql(
			"""
			UPDATE `tabNAVE Task`
			SET next_creation_date = recurrence_start_date
			WHERE IFNULL(is_recurring, 0) = 1
			  AND IFNULL(recurrence_active, 0) = 1
			  AND recurrence_start_date IS NOT NULL
			  AND (next_creation_date IS NULL OR next_creation_date = '')
			"""
		)
