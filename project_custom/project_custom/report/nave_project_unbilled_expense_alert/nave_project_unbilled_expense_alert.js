// Copyright (c) 2026, Nave Industries and contributors
// License: MIT. See LICENSE

frappe.query_reports["NAVE Project Unbilled Expense Alert"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
		},
		{
			fieldname: "project",
			label: __("Project"),
			fieldtype: "Link",
			options: "Project",
		},
		{
			fieldname: "customer",
			label: __("Customer"),
			fieldtype: "Link",
			options: "Customer",
		},
		{
			fieldname: "project_status",
			label: __("Project Status"),
			fieldtype: "Select",
			options: "\nOpen\nOn hold\nCompleted\nCancelled",
		},
		{
			fieldname: "alert_status",
			label: __("Alert Status"),
			fieldtype: "Select",
			options: "\nPending\nAlerted\nResolved",
		},
		{
			fieldname: "alert_sent",
			label: __("Alert Sent"),
			fieldtype: "Select",
			options: "\n0\n1",
		},
		{
			fieldname: "threshold_crossed_from",
			label: __("Threshold Crossed From"),
			fieldtype: "Date",
		},
		{
			fieldname: "threshold_crossed_to",
			label: __("Threshold Crossed To"),
			fieldtype: "Date",
		},
		{
			fieldname: "ageing_days_min",
			label: __("Ageing Days >="),
			fieldtype: "Int",
		},
		{
			fieldname: "unbilled_amount_min",
			label: __("Unbilled Amount >="),
			fieldtype: "Currency",
		},
		{
			fieldname: "include_resolved",
			label: __("Include Resolved"),
			fieldtype: "Check",
			default: 0,
		},
	],
};
