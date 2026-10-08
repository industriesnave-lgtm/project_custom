import frappe
from frappe.utils import flt

from project_custom.project_unbilled_alert_report import (
    assert_unbilled_alert_report_access,
    execute_unbilled_alert_report,
)
from project_custom.project_custom.report.monthly_project_billing.monthly_project_billing import (
    execute as execute_monthly_billing,
)


@frappe.whitelist()
def get_dashboard_data(month_year=None, project=None):
    # Apply the existing unbilled report's server-side access control.
    assert_unbilled_alert_report_access()

    billing_filters = {
        "month_year": month_year or frappe.utils.today(),
    }

    unbilled_filters = {}

    if project:
        billing_filters["project"] = project
        unbilled_filters["project"] = project

    billing_result = execute_monthly_billing(billing_filters)
    unbilled_result = execute_unbilled_alert_report(unbilled_filters)

    billing_rows = billing_result[1] or []
    unbilled_rows = unbilled_result[1] or []

    billing_summary = {
        "service_billing": sum(
            flt(row.get("service_billing")) for row in billing_rows
        ),
        "supply_billing": sum(
            flt(row.get("supply_billing")) for row in billing_rows
        ),
        "total_billing": sum(
            flt(row.get("total_billing")) for row in billing_rows
        ),
    }

    return {
        "billing": {
            "columns": billing_result[0],
            "data": billing_rows,
            "summary": billing_summary,
        },
        "unbilled": {
            "columns": unbilled_result[0],
            "data": unbilled_rows,
            "summary": unbilled_result[4] or [],
        },
    }
