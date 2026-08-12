import frappe

from erpnext.accounts.doctype.payment_entry.payment_entry import (
    get_party_details as standard_get_party_details,
)
from erpnext.accounts.party import get_party_account


@frappe.whitelist()
def get_party_details(company, party_type, party, date, cost_center=None):
    # Keep 100% standard ERPNext behaviour for all existing party types
    if party_type != "Other Party":
        return standard_get_party_details(
            company=company,
            party_type=party_type,
            party=party,
            date=date,
            cost_center=cost_center,
        )

    # Custom handling only for Other Party
    if not frappe.db.exists("Other Party", party):
        frappe.throw(f"Other Party {party} does not exist")

    ptype = "select" if frappe.only_has_select_perm("Other Party") else "read"
    frappe.has_permission("Other Party", ptype, party, throw=True)

    party_account = get_party_account(
        "Other Party",
        party,
        company,
    )

    if not party_account:
        frappe.throw(
            f"No Payable account found for Other Party {party} in company {company}"
        )

    account_currency = (
        frappe.get_cached_value("Account", party_account, "account_currency")
        or frappe.get_cached_value("Company", company, "default_currency")
    )

    party_name = frappe.db.get_value(
        "Other Party",
        party,
        "party_name",
    )

    return {
        "party_account": party_account,
        "party_name": party_name or party,
        "party_account_currency": account_currency,
        "party_bank_account": "",
        "bank_account": "",
    }
