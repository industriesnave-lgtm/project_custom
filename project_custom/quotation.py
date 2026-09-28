import frappe
from frappe import _


@frappe.whitelist()
def create_prospect_for_quotation(
    customer_name,
    contact_person=None,
    mobile_no=None,
    email_id=None,
    gstin=None,
):
    customer_name = (customer_name or "").strip()

    if not customer_name:
        frappe.throw(_("Customer Name is required."))

    prospect = frappe.new_doc("Prospect")
    prospect.company_name = customer_name
    prospect.insert()

    details = []

    if contact_person:
        details.append("Contact Person: " + contact_person)

    if mobile_no:
        details.append("Mobile No: " + mobile_no)

    if email_id:
        details.append("Email: " + email_id)

    if gstin:
        details.append("GSTIN: " + gstin)

    if details:
        prospect.add_comment(
            "Info",
            "Quotation enquiry details:<br>" +
            "<br>".join(
                frappe.utils.escape_html(x)
                for x in details
            )
        )

    return {
        "prospect": prospect.name,
        "created": True
    }
