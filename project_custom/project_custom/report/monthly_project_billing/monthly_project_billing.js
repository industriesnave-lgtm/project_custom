frappe.query_reports["Monthly Project Billing"] = {
    filters: [
        {
            fieldname: "month_year",
            label: __("Month-Year"),
            fieldtype: "Date",
            default: frappe.datetime.get_today(),
            description: __("Select any date within the required month."),
        },
        {
            fieldname: "project",
            label: __("Project"),
            fieldtype: "Link",
            options: "Project",
        },
        {
            fieldname: "from_date",
            label: __("From Date"),
            fieldtype: "Date",
        },
        {
            fieldname: "to_date",
            label: __("To Date"),
            fieldtype: "Date",
        },
    ],
};
