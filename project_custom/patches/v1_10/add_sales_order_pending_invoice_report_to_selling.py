import frappe


REPORT_NAME = "Sales Order Pending Invoice - Item Wise"


def execute():
    if not frappe.db.exists("Workspace Sidebar", "Selling"):
        return

    sidebar = frappe.get_doc("Workspace Sidebar", "Selling")

    # Do not create duplicate links.
    for item in sidebar.items:
        if (
            item.type == "Link"
            and item.link_type == "Report"
            and item.link_to == REPORT_NAME
        ):
            return

    # Find the Reports section.
    reports_section_index = None

    for index, item in enumerate(sidebar.items):
        if item.type == "Section Break" and item.label == "Reports":
            reports_section_index = index
            break

    if reports_section_index is None:
        frappe.throw("Reports section not found in Selling Workspace Sidebar")

    # Insert before the next top-level item after Reports
    # (currently this is Settings).
    insert_at = len(sidebar.items)

    for index in range(reports_section_index + 1, len(sidebar.items)):
        if not sidebar.items[index].child:
            insert_at = index
            break

    sidebar.append(
        "items",
        {
            "child": 1,
            "collapsible": 1,
            "icon": "table",
            "indent": 0,
            "keep_closed": 0,
            "label": REPORT_NAME,
            "link_to": REPORT_NAME,
            "link_type": "Report",
            "show_arrow": 0,
            "type": "Link",
        },
    )

    new_item = sidebar.items.pop()
    sidebar.items.insert(insert_at, new_item)

    # Rebuild child table order.
    for idx, item in enumerate(sidebar.items, start=1):
        item.idx = idx

    sidebar.save(ignore_permissions=True)
