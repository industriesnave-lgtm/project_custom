import frappe
from frappe.utils import cint, flt, now_datetime


MANAGER_ROLE = "NAVE Task Manager"


def get_roles():
    return frappe.get_roles(frappe.session.user)


def is_admin():
    roles = get_roles()
    return (
        frappe.session.user == "Administrator"
        or "System Manager" in roles
    )


def is_task_manager():
    return MANAGER_ROLE in get_roles()


def get_employee():
    return frappe.db.get_value(
        "Employee",
        {
            "user_id": frappe.session.user,
            "status": "Active",
        },
        ["name", "department"],
        as_dict=True,
    )


def get_task_for_user(task_name):
    task = frappe.get_doc("NAVE Task", task_name)

    if is_admin():
        return task

    if task.assigned_to == frappe.session.user:
        return task

    employee = get_employee()

    if (
        is_task_manager()
        and employee
        and employee.department
        and task.department == employee.department
    ):
        return task

    frappe.throw(
        "You are not permitted to access this task.",
        frappe.PermissionError,
    )


@frappe.whitelist()
def has_app_permission():
    return frappe.session.user != "Guest"


@frappe.whitelist()
def get_my_tasks():
    if frappe.session.user == "Guest":
        frappe.throw("Please log in.", frappe.PermissionError)

    filters = {}

    if not is_admin():
        employee = get_employee()

        if is_task_manager() and employee and employee.department:
            filters["department"] = employee.department
        else:
            filters["assigned_to"] = frappe.session.user

    return frappe.get_all(
        "NAVE Task",
        filters=filters,
        fields=[
            "name",
            "subject",
            "description",
            "category",
            "priority",
            "status",
            "progress",
            "assigned_to",
            "assigned_employee",
            "assigned_by",
            "department",
            "company",
            "project",
            "site",
            "start_date",
            "due_date",
            "is_overdue",
            "latest_update",
            "pending_reason",
            "support_required",
            "modified",
        ],
        order_by="is_overdue desc, due_date asc, modified desc",
        limit_page_length=200,
    )


@frappe.whitelist()
def submit_update(
    task_name,
    status,
    progress,
    update_text,
    pending_reason=None,
    support_required=0,
    attachment=None,
):
    if frappe.session.user == "Guest":
        frappe.throw("Please log in.", frappe.PermissionError)

    task = get_task_for_user(task_name)
    progress = flt(progress)

    if status not in ("Open", "Working", "Pending", "Completed"):
        frappe.throw("Invalid task status.")

    if progress < 0 or progress > 100:
        frappe.throw("Progress must be between 0 and 100.")

    if not (update_text or "").strip():
        frappe.throw("Please enter your progress update.")

    if status == "Pending" and not (pending_reason or "").strip():
        frappe.throw("Pending Reason is required.")

    if status == "Completed":
        progress = 100

    employee = get_employee()

    update = frappe.get_doc(
        {
            "doctype": "NAVE Task Update",
            "task": task.name,
            "update_by": frappe.session.user,
            "employee": employee.name if employee else None,
            "updated_on": now_datetime(),
            "status": status,
            "progress": progress,
            "update_text": update_text.strip(),
            "pending_reason": (pending_reason or "").strip(),
            "support_required": cint(support_required),
            "attachment": attachment,
        }
    )
    update.insert(ignore_permissions=True)

    task.db_set("status", status, update_modified=False)
    task.db_set("progress", progress, update_modified=False)
    task.db_set(
        "latest_update",
        update_text.strip(),
        update_modified=False,
    )
    task.db_set(
        "pending_reason",
        (pending_reason or "").strip(),
        update_modified=False,
    )
    task.db_set(
        "support_required",
        cint(support_required),
        update_modified=True,
    )

    return {
        "ok": True,
        "task": task.name,
        "update": update.name,
        "status": status,
        "progress": progress,
    }
