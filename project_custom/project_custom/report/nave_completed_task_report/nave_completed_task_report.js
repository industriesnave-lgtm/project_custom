// Copyright (c) 2026, Nave Industries and contributors
// License: MIT. See LICENSE

frappe.query_reports["NAVE Completed Task Report"] = {
	filters: [
		{
			fieldname: "assigned_to",
			label: __("Assigned To"),
			fieldtype: "Link",
			options: "User",
		},
		{
			fieldname: "department",
			label: __("Department"),
			fieldtype: "Link",
			options: "Department",
		},
		{
			fieldname: "project",
			label: __("Project"),
			fieldtype: "Link",
			options: "Project",
		},
		{
			fieldname: "priority",
			label: __("Priority"),
			fieldtype: "Select",
			options: ["", "Low", "Medium", "High", "Urgent"],
		},
		{
			fieldname: "status",
			label: __("Status"),
			fieldtype: "Select",
			options: ["", "Completed", "Closed"],
		},
		{
			fieldname: "completed_from",
			label: __("Completed From"),
			fieldtype: "Date",
		},
		{
			fieldname: "completed_to",
			label: __("Completed To"),
			fieldtype: "Date",
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
		{
			fieldname: "completion_result",
			label: __("Completion Result"),
			fieldtype: "Select",
			options: ["", "On Time", "Late", "No Due Date"],
		},
	],
};
