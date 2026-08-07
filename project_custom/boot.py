"""Desk boot tweaks for NAVE Tasks."""

from __future__ import annotations


LEGACY_DASHBOARD_PAGE = "nave-task-dashboard"


def extend_bootinfo(bootinfo=None):
	"""
	Defensive cleanup until migrate deletes the DB Page record.
	After v1_7.delete_nave_task_dashboard_page, this is a no-op.
	"""
	if bootinfo is None:
		return

	page_info = bootinfo.get("page_info")
	if isinstance(page_info, dict):
		page_info.pop(LEGACY_DASHBOARD_PAGE, None)

	allowed_pages = bootinfo.get("allowed_pages")
	if isinstance(allowed_pages, list):
		bootinfo["allowed_pages"] = [
			p for p in allowed_pages if p != LEGACY_DASHBOARD_PAGE
		]
