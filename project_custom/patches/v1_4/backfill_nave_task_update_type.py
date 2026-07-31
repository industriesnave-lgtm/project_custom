import frappe


def execute():
	"""Backfill update_type on existing NAVE Task Update rows. Additive only."""
	if not frappe.db.has_column("NAVE Task Update", "update_type"):
		return

	frappe.db.sql(
		"""
		UPDATE `tabNAVE Task Update`
		SET update_type = 'Progress Update'
		WHERE update_type IS NULL OR update_type = ''
		"""
	)
