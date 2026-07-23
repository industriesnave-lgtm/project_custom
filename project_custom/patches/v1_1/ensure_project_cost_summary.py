import frappe

from project_custom.project_cost import recalculate_project_journal_entry_cost


FIELDS = [
    {
        "dt": "Project",
        "label": "Total Cost Including Journal Entry",
        "fieldname": "custom_total_cost_including_journal_entry",
        "fieldtype": "Currency",
        "insert_after": "custom_total_journal_entry_cost",
        "read_only": 1,
        "no_copy": 1,
    },
    {
        "dt": "Project",
        "label": "Gross Margin Including Journal Entry",
        "fieldname": "custom_gross_margin_including_journal_entry",
        "fieldtype": "Currency",
        "insert_after": "gross_margin",
        "read_only": 1,
        "no_copy": 1,
    },
    {
        "dt": "Project",
        "label": "Gross Margin % Including Journal Entry",
        "fieldname": "custom_gross_margin_percent_including_journal_entry",
        "fieldtype": "Percent",
        "insert_after": "custom_gross_margin_including_journal_entry",
        "read_only": 1,
        "no_copy": 1,
    },
]


def execute():
    for field in FIELDS:
        if not frappe.db.exists(
            "Custom Field",
            {"dt": field["dt"], "fieldname": field["fieldname"]},
        ):
            frappe.get_doc(
                {
                    "doctype": "Custom Field",
                    **field,
                }
            ).insert(ignore_permissions=True)

    for project in frappe.get_all("Project", pluck="name"):
        recalculate_project_journal_entry_cost(project)
