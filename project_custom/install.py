import frappe

from project_custom.project_cost import recalculate_project_journal_entry_cost


def before_migrate():
	# Reserved for pre-sync hooks. Legacy sentinel role for nave-task-dashboard
	# is no longer required — the Page source is removed and v1_7 deletes the DB row.
	pass


def after_install():
	ensure_custom_fields()


def ensure_custom_fields():
	fields = [
		{
			"dt": "Journal Entry",
			"label": "Project",
			"fieldname": "project",
			"fieldtype": "Link",
			"options": "Project",
			"insert_after": "posting_date",
			"allow_on_submit": 1,
		},
		{
			"dt": "Project",
			"label": "Total Journal Entry Cost",
			"fieldname": "custom_total_journal_entry_cost",
			"fieldtype": "Currency",
			"insert_after": "total_consumed_material_cost",
			"read_only": 1,
			"no_copy": 1,
		},
		{
			"dt": "Project",
			"label": "Total Cost Including Journal Entry",
			"fieldname": "custom_total_cost_including_journal_entry",
			"fieldtype": "Currency",
			"insert_after": "custom_total_journal_entry_cost",
			"read_only": 1,
			"no_copy": 1,
		},
		{
			"dt": "Project",
			"label": "Gross Margin Including Journal Entry",
			"fieldname": "custom_gross_margin_including_journal_entry",
			"fieldtype": "Currency",
			"insert_after": "gross_margin",
			"read_only": 1,
			"no_copy": 1,
		},
		{
			"dt": "Project",
			"label": "Gross Margin % Including Journal Entry",
			"fieldname": "custom_gross_margin_percent_including_journal_entry",
			"fieldtype": "Percent",
			"insert_after": "custom_gross_margin_including_journal_entry",
			"read_only": 1,
			"no_copy": 1,
		},
{
    "dt": "Project",
    "label": "Total Payroll Manpower Cost",
    "fieldname": "custom_total_payroll_manpower_cost",
    "fieldtype": "Currency",
    "insert_after": "custom_total_journal_entry_cost",
    "read_only": 1,
    "no_copy": 1,
},
{
    "dt": "Project",
    "label": "Total Cost Including Journal & Payroll",
    "fieldname": "custom_total_cost_including_journal_and_payroll",
    "fieldtype": "Currency",
    "insert_after": "custom_total_payroll_manpower_cost",
    "read_only": 1,
    "no_copy": 1,
},
{
    "dt": "Project",
    "label": "Gross Margin Including Journal & Payroll",
    "fieldname": "custom_gross_margin_including_journal_and_payroll",
    "fieldtype": "Currency",
    "insert_after": "custom_gross_margin_including_journal_entry",
    "read_only": 1,
    "no_copy": 1,
},
{
    "dt": "Project",
    "label": "Gross Margin % Including Journal & Payroll",
    "fieldname": "custom_gross_margin_percent_including_journal_and_payroll",
    "fieldtype": "Percent",
    "insert_after": "custom_gross_margin_including_journal_and_payroll",
    "read_only": 1,
    "no_copy": 1,
},
	]

	for field in fields:
		if not frappe.db.exists(
			"Custom Field", {"dt": field["dt"], "fieldname": field["fieldname"]}
		):
			frappe.get_doc({"doctype": "Custom Field", **field}).insert(
				ignore_permissions=True
			)


def recalculate_all_project_journal_entry_costs():
	for project in frappe.get_all("Project", pluck="name"):
		recalculate_project_journal_entry_cost(project)


def after_migrate():
	ensure_custom_fields()
	ensure_expense_claim_payable_account_rule()
	recalculate_all_project_journal_entry_costs()


def ensure_expense_claim_payable_account_rule():
        frappe.make_property_setter(
                {
                        "doctype": "Expense Claim",
                        "doctype_or_field": "DocField",
                        "fieldname": "payable_account",
                        "property": "mandatory_depends_on",
                        "value": 'eval:doc.workflow_state=="Pending Accounts Payment"',
                        "property_type": "Data",
                }
        )
