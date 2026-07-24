import frappe
from frappe.utils import escape_html, getdate


ALLOWED_FIELDS = {
    "Sales Invoice": {
        "due_date": "Due Date",
        "remarks": "Remarks",
        "po_no": "Customer PO No",
    },
    "Purchase Invoice": {
        "due_date": "Due Date",
        "remarks": "Remarks",
        "bill_no": "Supplier Bill No",
    },
}


def require_super_user():
    if frappe.session.user != "Administrator" and not frappe.has_role("System Manager"):
        frappe.throw("Only System Manager can edit a submitted invoice.", frappe.PermissionError)


def get_allowed_fields(doctype):
    if doctype not in ALLOWED_FIELDS:
        frappe.throw("Only Sales Invoice and Purchase Invoice are supported.")

    meta = frappe.get_meta(doctype)
    return {
        fieldname: label
        for fieldname, label in ALLOWED_FIELDS[doctype].items()
        if meta.has_field(fieldname)
    }


@frappe.whitelist()
def get_editable_invoice_fields(doctype, name):
    require_super_user()

    doc = frappe.get_doc(doctype, name)
    if doc.docstatus != 1:
        frappe.throw("Only submitted invoices can be edited.")

    allowed_fields = get_allowed_fields(doctype)

    return {
        "doctype": doctype,
        "name": name,
        "fields": [
            {
                "fieldname": fieldname,
                "label": label,
                "value": doc.get(fieldname),
            }
            for fieldname, label in allowed_fields.items()
        ],
    }


@frappe.whitelist()
def update_submitted_invoice(doctype, name, values):
    require_super_user()

    if isinstance(values, str):
        values = frappe.parse_json(values)

    if not isinstance(values, dict):
        frappe.throw("Invalid update data.")

    doc = frappe.get_doc(doctype, name)

    if doc.docstatus != 1:
        frappe.throw("Only submitted invoices can be edited.")

    allowed_fields = get_allowed_fields(doctype)
    invalid_fields = set(values) - set(allowed_fields)

    if invalid_fields:
        frappe.throw(
            "These fields cannot be edited: " + ", ".join(sorted(invalid_fields))
        )

    changes = []

    for fieldname, new_value in values.items():
        if fieldname == "due_date" and new_value:
            new_value = str(getdate(new_value))

        old_value = doc.get(fieldname)

        if str(old_value or "") == str(new_value or ""):
            continue
    doc.db_set(fieldname, new_value, update_modified=True)

