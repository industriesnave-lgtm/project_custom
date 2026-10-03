import frappe
from frappe import _


PURCHASE_ORDER_LIMIT = 9999


def validate_purchase_order_source(doc, method=None):
    """
    A Purchase Order must be linked to at least one
    Sales Order OR Material Request through its item rows.
    """
    has_valid_source = False

    for item in doc.items:
        if item.sales_order or item.material_request:
            has_valid_source = True
            break

    if not has_valid_source:
        frappe.throw(
            _(
                "Purchase Order cannot be created without a linked "
                "Sales Order or Material Request."
            ),
            title=_("Source Document Required"),
        )


def validate_purchase_invoice_controls(doc, method=None):
    """
    Controls:
    1. Above INR 9,999 (Base Grand Total), Purchase Order is mandatory.
    2. If Supplier Invoice/Bill Date is earlier than linked PO date,
       only Administrator may proceed.
    """

    base_grand_total = frappe.utils.flt(doc.base_grand_total)

    linked_purchase_orders = {
        item.purchase_order
        for item in doc.items
        if item.purchase_order
    }

    # PO mandatory above INR 9,999
    if base_grand_total > PURCHASE_ORDER_LIMIT and not linked_purchase_orders:
        frappe.throw(
            _(
                "Purchase Order is mandatory for Purchase Invoices "
                "above ₹9,999."
            ),
            title=_("Purchase Order Required"),
        )

    # No linked PO = no PO-date comparison required
    if not linked_purchase_orders:
        return

    # Administrator alone can bypass backdated supplier invoice restriction
    if frappe.session.user == "Administrator":
        return

    supplier_invoice_date = doc.bill_date

    if not supplier_invoice_date:
        return

    supplier_invoice_date = frappe.utils.getdate(supplier_invoice_date)

    for purchase_order in linked_purchase_orders:
        po_date = frappe.db.get_value(
            "Purchase Order",
            purchase_order,
            "transaction_date",
        )

        if po_date and supplier_invoice_date < frappe.utils.getdate(po_date):
            frappe.throw(
                _(
                    "Supplier Invoice Date {0} cannot be earlier than "
                    "Purchase Order {1} dated {2}. Only Administrator "
                    "can process this Purchase Invoice."
                ).format(
                    frappe.utils.formatdate(supplier_invoice_date),
                    frappe.bold(purchase_order),
                    frappe.utils.formatdate(po_date),
                ),
                title=_("Invoice Date Before Purchase Order"),
            )
