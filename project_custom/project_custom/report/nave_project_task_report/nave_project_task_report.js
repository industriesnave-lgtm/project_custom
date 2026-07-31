// Copyright (c) 2026, Nave Industries and contributors
// License: MIT. See LICENSE

frappe.query_reports["NAVE Project Task Report"] = {
	filters: [
		{
			fieldname: "project",
			label: __("Project"),
			fieldtype: "Link",
			options: "Project",
		},
		{
			fieldname: "department",
			label: __("Department"),
			fieldtype: "Link",
			options: "Department",
		},
		{
			fieldname: "status",
			label: __("Status"),
			fieldtype: "Select",
			options: ["", "Open", "Working", "Pending", "Completed", "Closed", "Cancelled"],
		},
		{
			fieldname: "priority",
			label: __("Priority"),
			fieldtype: "Select",
			options: ["", "Low", "Medium", "High", "Urgent"],
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
