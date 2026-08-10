import frappe


def execute():
    if frappe.db.exists("Party Type", "Other Party"):
        frappe.db.set_value(
            "Party Type",
            "Other Party",
            "account_type",
            "Payable",
            update_modified=False,
        )
        return

    frappe.get_doc(
        {
            "doctype": "Party Type",
            "party_type": "Other Party",
            "account_type": "Payable",
        }
    ).insert(ignore_permissions=True)
