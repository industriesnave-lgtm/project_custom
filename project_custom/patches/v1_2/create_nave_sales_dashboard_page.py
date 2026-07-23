import frappe


def execute():
    if frappe.db.exists("Page", "nave-sales-dashboard"):
        return

    frappe.get_doc(
        {
            "doctype": "Page",
            "page_name": "nave-sales-dashboard",
            "title": "Sales Dashboard",
            "module": "Project Custom",
            "standard": "Yes",
            "roles": [
                {"role": "Sales User"},
                {"role": "Sales Manager"},
                {"role": "System Manager"},
            ],
        }
    ).insert(ignore_permissions=True)
