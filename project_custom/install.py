import frappe

from project_custom.project_cost import recalculate_project_journal_entry_cost

# Sentinel role for the legacy nave-task-dashboard Page.
# Nobody is assigned this role, so the Page stays out of Awesome Bar / page search
# (Frappe only lists Pages whose Has Role rows match the user). Empty roles would
# expose the Page to everyone.
NAVE_TASK_INTERNAL_REDIRECT_ROLE = "NAVE Task Internal Redirect"


def ensure_nave_task_internal_redirect_role():
    """Create the sentinel role used only to hide the legacy dashboard Page."""
    if frappe.db.exists("Role", NAVE_TASK_INTERNAL_REDIRECT_ROLE):
        return
    doc = frappe.get_doc(
        {
            "doctype": "Role",
            "role_name": NAVE_TASK_INTERNAL_REDIRECT_ROLE,
            "desk_access": 0,
            "is_custom": 1,
        }
    )
    doc.insert(ignore_permissions=True)


def before_migrate():
    # Role must exist before standard Page sync applies Has Role Link rows.
    ensure_nave_task_internal_redirect_role()


def after_install():
    ensure_custom_fields()
    ensure_nave_task_internal_redirect_role()


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


def after_migrate():
    ensure_nave_task_internal_redirect_role()
    ensure_custom_fields()
    recalculate_all_project_journal_entry_costs()
