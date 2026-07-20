import frappe


def after_install():
    if frappe.db.exists("Custom Field", {"dt": "Journal Entry", "fieldname": "project"}):
        return

    frappe.get_doc(
        {
            "doctype": "Custom Field",
            "dt": "Journal Entry",
            "label": "Project",
            "fieldname": "project",
            "fieldtype": "Link",
            "options": "Project",
            "insert_after": "posting_date",
            "allow_on_submit": 1,
        }
    ).insert(ignore_permissions=True)
