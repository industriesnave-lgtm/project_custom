from project_custom.install import (
    ensure_custom_fields,
    recalculate_all_project_journal_entry_costs,
)


def execute():
    ensure_custom_fields()
    recalculate_all_project_journal_entry_costs()
