import frappe
from frappe import _
from frappe.utils import flt


def _get_previous_state(doc):
    old_doc = doc.get_doc_before_save()
    return old_doc.workflow_state if old_doc else None


def _get_project_manager(doc):
    if not doc.custom_project:
        frappe.throw(_("Project is mandatory."))

    project_manager = frappe.db.get_value(
        "Project",
        doc.custom_project,
        "custom_project_manager",
    )

    if not project_manager:
        frappe.throw(
            _("Project Manager is not assigned in Project {0}.").format(
                doc.custom_project
            )
        )

    return project_manager


def _require_assigned_project_manager(doc):
    project_manager = _get_project_manager(doc)

    if frappe.session.user != project_manager:
        frappe.throw(
            _(
                "Only the assigned Project Manager ({0}) "
                "can update or approve this Material Request."
            ).format(project_manager)
        )

    return project_manager


def set_project_on_items(doc, method=None):
    """
    Material Request controls:
    1. Header Project -> Item Project
    2. Validate Approved Qty
    3. Pending request can only be edited by assigned PM
    4. Only assigned PM can Approve / Reject
    """

    previous_state = _get_previous_state(doc)
    current_state = doc.workflow_state
    old_doc = doc.get_doc_before_save()

    if not doc.custom_project:
        frappe.throw(_("Project is mandatory."))

    if old_doc and previous_state == "Pending PM Approval":
        if doc.custom_project != old_doc.custom_project:
            frappe.throw(
                _("Project cannot be changed after sending for approval.")
            )

        old_items = {item.name: item for item in old_doc.items}
        new_items = {item.name: item for item in doc.items}

        if set(old_items) != set(new_items):
            frappe.throw(
                _("Items cannot be added or removed during PM approval.")
            )

        for item in doc.items:
            old_item = old_items[item.name]
            if (
                item.item_code != old_item.item_code
                or flt(item.qty) != flt(old_item.qty)
            ):
                frappe.throw(
                    _("Item and Requested Qty cannot change during PM approval.")
                )

    if current_state in ("Draft", "Rejected", "Pending PM Approval"):
        if current_state != "Pending PM Approval" or (
            previous_state != "Pending PM Approval"
        ):
            if old_doc:
                old_qty = {
                    item.name: flt(item.custom_approved_qty)
                    for item in old_doc.items
                }
                for item in doc.items:
                    if flt(item.custom_approved_qty) != old_qty.get(item.name, 0):
                        frappe.throw(
                            _("Only the assigned PM can change Approved Qty.")
                        )
            else:
                for item in doc.items:
                    if flt(item.custom_approved_qty):
                        frappe.throw(
                            _("Approved Qty must be zero when creating a request.")
                        )

    # ---------------------------------------------------------
    # 1. Header Project -> Item Project
    # ---------------------------------------------------------
    if doc.custom_project:
        for item in doc.items:
            item.project = doc.custom_project

    # ---------------------------------------------------------
    # 2. Validate Approved Qty
    # ---------------------------------------------------------
    for item in doc.items:
        approved_qty = flt(item.custom_approved_qty)
        requested_qty = flt(item.qty)

        if approved_qty < 0:
            frappe.throw(
                _("Approved Qty cannot be negative for item {0}.").format(
                    item.item_code
                )
            )

        if approved_qty > requested_qty:
            frappe.throw(
                _(
                    "Approved Qty ({0}) cannot be greater than "
                    "Requested Qty ({1}) for item {2}."
                ).format(
                    approved_qty,
                    requested_qty,
                    item.item_code,
                )
            )

    # ---------------------------------------------------------
    # 3. Draft -> Pending:
    #    Projects User may send request.
    #    But Project must have assigned PM.
    # ---------------------------------------------------------
    if (
        current_state == "Pending PM Approval"
        and previous_state != "Pending PM Approval"
    ):
        _get_project_manager(doc)

    # ---------------------------------------------------------
    # 4. Already Pending:
    #    only assigned PM may edit/save
    # ---------------------------------------------------------
    if (
        current_state == "Pending PM Approval"
        and previous_state == "Pending PM Approval"
    ):
        _require_assigned_project_manager(doc)

    # ---------------------------------------------------------
    # 5. Pending -> Approved / Rejected:
    #    only assigned PM may perform action
    # ---------------------------------------------------------
    if (
        previous_state == "Pending PM Approval"
        and current_state in ("Approved", "Rejected")
    ):
        _require_assigned_project_manager(doc)

    # ---------------------------------------------------------
    # 6. Approved:
    #    Approved Qty required for every item
    # ---------------------------------------------------------
    if current_state == "Approved":
        for item in doc.items:
            if flt(item.custom_approved_qty) <= 0:
                frappe.throw(
                    _(
                        "Please enter Approved Qty for item {0} before approval."
                    ).format(item.item_code)
                )


