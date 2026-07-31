"""Thin whitelisted APIs for the NAVE Task Dashboard (Batch 8A).

All business logic lives in project_custom.nave_task_dashboard.
Access uses the same app-role gate as other NAVE Task APIs.
"""

from __future__ import annotations

import frappe

from project_custom.nave_task_dashboard import (
	get_dashboard_list,
	get_dashboard_metadata,
	get_dashboard_summary,
)
from project_custom.nave_task_utils import user_has_nave_task_app_access


def _require_nave_task_access():
	"""Login + NAVE Task app-role gate (same rules as api.nave_task)."""
	user = frappe.session.user
	if not user or user == "Guest":
		frappe.throw("Please log in.", frappe.PermissionError)
	if not user_has_nave_task_app_access(user, frappe.get_roles(user)):
		frappe.throw(
			"You do not have permission to access NAVE Tasks.",
			frappe.PermissionError,
		)


@frappe.whitelist()
def get_task_dashboard_summary(filters=None):
	"""Read-only dashboard KPI summary for the current user."""
	_require_nave_task_access()
	return get_dashboard_summary(filters, user=frappe.session.user)


@frappe.whitelist()
def get_task_dashboard_list(list_type, filters=None, limit=10):
	"""Read-only compact task list for dashboard widgets."""
	_require_nave_task_access()
	return get_dashboard_list(
		list_type,
		filters=filters,
		limit=limit,
		user=frappe.session.user,
	)


@frappe.whitelist()
def get_task_dashboard_metadata():
	"""Read-only dashboard UI metadata (no hidden users/departments)."""
	_require_nave_task_access()
	return get_dashboard_metadata(user=frappe.session.user)
