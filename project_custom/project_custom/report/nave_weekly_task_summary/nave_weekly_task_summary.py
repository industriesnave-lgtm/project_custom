# Copyright (c) 2026, Nave Industries and contributors
# License: MIT. See LICENSE

from project_custom.nave_task_script_reports import execute_weekly_task_summary_report


def execute(filters=None):
	return execute_weekly_task_summary_report(filters)
