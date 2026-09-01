# Copyright (c) 2026, Nave Industries and contributors
# License: MIT. See LICENSE

import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
    filters = frappe._dict(filters or {})

    columns = get_columns()
    data = get_data(filters)

    return columns, data


def get_columns():
    return [
        {
            "label": _("Sales Order"),
            "fieldname": "sales_order",
            "fieldtype": "Link",
            "options": "Sales Order",
            "width": 170,
        },
        {
            "label": _("SO Date"),
            "fieldname": "transaction_date",
            "fieldtype": "Date",
            "width": 100,
        },
        {
            "label": _("Customer"),
            "fieldname": "customer",
            "fieldtype": "Link",
            "options": "Customer",
            "width": 180,
        },
        {
            "label": _("Customer Name"),
            "fieldname": "customer_name",
            "fieldtype": "Data",
            "width": 180,
        },
        {
            "label": _("Project"),
            "fieldname": "project",
            "fieldtype": "Link",
            "options": "Project",
            "width": 160,
        },
        {
            "label": _("Item Code"),
            "fieldname": "item_code",
            "fieldtype": "Link",
            "options": "Item",
            "width": 140,
        },
        {
            "label": _("Item Name"),
            "fieldname": "item_name",
            "fieldtype": "Data",
            "width": 200,
        },
        {
            "label": _("UOM"),
            "fieldname": "uom",
            "fieldtype": "Link",
            "options": "UOM",
            "width": 80,
        },
        {
            "label": _("Ordered Qty"),
            "fieldname": "ordered_qty",
            "fieldtype": "Float",
            "width": 110,
        },
        {
            "label": _("Invoiced Qty"),
            "fieldname": "invoiced_qty",
            "fieldtype": "Float",
            "width": 110,
        },
        {
            "label": _("Pending Qty"),
            "fieldname": "pending_qty",
            "fieldtype": "Float",
            "width": 110,
        },
        {
            "label": _("Rate"),
            "fieldname": "rate",
            "fieldtype": "Currency",
            "options": "currency",
            "width": 110,
        },
        {
            "label": _("Ordered Amount"),
            "fieldname": "ordered_amount",
            "fieldtype": "Currency",
            "options": "currency",
            "width": 130,
        },
        {
            "label": _("Invoiced Amount"),
            "fieldname": "invoiced_amount",
            "fieldtype": "Currency",
            "options": "currency",
            "width": 130,
        },
        {
            "label": _("Pending Amount"),
            "fieldname": "pending_amount",
            "fieldtype": "Currency",
            "options": "currency",
            "width": 130,
        },
        {
            "label": _("Delivery Date"),
            "fieldname": "delivery_date",
            "fieldtype": "Date",
            "width": 105,
        },
        {
            "label": _("SO Status"),
            "fieldname": "so_status",
            "fieldtype": "Data",
            "width": 110,
        },
        {
            "label": _("Billing Status"),
            "fieldname": "billing_status",
            "fieldtype": "Data",
            "width": 120,
        },
        {
            "label": _("Currency"),
            "fieldname": "currency",
            "fieldtype": "Data",
            "width": 80,
        },
    ]


def get_data(filters):
    conditions = ["so.docstatus = 1"]

    values = {}

    if filters.get("company"):
        conditions.append("so.company = %(company)s")
        values["company"] = filters.company

    if filters.get("from_date"):
        conditions.append("so.transaction_date >= %(from_date)s")
        values["from_date"] = filters.from_date

    if filters.get("to_date"):
        conditions.append("so.transaction_date <= %(to_date)s")
        values["to_date"] = filters.to_date

    if filters.get("customer"):
        conditions.append("so.customer = %(customer)s")
        values["customer"] = filters.customer

    if filters.get("sales_order"):
        conditions.append("so.name = %(sales_order)s")
        values["sales_order"] = filters.sales_order

    if filters.get("project"):
        conditions.append("so.project = %(project)s")
        values["project"] = filters.project

    if filters.get("item_code"):
        conditions.append("soi.item_code = %(item_code)s")
        values["item_code"] = filters.item_code

    rows = frappe.db.sql(
        f"""
        SELECT
            so.name AS sales_order,
            so.transaction_date,
            so.customer,
            so.customer_name,
            so.project,
            so.status AS so_status,
            so.currency,

            soi.name AS sales_order_item,
            soi.item_code,
            soi.item_name,
            soi.uom,
            soi.qty AS ordered_qty,
            soi.rate,
            soi.amount AS ordered_amount,
            soi.delivery_date,

            COALESCE(inv.invoiced_qty, 0) AS invoiced_qty,
            COALESCE(inv.invoiced_amount, 0) AS invoiced_amount

        FROM `tabSales Order` so
        INNER JOIN `tabSales Order Item` soi
            ON soi.parent = so.name

        LEFT JOIN (
            SELECT
                sii.so_detail,
                SUM(sii.qty) AS invoiced_qty,
                SUM(sii.amount) AS invoiced_amount
            FROM `tabSales Invoice Item` sii
            INNER JOIN `tabSales Invoice` si
                ON si.name = sii.parent
            WHERE
                si.docstatus = 1
                AND IFNULL(sii.so_detail, '') != ''
            GROUP BY sii.so_detail
        ) inv
            ON inv.so_detail = soi.name

        WHERE {" AND ".join(conditions)}

        ORDER BY
            so.transaction_date DESC,
            so.name DESC,
            soi.idx ASC
        """,
        values,
        as_dict=True,
    )

    data = []

    for row in rows:
        ordered_qty = flt(row.ordered_qty)
        invoiced_qty = flt(row.invoiced_qty)
        pending_qty = ordered_qty - invoiced_qty

        ordered_amount = flt(row.ordered_amount)
        invoiced_amount = flt(row.invoiced_amount)
        pending_amount = ordered_amount - invoiced_amount

        # Ignore tiny floating-point differences.
        if abs(pending_qty) < 0.000001:
            pending_qty = 0

        if abs(pending_amount) < 0.01:
            pending_amount = 0

        if filters.get("pending_only") and pending_qty <= 0:
            continue

        if invoiced_qty <= 0:
            billing_status = "Not Invoiced"
        elif pending_qty > 0:
            billing_status = "Partly Invoiced"
        else:
            billing_status = "Fully Invoiced"

        row.update(
            {
                "pending_qty": pending_qty,
                "pending_amount": pending_amount,
                "billing_status": billing_status,
            }
        )

        data.append(row)

    return data
