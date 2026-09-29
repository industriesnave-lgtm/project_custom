import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def setup_employee_custom_fields():
    custom_fields = {
        "Employee": [
            {
                "fieldname": "custom_nave_identity_section",
                "label": "NAVE Employee Identity",
                "fieldtype": "Section Break",
                "insert_after": "personal_details",
            },
            {
                "fieldname": "custom_aadhaar_number",
                "label": "Aadhaar Number",
                "fieldtype": "Data",
                "reqd": 1,
                "unique": 1,
                "insert_after": "custom_nave_identity_section",
                "description": "Enter the 12-digit Aadhaar number.",
            },
            {
                "fieldname": "custom_esic_number",
                "label": "ESIC No",
                "fieldtype": "Data",
                "insert_after": "custom_aadhaar_number",
            },
            {
                "fieldname": "custom_mothers_name",
                "label": "Mother's Name",
                "fieldtype": "Data",
                "reqd": 1,
                "insert_after": "custom_esic_number",
            },
        ]
    }

    create_custom_fields(
        custom_fields,
        update=True,
    )


def validate_employee(doc, method=None):
    aadhaar = str(
        doc.get("custom_aadhaar_number") or ""
    ).strip()

    if not aadhaar:
        frappe.throw("Aadhaar Number is mandatory.")

    if not aadhaar.isdigit() or len(aadhaar) != 12:
        frappe.throw(
            "Aadhaar Number must contain exactly 12 numeric digits."
        )

    doc.custom_aadhaar_number = aadhaar

    mothers_name = (
        doc.get("custom_mothers_name") or ""
    ).strip()

    if not mothers_name:
        frappe.throw("Mother's Name is mandatory.")

    doc.custom_mothers_name = mothers_name
