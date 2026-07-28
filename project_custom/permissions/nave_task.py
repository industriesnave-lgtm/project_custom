import frappe


MANAGER_ROLE = "NAVE Task Manager"


def _roles(user):
    return frappe.get_roles(user)


def _is_admin(user):
    roles = _roles(user)
    return user == "Administrator" or "System Manager" in roles


def _employee_department(user):
    return frappe.db.get_value(
        "Employee",
        {"user_id": user, "status": "Active"},
        "department",
    )


def get_task_query_conditions(user=None):
    user = user or frappe.session.user

    if not user or user == "Guest":
        return "1=0"

    if _is_admin(user):
        return ""

    escaped_user = frappe.db.escape(user)
    roles = _roles(user)

    if MANAGER_ROLE in roles:
        department = _employee_department(user)

        if department:
            escaped_department = frappe.db.escape(department)
            return (
                f"(`tabNAVE Task`.`assigned_to` = {escaped_user} "
                f"OR `tabNAVE Task`.`department` = {escaped_department})"
            )

    return f"`tabNAVE Task`.`assigned_to` = {escaped_user}"


def has_task_permission(doc, user=None, permission_type=None):
    user = user or frappe.session.user

    if not user or user == "Guest":
        return False

    if _is_admin(user):
        return True

    if doc.assigned_to == user:
        return True

    roles = _roles(user)

    if MANAGER_ROLE in roles:
        department = _employee_department(user)
        return bool(department and doc.department == department)

    return False


def get_update_query_conditions(user=None):
    user = user or frappe.session.user

    if not user or user == "Guest":
        return "1=0"

    if _is_admin(user):
        return ""

    escaped_user = frappe.db.escape(user)
    roles = _roles(user)

    if MANAGER_ROLE in roles:
        department = _employee_department(user)

        if department:
            escaped_department = frappe.db.escape(department)
            return f"""
                EXISTS (
                    SELECT 1
                    FROM `tabNAVE Task`
                    WHERE `tabNAVE Task`.`name` = `tabNAVE Task Update`.`task`
                    AND (
                        `tabNAVE Task`.`assigned_to` = {escaped_user}
                        OR `tabNAVE Task`.`department` = {escaped_department}
                    )
                )
            """

    return f"""
        EXISTS (
            SELECT 1
            FROM `tabNAVE Task`
            WHERE `tabNAVE Task`.`name` = `tabNAVE Task Update`.`task`
            AND `tabNAVE Task`.`assigned_to` = {escaped_user}
        )
    """


def has_update_permission(doc, user=None, permission_type=None):
    if not doc.task:
        return False

    task = frappe.get_doc("NAVE Task", doc.task)
    return has_task_permission(task, user, permission_type)
