// Copyright (c) 2026, Nave Industries and contributors
// License: MIT. See LICENSE

frappe.query_reports["NAVE Pending Aging"] = {
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
			options: ["", "Open", "Working", "Pending"],
		},
		{
			fieldname: "pending_aging_bucket",
			label: __("Pending Aging Bucket"),
			fieldtype: "Select",
			options: ["", "0-3 Days", "4-7 Days", "8-15 Days", "16-30 Days", "30+ Days"],
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
	],
};
