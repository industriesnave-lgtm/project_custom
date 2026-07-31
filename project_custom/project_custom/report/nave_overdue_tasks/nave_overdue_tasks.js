// Copyright (c) 2026, Nave Industries and contributors
// License: MIT. See LICENSE

frappe.query_reports["NAVE Overdue Tasks"] = {
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
			fieldname: "aging_bucket",
			label: __("Aging Bucket"),
			fieldtype: "Select",
			options: ["", "1-3 Days", "4-7 Days", "8-15 Days", "16-30 Days", "30+ Days"],
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
