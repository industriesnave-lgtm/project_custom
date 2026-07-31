// Copyright (c) 2026, Nave Industries and contributors
// License: MIT. See LICENSE

frappe.query_reports["NAVE Team Tasks"] = {
	filters: [
		{
			fieldname: "assigned_to",
			label: __("Assigned To"),
			fieldtype: "Link",
			options: "User",
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
			fieldname: "from_date",
			label: __("Created From"),
			fieldtype: "Date",
		},
		{
			fieldname: "to_date",
			label: __("Created To"),
			fieldtype: "Date",
		},
		{
			fieldname: "due_date_from",
			label: __("Due From"),
			fieldtype: "Date",
		},
		{
			fieldname: "due_date_to",
			label: __("Due To"),
			fieldtype: "Date",
		},
	],
};
