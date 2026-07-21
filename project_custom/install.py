import frappe

from project_custom.project_cost import recalculate_project_journal_entry_cost


def after_install():
    ensure_custom_fields()


def ensure_custom_fields():
    fields = [
        {
            "dt": "Journal Entry",
            "label": "Project",
            "fieldname": "project",
            "fieldtype": "Link",
            "options": "Project",
            "insert_after": "posting_date",
            "allow_on_submit": 1,
        },
        {
            "dt": "Project",
            "label": "Total Journal Entry Cost",
            "fieldname": "custom_total_journal_entry_cost",
            "fieldtype": "Currency",
            "insert_after": "total_consumed_material_cost",
            "read_only": 1,
            "no_copy": 1,
        },
    ]

    for field in fields:
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


def recalculate_all_project_journal_entry_costs():
    for project in frappe.get_all("Project", pluck="name"):
        recalculate_project_journal_entry_cost(project)
