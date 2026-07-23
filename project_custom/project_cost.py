import frappe
from frappe.utils import flt


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
    journal_entry_cost = frappe.db.sql(
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

    financials = frappe.db.get_value(
        "Project",
        project,
        ["total_billed_amount", "gross_margin"],
        as_dict=True,
    ) or {}

    billed_amount = flt(financials.total_billed_amount)
    standard_gross_margin = flt(financials.gross_margin)
    standard_total_cost = billed_amount - standard_gross_margin
    gross_margin_including_journal_entry = (
        standard_gross_margin - flt(journal_entry_cost)
    )

    frappe.db.set_value(
        "Project",
        project,
        {
            "custom_total_journal_entry_cost": journal_entry_cost,
            "custom_total_cost_including_journal_entry": (
                standard_total_cost + flt(journal_entry_cost)
            ),
            "custom_gross_margin_including_journal_entry": (
                gross_margin_including_journal_entry
            ),
            "custom_gross_margin_percent_including_journal_entry": (
                gross_margin_including_journal_entry / billed_amount * 100
                if billed_amount
                else 0
            ),
        },
        update_modified=False,
    )
