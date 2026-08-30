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


def get_project_payroll_manpower_cost(project):
    # Nave Payroll may not be installed on every site.
    if not frappe.db.exists("DocType", "Monthly Project Allocation"):
        return 0

    if not frappe.db.exists(
        "DocType", "Monthly Project Allocation Detail"
    ):
        return 0

    payroll_cost = frappe.db.sql(
        """
        SELECT COALESCE(SUM(detail.project_manpower_cost), 0)
        FROM `tabMonthly Project Allocation Detail` detail
        INNER JOIN `tabMonthly Project Allocation` allocation
            ON allocation.name = detail.parent
        WHERE allocation.docstatus = 1
          AND detail.parenttype = 'Monthly Project Allocation'
          AND detail.project = %s
        """,
        project,
    )[0][0]

    return flt(payroll_cost)


def recalculate_project_journal_entry_cost(project):
    journal_entry_cost = frappe.db.sql(
        """
        SELECT COALESCE(SUM(jea.debit - jea.credit), 0)
        FROM `tabJournal Entry` je
        INNER JOIN `tabJournal Entry Account` jea
            ON jea.parent = je.name
        INNER JOIN `tabAccount` account
            ON account.name = jea.account
        WHERE je.docstatus = 1
          AND je.project = %s
          AND account.root_type = 'Expense'
        """,
        project,
    )[0][0]

    payroll_manpower_cost = get_project_payroll_manpower_cost(project)

    financials = frappe.db.get_value(
        "Project",
        project,
        ["total_billed_amount", "gross_margin"],
        as_dict=True,
    ) or {}

    billed_amount = flt(financials.total_billed_amount)
    standard_gross_margin = flt(financials.gross_margin)

    # ERPNext standard project cost
    standard_total_cost = (
        billed_amount - standard_gross_margin
    )

    # Existing cost including Journal Entry
    total_cost_including_journal_entry = (
        standard_total_cost + flt(journal_entry_cost)
    )

    gross_margin_including_journal_entry = (
        standard_gross_margin - flt(journal_entry_cost)
    )

    # Final cost including Journal Entry + Payroll CTC
    total_cost_including_all = (
        standard_total_cost
        + flt(journal_entry_cost)
        + flt(payroll_manpower_cost)
    )

    gross_margin_including_all = (
        standard_gross_margin
        - flt(journal_entry_cost)
        - flt(payroll_manpower_cost)
    )

    frappe.db.set_value(
        "Project",
        project,
        {
            # Existing Journal Entry summary
            "custom_total_journal_entry_cost":
                flt(journal_entry_cost),

            "custom_total_cost_including_journal_entry":
                total_cost_including_journal_entry,

            "custom_gross_margin_including_journal_entry":
                gross_margin_including_journal_entry,

            "custom_gross_margin_percent_including_journal_entry": (
                gross_margin_including_journal_entry
                / billed_amount
                * 100
                if billed_amount
                else 0
            ),

            # Nave Payroll manpower summary
            "custom_total_payroll_manpower_cost":
                flt(payroll_manpower_cost),

            "custom_total_cost_including_journal_and_payroll":
                total_cost_including_all,

            "custom_gross_margin_including_journal_and_payroll":
                gross_margin_including_all,

            "custom_gross_margin_percent_including_journal_and_payroll": (
                gross_margin_including_all
                / billed_amount
                * 100
                if billed_amount
                else 0
            ),
        },
        update_modified=False,
    )


@frappe.whitelist(methods=["POST"])
def recalculate_project_cost_summary(project):
    if "System Manager" not in frappe.get_roles():
        frappe.throw(
            "Only System Manager can recalculate Project costing.",
            frappe.PermissionError,
        )

    if not frappe.db.exists("Project", project):
        frappe.throw(f"Project not found: {project}")

    recalculate_project_journal_entry_cost(project)

    return {
        "success": True,
        "project": project,
        "journal_entry_cost": frappe.db.get_value(
            "Project",
            project,
            "custom_total_journal_entry_cost",
        ),
        "payroll_manpower_cost": frappe.db.get_value(
            "Project",
            project,
            "custom_total_payroll_manpower_cost",
        ),
    }
