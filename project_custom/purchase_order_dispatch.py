import frappe
from frappe import _
from frappe.utils import cint


def set_supplier_dispatch_address(doc, method=None):
    """
    Automatically set Purchase Order Dispatch Address from the
    selected Supplier's linked Address.

    Priority:
    1. Primary Supplier Address
    2. First linked Supplier Address
    """

    if not doc.supplier:
        return

    # Respect an address already selected manually.
    if doc.dispatch_address:
        return

    linked_addresses = frappe.get_all(
        "Dynamic Link",
        filters={
            "link_doctype": "Supplier",
            "link_name": doc.supplier,
            "parenttype": "Address",
        },
        fields=["parent"],
    )

    if not linked_addresses:
        frappe.throw(
            _(
                "No Address is linked with Supplier {0}. "
                "Please add a Supplier Address before creating the Purchase Order."
            ).format(frappe.bold(doc.supplier)),
            title=_("Supplier Address Required"),
        )

    address_names = [row.parent for row in linked_addresses]

    addresses = frappe.get_all(
        "Address",
        filters={
            "name": ["in", address_names],
            "disabled": 0,
        },
        fields=[
            "name",
            "is_primary_address",
            "modified",
        ],
        order_by="is_primary_address desc, modified desc",
    )

    if not addresses:
        frappe.throw(
            _("No active Address found for Supplier {0}.").format(
                frappe.bold(doc.supplier)
            ),
            title=_("Supplier Address Required"),
        )

    primary_addresses = [
        row for row in addresses if cint(row.is_primary_address)
    ]

    selected_address = (
        primary_addresses[0]
        if primary_addresses
        else addresses[0]
    )

    doc.dispatch_address = selected_address.name

    # Populate formatted Dispatch Address Details using ERPNext/Frappe
    # standard address display.
    from frappe.contacts.doctype.address.address import get_address_display

    doc.dispatch_address_display = get_address_display(
        selected_address.name
    )
