import frappe


ACCOUNTS_EMAIL = "accounts@naveindustries.com"


def handle_expense_claim_update(doc, method=None):
    if not doc.has_value_changed("workflow_state"):
        return

    if doc.workflow_state == "Pending Admin":
        _send_to_admin_manager(doc)

    elif doc.workflow_state == "Pending Expense Approver":
        _send_to_expense_approver(doc)

    elif doc.workflow_state == "Pending Accounts Payment":
        _send_mail(
            doc,
            [ACCOUNTS_EMAIL],
            "Expense Claim Pending Accounts Payment",
        )


def _send_to_admin_manager(doc):
    recipients = frappe.get_all(
        "Has Role",
        filters={
            "role": "Admin Manager",
            "parenttype": "User",
        },
        pluck="parent",
    )

    recipients = _enabled_email_users(recipients)

    if recipients:
        _send_mail(
            doc,
            recipients,
            "Expense Claim Pending Admin Verification",
        )


def _send_to_expense_approver(doc):
    approver = None

    if doc.employee:
        approver = frappe.db.get_value(
            "Employee",
            doc.employee,
            "expense_approver",
        )

    if not approver:
        approver = doc.expense_approver

    if not approver:
        frappe.log_error(
            f"No Expense Approver found for Employee {doc.employee}",
            "Expense Claim Workflow Email",
        )
        return

    recipients = _enabled_email_users([approver])

    if recipients:
        _send_mail(
            doc,
            recipients,
            "Expense Claim Pending Your Approval",
        )


def _enabled_email_users(users):
    recipients = []

    for user in set(users or []):
        if not user or user == "Administrator":
            continue

        enabled = frappe.db.get_value(
            "User",
            user,
            "enabled",
        )

        if enabled:
            recipients.append(user)

    return recipients


def _send_mail(doc, recipients, subject):
    if not recipients:
        return

    employee_name = doc.employee_name or doc.employee or ""

    message = f"""
        <p>Dear Sir/Madam,</p>

        <p>Expense Claim <b>{doc.name}</b> requires your attention.</p>

        <p>
            Employee: <b>{employee_name}</b><br>
            Workflow Status: <b>{doc.workflow_state}</b><br>
            Total Claim Amount: <b>{doc.grand_total}</b>
        </p>

        <p>
            <a href="{frappe.utils.get_url_to_form('Expense Claim', doc.name)}">
                Open Expense Claim
            </a>
        </p>
    """

    frappe.sendmail(
        recipients=recipients,
        subject=subject,
        message=message,
        reference_doctype="Expense Claim",
        reference_name=doc.name,
    )
