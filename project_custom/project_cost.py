import frappe


def store_previous_project(doc, method=None):
    doc.flags.previous_project = frappe.db.get_value(
        "Journal Entry", doc.name, "project"
    )


def recalculate_for_journal_entry(doc, method=None):
    projects = {
        doc.get("project"),
        getattr(doc.flags, "previous_project", None),
    }

    for project in filter(None, projects):
        recalculate_project_journal_entry_cost(project)


def recalculate_project_journal_entry_cost(project):
    amount = frappe.db.sql(
        """
        SELECT COALESCE(SUM(jea.debit - jea.credit), 0)
        FROM `tabJournal Entry` je
        INNER JOIN `tabJournal Entry Account` jea ON jea.parent = je.name
        INNER JOIN `tabAccount` account ON account.name = jea.account
        WHERE je.docstatus = 1
          AND je.project = %s
          AND account.root_type = 'Expense'
        """,
        project,
    )[0][0]

    frappe.db.set_value(
        "Project",
        project,
        "custom_total_journal_entry_cost",
        amount,
        update_modified=False,
    )
