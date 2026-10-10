import frappe
from frappe.permissions import (
    add_permission,
    update_permission_property,
)


ROLE_PERMISSIONS = {
    "NAVE Material Request User": {
        "read": 1,
        "write": 1,
        "create": 1,
        "submit": 0,
        "cancel": 0,
        "delete": 0,
    },
    "NAVE Material Request Approver": {
        "read": 1,
        "write": 1,
        "create": 0,
        "submit": 1,
        "cancel": 0,
        "delete": 0,
    },
}


def setup_material_request_permissions():
    for role_name, permissions in ROLE_PERMISSIONS.items():

        if not frappe.db.exists("Role", role_name):
            role = frappe.new_doc("Role")
            role.role_name = role_name
            role.desk_access = 1
            role.insert(ignore_permissions=True)

        exists = frappe.db.exists(
            "Custom DocPerm",
            {
                "parent": "Material Request",
                "role": role_name,
                "permlevel": 0,
            },
        )

        if not exists:
            add_permission(
                "Material Request",
                role_name,
                permlevel=0,
            )

        for permission, value in permissions.items():
            update_permission_property(
                "Material Request",
                role_name,
                0,
                permission,
                value,
                validate=False,
            )

    frappe.clear_cache(doctype="Material Request")

    print("DONE: Material Request role permissions configured.")
