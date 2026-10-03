import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


WORKFLOW_NAME = "Material Request Approval"


def ensure_custom_fields():
    create_custom_fields(
        {
            "Material Request": [
                {
                    "fieldname": "custom_project",
                    "label": "Project",
                    "fieldtype": "Link",
                    "options": "Project",
                    "insert_after": "transaction_date",
                    "reqd": 1,
                }
            ],
            "Material Request Item": [
                {
                    "fieldname": "custom_approved_qty",
                    "label": "Approved Qty",
                    "fieldtype": "Float",
                    "insert_after": "qty",
                    "in_list_view": 1,
                    "read_only": 1,
                    "description": "Quantity approved by Project Manager",
                }
            ],
            "Project": [
                {
                    "fieldname": "custom_project_manager",
                    "label": "Project Manager",
                    "fieldtype": "Link",
                    "options": "User",
                    "insert_after": "project_name",
                }
            ],
        },
        update=True,
    )


def ensure_workflow_state(name):
    if not frappe.db.exists("Workflow State", name):
        doc = frappe.new_doc("Workflow State")
        doc.workflow_state_name = name
        doc.insert(ignore_permissions=True)


def ensure_workflow_action(name):
    if not frappe.db.exists("Workflow Action Master", name):
        doc = frappe.new_doc("Workflow Action Master")
        doc.workflow_action_name = name
        doc.insert(ignore_permissions=True)


def setup_material_request_workflow():
    ensure_custom_fields()

    for state in [
        "Draft",
        "Pending PM Approval",
        "Approved",
        "Rejected",
    ]:
        ensure_workflow_state(state)

    for action in [
        "Send for Approval",
        "Approve",
        "Reject",
    ]:
        ensure_workflow_action(action)

    existing = frappe.db.exists("Workflow", WORKFLOW_NAME)

    if existing:
        workflow = frappe.get_doc("Workflow", existing)
    else:
        workflow = frappe.new_doc("Workflow")
        workflow.workflow_name = WORKFLOW_NAME

    workflow.document_type = "Material Request"
    workflow.is_active = 1
    workflow.override_status = 0
    workflow.send_email_alert = 0
    workflow.workflow_state_field = "workflow_state"

    workflow.set(
        "states",
        [
            {
                "state": "Draft",
                "doc_status": "0",
                "allow_edit": "Projects User",
            },
            {
                "state": "Pending PM Approval",
                "doc_status": "0",
                "allow_edit": "Projects Manager",
            },
            {
                "state": "Approved",
                "doc_status": "1",
                "allow_edit": "Projects Manager",
            },
            {
                "state": "Rejected",
                "doc_status": "0",
                "allow_edit": "Projects User",
            },
        ],
    )

    workflow.set(
        "transitions",
        [
            {
                "state": "Draft",
                "action": "Send for Approval",
                "next_state": "Pending PM Approval",
                "allowed": "Projects User",
                "allow_self_approval": 0,
            },
            {
                "state": "Pending PM Approval",
                "action": "Approve",
                "next_state": "Approved",
                "allowed": "Projects Manager",
                "allow_self_approval": 0,
            },
            {
                "state": "Pending PM Approval",
                "action": "Reject",
                "next_state": "Rejected",
                "allowed": "Projects Manager",
                "allow_self_approval": 0,
            },
            {
                "state": "Rejected",
                "action": "Send for Approval",
                "next_state": "Pending PM Approval",
                "allowed": "Projects User",
                "allow_self_approval": 0,
            },
        ],
    )

    workflow.save(ignore_permissions=True)
    frappe.db.commit()

    print("DONE: Material Request setup completed.")
