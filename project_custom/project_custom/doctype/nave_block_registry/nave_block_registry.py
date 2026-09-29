import re

import frappe
from frappe.model.document import Document
from frappe.utils import nowdate


class NAVEBlockRegistry(Document):
    def validate(self):
        self._normalize_identity()
        self._validate_identity()
        self._protect_status()
        self._set_audit_fields()
        self._check_duplicate_active_block()

    def _normalize_identity(self):
        self.aadhaar_number = str(
            self.aadhaar_number or ""
        ).strip()

        self.gstin = str(
            self.gstin or ""
        ).strip().upper()

        self.pan_number = str(
            self.pan_number or ""
        ).strip().upper()

    def _validate_identity(self):
        if self.party_type == "Person":
            if (
                not self.aadhaar_number
                or not self.aadhaar_number.isdigit()
                or len(self.aadhaar_number) != 12
            ):
                frappe.throw(
                    "Aadhaar Number is mandatory for Person and "
                    "must contain exactly 12 numeric digits."
                )

            if not self.person_category:
                frappe.throw(
                    "Person Category is mandatory for Person."
                )

            self.gstin = ""
            self.pan_number = ""
            return

        if self.party_type in ("Supplier / Vendor", "Customer"):
            self.aadhaar_number = ""
            self.person_category = ""

            if not self.gstin:
                frappe.throw(
                    "GSTIN is mandatory for "
                    f"{self.party_type}."
                )

            if not re.fullmatch(
                r"[0-9A-Z]{15}",
                self.gstin,
            ):
                frappe.throw(
                    "GSTIN must contain exactly 15 "
                    "letters/numbers."
                )

            if self.pan_number and not re.fullmatch(
                r"[A-Z]{5}[0-9]{4}[A-Z]",
                self.pan_number,
            ):
                frappe.throw(
                    "PAN Number must follow the standard "
                    "10-character PAN format."
                )

            return

        frappe.throw("Please select a valid Party Type.")

    def _protect_status(self):
        if self.is_new():
            self.status = "Active"
            return

        old_status = frappe.db.get_value(
            self.doctype,
            self.name,
            "status",
        )

        if old_status == "Revoked" and self.status == "Active":
            frappe.throw(
                "A revoked block cannot be reactivated. "
                "Create a new Block Registry entry instead."
            )

    def _set_audit_fields(self):
        if self.is_new() and not self.blocked_by:
            self.blocked_by = frappe.session.user

        if self.status == "Revoked":
            if not self.revocation_reason:
                frappe.throw(
                    "Revocation Reason is mandatory when "
                    "revoking a block."
                )

            if not self.revoked_date:
                self.revoked_date = nowdate()

            if not self.revoked_by:
                self.revoked_by = frappe.session.user
        else:
            self.revoked_date = None
            self.revoked_by = None
            self.revocation_reason = None

    def _check_duplicate_active_block(self):
        if self.status != "Active":
            return

        filters = {
            "status": "Active",
            "party_type": self.party_type,
            "name": ["!=", self.name or ""],
        }

        if self.party_type == "Person":
            filters["aadhaar_number"] = self.aadhaar_number
        else:
            filters["gstin"] = self.gstin

        existing = frappe.db.get_value(
            "NAVE Block Registry",
            filters,
            "name",
        )

        if existing:
            frappe.throw(
                "This identity is already actively blocked "
                f"under {existing}."
            )
