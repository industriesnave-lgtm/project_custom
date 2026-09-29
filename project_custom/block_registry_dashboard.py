import frappe


@frappe.whitelist()
def get_dashboard_data():
    frappe.only_for("System Manager")

    doctype = "NAVE Block Registry"

    active = frappe.db.count(
        doctype,
        {"status": "Active"},
    )

    persons = frappe.db.count(
        doctype,
        {
            "status": "Active",
            "party_type": "Person",
        },
    )

    suppliers = frappe.db.count(
        doctype,
        {
            "status": "Active",
            "party_type": "Supplier / Vendor",
        },
    )

    customers = frappe.db.count(
        doctype,
        {
            "status": "Active",
            "party_type": "Customer",
        },
    )

    revoked = frappe.db.count(
        doctype,
        {"status": "Revoked"},
    )

    recent = frappe.get_all(
        doctype,
        fields=[
            "name",
            "party_name",
            "party_type",
            "status",
            "reason_category",
            "block_date",
            "modified",
        ],
        order_by="modified desc",
        limit_page_length=10,
    )

    return {
        "active": active,
        "persons": persons,
        "suppliers": suppliers,
        "customers": customers,
        "revoked": revoked,
        "recent": recent,
    }
