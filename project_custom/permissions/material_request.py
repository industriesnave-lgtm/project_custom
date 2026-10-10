import frappe


USER_ROLE = "NAVE Material Request User"
APPROVER_ROLE = "NAVE Material Request Approver"

PURCHASE_STOCK_ROLES = {
    "Purchase Manager",
    "Purchase User",
    "Stock User",
    "Stock Manager",
}


def get_material_request_query_conditions(user=None, doctype=None):
    user = user or frappe.session.user

    if user == "Administrator":
        return ""

    roles = set(frappe.get_roles(user))
    escaped_user = frappe.db.escape(user)
    conditions = []

    if USER_ROLE in roles:
        conditions.append(
            f"`tabMaterial Request`.`owner` = {escaped_user}"
        )

    if APPROVER_ROLE in roles:
        conditions.append(
            "`tabMaterial Request`.`custom_project` IN ("
            "SELECT name FROM `tabProject` "
            f"WHERE custom_project_manager = {escaped_user})"
        )

    if roles.intersection(PURCHASE_STOCK_ROLES):
        conditions.append(
            "`tabMaterial Request`.`workflow_state` = 'Approved'"
        )

    if not conditions:
        return "1 = 0"

    return "(" + " OR ".join(conditions) + ")"


def has_material_request_permission(
    doc, ptype=None, user=None, debug=False
):
    user = user or frappe.session.user

    if user == "Administrator":
        return True

    roles = set(frappe.get_roles(user))
    if ptype == "create":
        return USER_ROLE in roles

    if doc is None:
        return False

    state = doc.workflow_state

    is_owner = USER_ROLE in roles and doc.owner == user

    is_assigned_pm = (
        APPROVER_ROLE in roles
        and bool(doc.custom_project)
        and frappe.db.get_value(
            "Project",
            doc.custom_project,
            "custom_project_manager",
        ) == user
    )

    is_purchase_stock = (
        bool(roles.intersection(PURCHASE_STOCK_ROLES))
        and state == "Approved"
    )

    if ptype in ("read", "select"):
        return is_owner or is_assigned_pm or is_purchase_stock

    if ptype == "write":
        old_doc = doc.get_doc_before_save()
        old_state = (
            old_doc.workflow_state
            if old_doc
            else frappe.db.get_value(
                "Material Request", doc.name, "workflow_state"
            ) if doc.name and not doc.is_new() else state
        )

        if old_state in ("Draft", "Rejected"):
            return is_owner and state in (
                "Draft", "Rejected", "Pending PM Approval"
            )

        if old_state == "Pending PM Approval":
            return is_assigned_pm and state in (
                "Pending PM Approval", "Approved", "Rejected"
            )

        return False

    if ptype == "submit":
        return is_assigned_pm and state == "Approved"

    if ptype == "create":
        return USER_ROLE in roles

    if ptype in ("delete", "cancel", "amend"):
        return False

    return None
