"""Desk boot tweaks for NAVE Tasks."""

from __future__ import annotations


LEGACY_DASHBOARD_PAGE = "nave-task-dashboard"


def extend_bootinfo(bootinfo=None):
	"""
	Hide the legacy standalone NAVE Task Dashboard from Desk search / page_info.
	The consolidated entry remains `nave-tasks` (NAVE Tasks).
	URL redirects in hooks + role_dashboard_redirect.js keep bookmarks working.
	"""
	if bootinfo is None:
		return

	page_info = bootinfo.get("page_info")
	if isinstance(page_info, dict):
		page_info.pop(LEGACY_DASHBOARD_PAGE, None)

	# Some Frappe builds also expose allowed pages as a list.
	allowed_pages = bootinfo.get("allowed_pages")
	if isinstance(allowed_pages, list):
		bootinfo["allowed_pages"] = [
			p for p in allowed_pages if p != LEGACY_DASHBOARD_PAGE
		]
