# Copyright (c) 2026, Nave Industries and contributors
# License: MIT. See LICENSE

from project_custom.nave_task_script_reports import execute_completed_task_report


def execute(filters=None):
	return execute_completed_task_report(filters)
