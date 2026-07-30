# Copyright (c) 2026, Nave Industries and contributors
# License: MIT. See LICENSE

from project_custom.nave_task_script_reports import execute_pending_aging


def execute(filters=None):
	return execute_pending_aging(filters)
