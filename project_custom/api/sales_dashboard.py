import frappe
from frappe.utils import get_first_day, getdate, nowdate


def get_total(filters):
    values = frappe.get_all(
        "Sales Invoice",
        filters=filters,
        pluck="grand_total",
        limit_page_length=0,
    )
    return sum(float(value or 0) for value in values)


@frappe.whitelist()
def get_sales_dashboard():
    frappe.only_for(["Sales User", "Sales Manager", "System Manager"])

    today = getdate(nowdate())
    month_start = get_first_day(today)

    today_sales = get_total(
        {"docstatus": 1, "is_return": 0, "posting_date": today}
    )

    month_sales = get_total(
        {
            "docstatus": 1,
            "is_return": 0,
            "posting_date": ["between", [month_start, today]],
        }
    )

    pending_collection = get_total(
        {"docstatus": 1, "is_return": 0, "outstanding_amount": [">", 0]}
    )

    overdue_amount = get_total(
        {
            "docstatus": 1,
            "is_return": 0,
            "outstanding_amount": [">", 0],
            "due_date": ["<", today],
        }
    )

    credit_note_amount = abs(
        get_total(
            {
                "docstatus": 1,
                "is_return": 1,
                "posting_date": ["between", [month_start, today]],
            }
        )
    )

    pending_orders = frappe.db.count(
        "Sales Order",
        filters={
            "docstatus": 1,
            "status": ["not in", ["Closed", "Completed", "Cancelled"]],
        },
    )

    recent_invoices = frappe.get_all(
        "Sales Invoice",
        filters={"docstatus": 1},
        fields=[
            "name",
            "customer",
            "grand_total",
            "outstanding_amount",
            "status",
            "posting_date",
        ],
        order_by="posting_date desc, modified desc",
        limit_page_length=5,
    )

    return {
        "today_sales": today_sales,
        "month_sales": month_sales,
        "pending_collection": pending_collection,
        "overdue_amount": overdue_amount,
        "credit_note_amount": credit_note_amount,
        "pending_orders": pending_orders,
        "recent_invoices": recent_invoices,
    }
