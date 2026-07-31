// Copyright (c) 2026, Nave Industries and contributors
// License: MIT. See LICENSE
//
// Standalone Batch 8D route retained for backward compatibility.
// Phase 4.5 consolidates the UI into /app/nave-tasks (Dashboard tab).

frappe.pages["nave-task-dashboard"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("NAVE Task Dashboard"),
		single_column: true,
	});

	page.main.html(
		`<div class="text-muted" style="padding:24px;">${__(
			"Redirecting to NAVE Tasks…"
		)}</div>`
	);

	// Preferred consolidated entry: NAVE Tasks Dashboard tab.
	frappe.set_route("nave-tasks");
};

frappe.pages["nave-task-dashboard"].on_page_show = function () {
	frappe.set_route("nave-tasks");
};
