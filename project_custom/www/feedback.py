import frappe


no_cache = 1


def get_context(context):
	context.no_cache = 1
	context.no_breadcrumbs = 1
	context.title = "Customer Feedback | Nave Industries"

	settings = frappe.get_single("Customer Feedback Settings")

	if not settings.portal_enabled:
		frappe.throw(
			"The customer feedback portal is currently unavailable.",
			frappe.PermissionError,
		)

	context.google_review_url = settings.google_review_url or ""
	return context
