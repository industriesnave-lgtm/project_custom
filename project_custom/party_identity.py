import re

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


GSTIN_PATTERN = re.compile(
    r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$"
)


def setup_party_identity_fields():
    custom_fields = {
        "Supplier": [
            {
                "fieldname": "custom_gstin",
                "label": "GSTIN",
                "fieldtype": "Data",
                "insert_after": "supplier_name",
                "reqd": 1,
                "unique": 1,
                "description": "Enter the 15-character GSTIN.",
            }
        ],
        "Customer": [
            {
                "fieldname": "custom_gstin",
                "label": "GSTIN",
                "fieldtype": "Data",
                "insert_after": "customer_name",
                "reqd": 1,
                "unique": 1,
                "description": "Enter the 15-character GSTIN.",
            }
        ],
    }

    create_custom_fields(custom_fields, update=True)


def normalize_gstin(value):
    return str(value or "").strip().upper().replace(" ", "")


def validate_party_gstin(doc, method=None):
    gstin = normalize_gstin(doc.get("custom_gstin"))

    if not gstin:
        frappe.throw("GSTIN is mandatory.")

    if not GSTIN_PATTERN.fullmatch(gstin):
        frappe.throw(
            "Please enter a valid 15-character GSTIN."
        )

    doc.custom_gstin = gstin
