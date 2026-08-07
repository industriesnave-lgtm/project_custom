import frappe


def execute():
	"""Permanently remove the legacy standalone NAVE Task Dashboard Page.

	The consolidated entry is `nave-tasks`. Hiding via bootinfo/sentinel role
	is insufficient — Administrator still saw the Page in Desk. Source files
	are deleted; this patch clears any surviving database Page record.
	"""
	page_name = "nave-task-dashboard"
	if frappe.db.exists("Page", page_name):
		frappe.delete_doc("Page", page_name, force=1, ignore_permissions=True)
