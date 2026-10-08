import frappe
from frappe import _
from frappe.utils import getdate, flt
from datetime import date
from calendar import monthrange


def execute(filters=None):
    filters = frappe._dict(filters or {})

    selected = getdate(filters.get("month_year") or date.today())

    if filters.get("from_date") and filters.get("to_date"):
        from_date = getdate(filters.from_date)
        to_date = getdate(filters.to_date)
    elif filters.get("from_date") or filters.get("to_date"):
        frappe.throw(_("Please provide both From Date and To Date."))
    else:
        from_date = date(selected.year, selected.month, 1)
        to_date = date(
            selected.year,
            selected.month,
            monthrange(selected.year, selected.month)[1],
        )

    if from_date > to_date:
        frappe.throw(_("From Date cannot be after To Date."))

    conditions = ""
    params = {
        "from_date": from_date,
        "to_date": to_date,
    }

    if filters.get("project"):
        conditions += """
            AND COALESCE(
                NULLIF(sii.project, ''),
                NULLIF(si.project, ''),
                NULLIF(original_item.project, ''),
                NULLIF(original_si.project, '')
            ) = %(project)s
        """
        params["project"] = filters.project

    rows = frappe.db.sql(
        f"""
        SELECT
            COALESCE(
                NULLIF(sii.project, ''),
                NULLIF(si.project, ''),
                NULLIF(original_item.project, ''),
                NULLIF(original_si.project, '')
            ) AS project,
            so.custom_billing_type AS billing_type,
            SUM(sii.base_net_amount) AS amount
        FROM `tabSales Invoice Item` sii
        INNER JOIN `tabSales Invoice` si
            ON si.name = sii.parent

        LEFT JOIN `tabSales Invoice` original_si
            ON si.is_return = 1
            AND original_si.name = si.return_against
            AND original_si.docstatus = 1

        LEFT JOIN `tabSales Invoice Item` original_item
            ON original_item.name = sii.sales_invoice_item
            AND original_item.parent = original_si.name

        LEFT JOIN `tabSales Order` so
            ON so.name = COALESCE(
                NULLIF(sii.sales_order, ''),
                NULLIF(original_item.sales_order, '')
            )

        WHERE si.docstatus = 1
            AND si.posting_date BETWEEN %(from_date)s AND %(to_date)s
            AND so.custom_billing_type IN ('Service', 'Supply')
            AND COALESCE(
                NULLIF(sii.project, ''),
                NULLIF(si.project, ''),
                NULLIF(original_item.project, ''),
                NULLIF(original_si.project, '')
            ) IS NOT NULL
            {conditions}

        GROUP BY
            project,
            so.custom_billing_type
        ORDER BY project
        """,
        params,
        as_dict=True,
    )

    projects = {}

    for row in rows:
        project = row.project

        if project not in projects:
            projects[project] = {
                "project": project,
                "service_billing": 0,
                "supply_billing": 0,
                "total_billing": 0,
            }

        amount = flt(row.amount)

        if row.billing_type == "Service":
            projects[project]["service_billing"] += amount
        elif row.billing_type == "Supply":
            projects[project]["supply_billing"] += amount

    data = list(projects.values())

    for row in data:
        row["total_billing"] = (
            row["service_billing"] + row["supply_billing"]
        )

    columns = [
        {
            "label": _("Project"),
            "fieldname": "project",
            "fieldtype": "Link",
            "options": "Project",
            "width": 230,
        },
        {
            "label": _("Service Billing"),
            "fieldname": "service_billing",
            "fieldtype": "Currency",
            "width": 180,
        },
        {
            "label": _("Supply Billing"),
            "fieldname": "supply_billing",
            "fieldtype": "Currency",
            "width": 180,
        },
        {
            "label": _("Total Billing"),
            "fieldname": "total_billing",
            "fieldtype": "Currency",
            "width": 180,
        },
    ]

    summary = [
        {
            "label": _("Service Billing"),
            "value": sum(flt(d["service_billing"]) for d in data),
            "indicator": "Blue",
            "datatype": "Currency",
        },
        {
            "label": _("Supply Billing"),
            "value": sum(flt(d["supply_billing"]) for d in data),
            "indicator": "Orange",
            "datatype": "Currency",
        },
        {
            "label": _("Total Billing"),
            "value": sum(flt(d["total_billing"]) for d in data),
            "indicator": "Green",
            "datatype": "Currency",
        },
    ]

    return columns, data, None, None, summary
