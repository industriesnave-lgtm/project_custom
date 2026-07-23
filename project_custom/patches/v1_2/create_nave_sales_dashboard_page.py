import frappe


def execute():
    if frappe.db.exists("Page", "nave-sales-dashboard"):
        return

    previous_developer_mode = frappe.conf.get("developer_mode")
    frappe.conf.developer_mode = 1

    try:
        page = frappe.get_doc(
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
        )
        page.flags.do_not_update_json = True
        page.insert(ignore_permissions=True)
    finally:
        frappe.conf.developer_mode = previous_developer_mode
