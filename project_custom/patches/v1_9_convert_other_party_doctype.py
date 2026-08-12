import frappe


def execute():
    if not frappe.db.exists("DocType", "Other Party"):
        return

    custom = frappe.db.get_value("DocType", "Other Party", "custom")

    # Production may already have Other Party as a Custom DocType.
    # Convert only its metadata to an app-managed DocType.
    # Existing records in `tabOther Party` are preserved.
    if custom:
        frappe.db.set_value(
            "DocType",
            "Other Party",
            {
                "custom": 0,
                "module": "Project Custom",
                "autoname": "field:party_name",
                "title_field": "party_name",
            },
            update_modified=False,
        )

        frappe.clear_cache(doctype="Other Party")
