import frappe


def _clean(value):
    return str(value or "").strip().upper().replace(" ", "")


def get_active_block(party_type, identity_field, identity_value):
    identity_value = _clean(identity_value)

    if not identity_value:
        return None

    return frappe.db.get_value(
        "NAVE Block Registry",
        {
            "party_type": party_type,
            identity_field: identity_value,
            "status": "Active",
        },
        ["name", "party_name", "reason_category"],
        as_dict=True,
    )


def throw_blocked(block, party_label):
    if not block:
        return

    frappe.throw(
        f"{party_label} is blocked in NAVE Block Registry. "
        f"Reference: {block.name}. "
        "Please contact the System Manager."
    )


def validate_employee_block(doc, method=None):
    aadhaar = str(
        doc.get("custom_aadhaar_number") or ""
    ).strip()

    if not aadhaar:
        return

    block = get_active_block(
        "Person",
        "aadhaar_number",
        aadhaar,
    )

    throw_blocked(block, "Employee")


def validate_supplier_block(doc, method=None):
    gstin = _clean(doc.get("custom_gstin"))

    if not gstin:
        return

    block = get_active_block(
        "Supplier / Vendor",
        "gstin",
        gstin,
    )

    throw_blocked(block, "Supplier / Vendor")


def validate_customer_block(doc, method=None):
    gstin = _clean(doc.get("custom_gstin"))

    if not gstin:
        return

    block = get_active_block(
        "Customer",
        "gstin",
        gstin,
    )

    throw_blocked(block, "Customer")


def validate_supplier_transaction(doc, method=None):
    supplier = doc.get("supplier")

    if not supplier:
        return

    gstin = frappe.db.get_value(
        "Supplier",
        supplier,
        "custom_gstin",
    )

    if not gstin:
        return

    block = get_active_block(
        "Supplier / Vendor",
        "gstin",
        gstin,
    )

    throw_blocked(block, "Supplier / Vendor")


def validate_customer_transaction(doc, method=None):
    customer = doc.get("customer")

    if not customer:
        return

    gstin = frappe.db.get_value(
        "Customer",
        customer,
        "custom_gstin",
    )

    if not gstin:
        return

    block = get_active_block(
        "Customer",
        "gstin",
        gstin,
    )

    throw_blocked(block, "Customer")
