import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def ensure_billing_type():
    """Ensure Sales Order Billing Type exists."""
    create_custom_fields({
        "Sales Order": [
            {
                "fieldname": "custom_billing_type",
                "label": "Billing Type",
                "fieldtype": "Select",
                "options": "\nService\nSupply",
                "insert_after": "customer_name",
                "allow_on_submit": 1,
                "reqd": 0,
                "description": "Classify Sales Order as Service or Supply.",
            }
        ]
    })


def execute():
    ensure_billing_type()
