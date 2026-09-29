import frappe
from frappe import _
from frappe.utils import flt


def validate_sales_invoice_qty(doc, method=None):
    """
    Prevent cumulative submitted Sales Invoice quantity from exceeding
    the linked Sales Order Item quantity.
    """

    for row in doc.items:
        if not row.sales_order or not row.so_detail:
            continue

        ordered_qty = frappe.db.get_value(
            "Sales Order Item",
            row.so_detail,
            "qty"
        )

        if ordered_qty is None:
            continue

        already_invoiced = frappe.db.sql(
            """
            SELECT COALESCE(SUM(sii.qty), 0)
            FROM `tabSales Invoice Item` sii
            INNER JOIN `tabSales Invoice` si
                ON si.name = sii.parent
            WHERE
                si.docstatus = 1
                AND sii.so_detail = %s
                AND si.name != %s
                AND IFNULL(si.is_return, 0) = 0
            """,
            (row.so_detail, doc.name or ""),
        )[0][0] or 0

        current_invoice_qty = sum(
            flt(item.qty)
            for item in doc.items
            if item.so_detail == row.so_detail
            and item.sales_order == row.sales_order
        )

        total_qty = flt(already_invoiced) + flt(current_invoice_qty)

        if total_qty > flt(ordered_qty):
            remaining_qty = max(
                flt(ordered_qty) - flt(already_invoiced),
                0
            )

            frappe.throw(
                _(
                    "Sales Order {0}, Item {1}: Ordered Qty is {2}, "
                    "already invoiced Qty is {3}, and remaining Qty is {4}. "
                    "You cannot invoice Qty {5}."
                ).format(
                    frappe.bold(row.sales_order),
                    frappe.bold(row.item_code),
                    flt(ordered_qty),
                    flt(already_invoiced),
                    flt(remaining_qty),
                    flt(current_invoice_qty),
                ),
                title=_("Sales Order Quantity Exceeded"),
            )


@frappe.whitelist()
def revise_sales_order_quantity(
    sales_order,
    item_row,
    new_qty,
    reason,
    revised_po_reference=None,
):
    """
    Controlled quantity increase for a submitted Sales Order.
    Uses ERPNext's standard update_child_qty_rate mechanism.
    """

    import json
    from erpnext.controllers.accounts_controller import update_child_qty_rate

    if not sales_order or not item_row:
        frappe.throw(_("Sales Order and Item Row are required."))

    so = frappe.get_doc("Sales Order", sales_order)
    so.check_permission("write")

    if so.docstatus != 1:
        frappe.throw(
            _("Only a submitted Sales Order can be revised."),
            title=_("Invalid Sales Order"),
        )

    target = None
    for row in so.items:
        if row.name == item_row:
            target = row
            break

    if not target:
        frappe.throw(
            _("Selected item does not belong to Sales Order {0}.").format(
                frappe.bold(sales_order)
            )
        )

    old_qty = flt(target.qty)
    new_qty = flt(new_qty)

    if new_qty <= old_qty:
        frappe.throw(
            _("New Qty must be greater than current Qty {0}.").format(old_qty),
            title=_("Quantity Increase Required"),
        )

    if not reason or not str(reason).strip():
        frappe.throw(_("Reason for revision is mandatory."))

    # Send ALL existing SO rows to ERPNext's standard updater.
    # Only the selected row gets a changed quantity.
    trans_items = []

    for row in so.items:
        qty = new_qty if row.name == target.name else flt(row.qty)

        trans_items.append(
            {
                "item_code": row.item_code,
                "rate": flt(row.rate),
                "qty": qty,
                "docname": row.name,
                "conversion_factor": flt(row.conversion_factor),
            }
        )

    update_child_qty_rate(
        "Sales Order",
        json.dumps(trans_items),
        so.name,
    )

    so.reload()

    reference_text = (
        str(revised_po_reference).strip()
        if revised_po_reference
        else "-"
    )

    comment = _(
        "Sales Order quantity revised for Item {0}: {1} → {2}. "
        "Revised PO/Reference: {3}. Reason: {4}"
    ).format(
        frappe.bold(target.item_code),
        old_qty,
        new_qty,
        frappe.bold(reference_text),
        frappe.utils.escape_html(str(reason).strip()),
    )

    so.add_comment("Info", comment)

    return {
        "sales_order": so.name,
        "item_row": target.name,
        "item_code": target.item_code,
        "old_qty": old_qty,
        "new_qty": new_qty,
        "revised_po_reference": reference_text,
    }