def send_material_request_workflow_email(doc, method=None):
    """
    Send email only when workflow state actually changes.

    Pending PM Approval:
        -> Assigned Project Manager

    Approved:
        -> Material Request creator
        -> Enabled users having Purchase Manager role
    """

    previous_state = _get_previous_state(doc)
    current_state = doc.workflow_state

    if not current_state or current_state == previous_state:
        return

    # ---------------------------------------------------------
    # Send for Approval -> Project Manager
    # ---------------------------------------------------------
    if current_state == "Pending PM Approval":
        project_manager = _get_project_manager(doc)

        recipients = [project_manager]

        subject = _(
            "Material Request {0} - Approval Required"
        ).format(doc.name)

        message = _build_material_request_email(
            doc,
            heading="Material Request Approval Required",
        )

        frappe.sendmail(
            recipients=recipients,
            subject=subject,
            message=message,
            reference_doctype=doc.doctype,
            reference_name=doc.name,
        )

    # ---------------------------------------------------------
    # Approved -> Creator + Purchase Manager
    # ---------------------------------------------------------
    elif current_state == "Approved":

        recipients = set()

        if doc.owner and doc.owner != "Administrator":
            recipients.add(doc.owner)

        purchase_managers = frappe.get_all(
            "Has Role",
            filters={
                "role": "Purchase Manager",
                "parenttype": "User",
            },
            pluck="parent",
        )

        if purchase_managers:
            enabled_users = frappe.get_all(
                "User",
                filters={
                    "name": ["in", purchase_managers],
                    "enabled": 1,
                },
                pluck="name",
            )

            recipients.update(enabled_users)

        recipients.discard("Administrator")
        recipients.discard("Guest")

        if not recipients:
            return

        subject = _(
            "Material Request {0} Approved - Purchase Action Required"
        ).format(doc.name)

        message = _build_material_request_email(
            doc,
            heading="Material Request Approved",
        )

        frappe.sendmail(
            recipients=list(recipients),
            subject=subject,
            message=message,
            reference_doctype=doc.doctype,
            reference_name=doc.name,
        )


def _build_material_request_email(doc, heading):
    rows = []

    for item in doc.items:
        rows.append(
            """
            <tr>
                <td style="padding:8px;border:1px solid #ddd;">{item_code}</td>
                <td style="padding:8px;border:1px solid #ddd;">{description}</td>
                <td style="padding:8px;border:1px solid #ddd;text-align:right;">{requested_qty}</td>
                <td style="padding:8px;border:1px solid #ddd;text-align:right;">{approved_qty}</td>
            </tr>
            """.format(
                item_code=frappe.utils.escape_html(item.item_code or ""),
                description=frappe.utils.escape_html(
                    frappe.utils.strip_html(
                        item.description or item.item_name or ""
                    )
                ),
                requested_qty=flt(item.qty),
                approved_qty=flt(item.custom_approved_qty),
            )
        )

    document_link = frappe.utils.get_url_to_form(doc.doctype, doc.name)

    return """
        <p>Dear Sir/Madam,</p>

        <p><strong>{heading}</strong></p>

        <p>
            <strong>Material Request:</strong> {mr}<br>
            <strong>Project:</strong> {project}<br>
            <strong>Requested By:</strong> {requested_by}
        </p>

        <table style="border-collapse:collapse;width:100%;">
            <thead>
                <tr>
                    <th style="padding:8px;border:1px solid #ddd;text-align:left;">Item</th>
                    <th style="padding:8px;border:1px solid #ddd;text-align:left;">Description</th>
                    <th style="padding:8px;border:1px solid #ddd;text-align:right;">Requested Qty</th>
                    <th style="padding:8px;border:1px solid #ddd;text-align:right;">Approved Qty</th>
                </tr>
            </thead>
            <tbody>
                {rows}
            </tbody>
        </table>

        <p>
            <a href="{document_link}">Open Material Request</a>
        </p>

        <p>Regards,<br>NAVE INDUSTRIES PRIVATE LIMITED</p>
    """.format(
        heading=frappe.utils.escape_html(heading),
        mr=frappe.utils.escape_html(doc.name),
        project=frappe.utils.escape_html(doc.custom_project or ""),
        requested_by=frappe.utils.escape_html(doc.owner or ""),
        rows="".join(rows),
        document_link=document_link,
    )
