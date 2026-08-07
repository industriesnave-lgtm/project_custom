// Copyright (c) 2026, Nave Industries and contributors
// License: MIT. See LICENSE
//
// Reusable NAVE Task Dashboard UI (Batch 8D / Phase 4.5).
// Consumes Batch 8A/8B/8C whitelisted APIs — no client-side KPI/chart math.

frappe.provide("frappe.project_custom");

frappe.project_custom.mount_nave_task_dashboard = function ($container, options) {
	options = options || {};
	const embedded = !!options.embedded;
	$container = $($container);

	const API = {
		metadata: "project_custom.api.nave_task_dashboard.get_task_dashboard_metadata",
		kpi: "project_custom.api.nave_task_dashboard.get_task_dashboard_kpi_cards",
		widget: "project_custom.api.nave_task_dashboard.get_task_dashboard_widget",
		chart: "project_custom.api.nave_task_dashboard.get_task_dashboard_chart",
	};

	const WIDGETS = [
		{ type: "due_today", title: __("Due Today") },
		{ type: "due_tomorrow", title: __("Due Tomorrow") },
		{ type: "overdue", title: __("Overdue") },
		{ type: "high_priority", title: __("High Priority") },
		{ type: "recently_updated", title: __("Recently Updated") },
	];

	const CHARTS = [
		{ type: "monthly_trend", title: __("Monthly Trend"), chart_type: "line", note: true },
		{ type: "status_distribution", title: __("Status Distribution"), chart_type: "percentage" },
		{ type: "priority_distribution", title: __("Priority Distribution"), chart_type: "bar" },
		{ type: "department_performance", title: __("Department Performance"), chart_type: "bar" },
		{ type: "project_performance", title: __("Project Performance"), chart_type: "bar" },
		{ type: "overdue_trend", title: __("Overdue Trend"), chart_type: "line", note: true },
	];

	const KPI_TONES = {
		overdue: "alert",
		due_today: "warning",
		due_tomorrow: "warning",
		high_priority: "warning",
		completed: "success",
		closed: "success",
		completed_today: "success",
		active: "",
		total: "",
	};

	// Valid destinations only — cards without a mapping stay non-clickable.
	const KPI_NAV = {
		open: { kind: "view", view: "all_tasks", status: "Open" },
		working: { kind: "view", view: "all_tasks", status: "Working" },
		pending: { kind: "view", view: "all_tasks", status: "Pending" },
		completed: { kind: "report", report: "NAVE Completed Task Report" },
		closed: { kind: "view", view: "all_tasks", status: "Closed" },
		overdue: { kind: "report", report: "NAVE Overdue Tasks" },
		due_today: { kind: "view", view: "all_tasks", due_date: "today" },
		due_tomorrow: { kind: "view", view: "all_tasks", due_date: "tomorrow" },
		high_priority: { kind: "view", view: "all_tasks", priority: "High" },
		completed_today: { kind: "report", report: "NAVE Completed Task Report" },
		// total / active: no single unambiguous filtered destination
	};

	const REPORT_SHORTCUTS = [
		{ label: __("My Tasks"), report: "NAVE My Tasks" },
		{ label: __("Overdue Tasks"), report: "NAVE Overdue Tasks" },
		{ label: __("Completed Tasks"), report: "NAVE Completed Task Report" },
		{ label: __("Department Report"), report: "NAVE Department Task Report" },
		{ label: __("Project Report"), report: "NAVE Project Task Report" },
		{ label: __("Employee Performance"), report: "NAVE Employee Performance Report" },
		{ label: __("Weekly Summary"), report: "NAVE Weekly Task Summary" },
		{ label: __("Monthly Summary"), report: "NAVE Monthly Task Summary" },
	];

	const CHART_NAV = {
		department_performance: { kind: "report", report: "NAVE Department Task Report" },
		project_performance: { kind: "report", report: "NAVE Project Task Report" },
		overdue_trend: { kind: "report", report: "NAVE Overdue Tasks" },
		monthly_trend: { kind: "report", report: "NAVE Monthly Task Summary" },
		// status_distribution / priority_distribution: no dedicated report
	};

	const state = {
		loading: false,
		request_id: 0,
		metadata: null,
		filters: {},
		chart_instances: {},
		controls: {},
	};

	const escape = (value) => frappe.utils.escape_html(String(value == null ? "" : value));

	const call_method = (method, args) =>
		new Promise((resolve, reject) => {
			frappe.call({
				method,
				args: args || {},
				callback: (r) => {
					if (r.exc) {
						reject(r.exc);
						return;
					}
					resolve(r.message);
				},
				error: (err) => reject(err),
			});
		});

	const year_start = () => `${String(frappe.datetime.get_today()).slice(0, 4)}-01-01`;

	const default_filters = () => ({
		from_date: year_start(),
		to_date: frappe.datetime.get_today(),
		assigned_to: "",
		department: "",
		project: "",
		priority: "",
		status: "",
	});

	const add_styles = () => {
		if (document.getElementById("nave-task-dashboard-style")) {
			return;
		}
		$(`<style id="nave-task-dashboard-style">
			.ntd-wrap { padding: 16px; background: #f6f8fc; border-radius: 12px; min-height: calc(100vh - 100px); }
			.ntd-wrap.ntd-embedded { min-height: 0; padding: 4px 0 12px; background: transparent; border-radius: 0; }
			.ntd-header { display:flex; justify-content:space-between; gap:16px; align-items:center; background:#fff; padding:16px 20px; border-radius:12px; margin-bottom:14px; box-shadow:0 2px 10px rgba(23,59,103,.06); }
			.ntd-header h2 { margin:0; color:#173b67; font-size:22px; font-weight:700; }
			.ntd-meta { color:#748096; font-size:13px; margin-top:4px; }
			.ntd-actions { display:flex; gap:8px; flex-wrap:wrap; }
			.ntd-filters { background:#fff; padding:14px 16px; border-radius:12px; margin-bottom:14px; box-shadow:0 2px 10px rgba(23,59,103,.06); }
			.ntd-filter-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(160px,1fr)); gap:10px; align-items:end; }
			.ntd-filter-grid .form-group { margin-bottom:0; }
			.ntd-filter-actions { display:flex; gap:8px; flex-wrap:wrap; margin-top:12px; }
			.ntd-kpi-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(140px,1fr)); gap:10px; margin-bottom:14px; align-items:stretch; }
			.ntd-kpi { background:#fff; border-radius:12px; padding:14px; border-top:4px solid #1683d8; box-shadow:0 2px 10px rgba(23,59,103,.06); min-height:88px; height:100%; display:flex; flex-direction:column; justify-content:space-between; box-sizing:border-box; }
			.ntd-kpi.is-clickable { cursor:pointer; transition: transform .12s ease, box-shadow .12s ease; }
			.ntd-kpi.is-clickable:hover { transform: translateY(-1px); box-shadow:0 6px 16px rgba(23,59,103,.12); }
			.ntd-kpi.is-static { cursor:default; }
			.ntd-kpi.success { border-top-color:#16a36a; }
			.ntd-kpi.warning { border-top-color:#f59e0b; }
			.ntd-kpi.alert { border-top-color:#e34b4b; }
			.ntd-kpi-label { color:#64748b; font-size:12px; font-weight:600; line-height:1.3; }
			.ntd-kpi-value { color:#173b67; font-size:24px; font-weight:700; margin-top:6px; line-height:1.2; }
			.ntd-shortcut-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(160px,1fr)); gap:10px; margin-bottom:14px; align-items:stretch; }
			.ntd-shortcut { background:#fff; border:1px solid #e6ebf3; border-radius:10px; padding:12px 14px; text-align:left; color:#173b67; font-weight:600; font-size:13px; cursor:pointer; min-height:48px; box-shadow:0 1px 6px rgba(23,59,103,.04); }
			.ntd-shortcut:hover { border-color:#1683d8; color:#1683d8; }
			.ntd-widget-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(280px,1fr)); gap:12px; margin-bottom:14px; align-items:stretch; }
			.ntd-panel { background:#fff; border-radius:12px; padding:14px; box-shadow:0 2px 10px rgba(23,59,103,.06); min-height:120px; height:100%; display:flex; flex-direction:column; box-sizing:border-box; }
			.ntd-panel h4 { margin:0 0 10px; color:#173b67; font-size:15px; font-weight:700; }
			.ntd-panel.is-clickable h4 { cursor:pointer; }
			.ntd-panel.is-clickable h4:hover { color:#1683d8; }
			.ntd-note { color:#748096; font-size:12px; margin:0 0 8px; }
			.ntd-table { width:100%; border-collapse:collapse; font-size:13px; }
			.ntd-table th, .ntd-table td { padding:8px 6px; border-bottom:1px solid #eef1f6; text-align:left; vertical-align:top; }
			.ntd-table th { color:#64748b; font-size:11px; text-transform:uppercase; }
			.ntd-empty, .ntd-error, .ntd-loading { color:#748096; padding:12px 4px; }
			.ntd-error { color:#b42318; }
			.ntd-chart-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(320px,1fr)); gap:12px; align-items:stretch; }
			.ntd-chart-box { min-height:260px; flex:1; }
			.ntd-widget-body { flex:1; overflow:auto; }
			.ntd-badge { display:inline-block; padding:2px 8px; border-radius:999px; background:#eff6ff; color:#1683d8; font-size:11px; font-weight:600; }
			.ntd-badge.Overdue, .ntd-badge.overdue { background:#fef2f2; color:#dc2626; }
			.ntd-disabled { pointer-events:none; opacity:.65; }
			@media (max-width: 900px) {
				.ntd-header { flex-direction:column; align-items:flex-start; }
				.ntd-wrap { padding:10px; }
				.ntd-wrap.ntd-embedded { padding:0 0 10px; }
				.ntd-kpi-grid { grid-template-columns:repeat(auto-fit,minmax(120px,1fr)); }
			}
		</style>`).appendTo("head");
	};

	const shell_html = () => `
		<div class="ntd-wrap ${embedded ? "ntd-embedded" : ""}">
			<div class="ntd-header">
				<div>
					<h2>${embedded ? __("Dashboard") : __("NAVE Task Dashboard")}</h2>
					<div class="ntd-meta ntd-last-refreshed">${__("Not refreshed yet")}</div>
				</div>
				<div class="ntd-actions">
					<button class="btn btn-default btn-sm ntd-refresh" type="button">${__("Refresh")}</button>
				</div>
			</div>
			<div class="ntd-filters">
				<div class="ntd-filter-grid">
					<div class="form-group">
						<label>${__("From Date")}</label>
						<input type="date" class="form-control ntd-filter" data-key="from_date" />
					</div>
					<div class="form-group">
						<label>${__("To Date")}</label>
						<input type="date" class="form-control ntd-filter" data-key="to_date" />
					</div>
					<div class="form-group ntd-ctrl-assigned_to"></div>
					<div class="form-group ntd-ctrl-department"></div>
					<div class="form-group ntd-ctrl-project"></div>
					<div class="form-group">
						<label>${__("Priority")}</label>
						<select class="form-control ntd-filter" data-key="priority">
							<option value=""></option>
						</select>
					</div>
					<div class="form-group">
						<label>${__("Status")}</label>
						<select class="form-control ntd-filter" data-key="status">
							<option value=""></option>
						</select>
					</div>
				</div>
				<div class="ntd-filter-actions">
					<button class="btn btn-primary btn-sm ntd-apply" type="button">${__("Apply")}</button>
					<button class="btn btn-default btn-sm ntd-clear" type="button">${__("Clear")}</button>
				</div>
				<div class="ntd-filter-error text-danger small" style="display:none;margin-top:8px;"></div>
			</div>
			<div class="ntd-global-error ntd-error" style="display:none;"></div>
			<div class="ntd-kpi-grid"></div>
			<div class="ntd-shortcut-grid">
				${REPORT_SHORTCUTS.map(
					(s) => `
					<button type="button" class="ntd-shortcut" data-report="${escape(s.report)}">${escape(
						s.label
					)}</button>`
				).join("")}
			</div>
			<div class="ntd-widget-grid">
				${WIDGETS.map(
					(w) => `
					<div class="ntd-panel" data-widget="${escape(w.type)}">
						<h4>${escape(w.title)}</h4>
						<div class="ntd-widget-body ntd-loading">${__("Loading...")}</div>
					</div>`
				).join("")}
			</div>
			<div class="ntd-chart-grid">
				${CHARTS.map(
					(c) => {
						const clickable = CHART_NAV[c.type] ? "is-clickable" : "";
						return `
					<div class="ntd-panel ${clickable}" data-chart="${escape(c.type)}">
						<h4>${escape(c.title)}</h4>
						<div class="ntd-note ntd-chart-note" style="display:none;"></div>
						<div class="ntd-chart-box" id="ntd-chart-${escape(c.type)}">
							<div class="ntd-loading">${__("Loading...")}</div>
						</div>
					</div>`;
					}
				).join("")}
			</div>
		</div>
	`;

	const make_link_control = (parent_sel, fieldname, options, label) => {
		const $parent = $container.find(parent_sel);
		$parent.empty();
		const control = frappe.ui.form.make_control({
			parent: $parent.get(0),
			df: {
				fieldtype: "Link",
				options,
				fieldname,
				label,
				only_select: 1,
			},
			render_input: true,
		});
		control.refresh();
		state.controls[fieldname] = control;
		return control;
	};

	const fill_select = ($el, values) => {
		const current = $el.val();
		$el.find("option:not([value=''])").remove();
		(values || []).forEach((value) => {
			$el.append(`<option value="${escape(value)}">${escape(value)}</option>`);
		});
		if (current) {
			$el.val(current);
		}
	};

	const read_filters = () => {
		const filters = {};
		$container.find(".ntd-filter").each(function () {
			const key = $(this).data("key");
			const value = ($(this).val() || "").trim();
			if (value) {
				filters[key] = value;
			}
		});
		["assigned_to", "department", "project"].forEach((key) => {
			const control = state.controls[key];
			const value = control && control.get_value ? (control.get_value() || "").trim() : "";
			if (value) {
				filters[key] = value;
			}
		});
		return filters;
	};

	const write_filters = (filters) => {
		const values = Object.assign(default_filters(), filters || {});
		$container.find('.ntd-filter[data-key="from_date"]').val(values.from_date || "");
		$container.find('.ntd-filter[data-key="to_date"]').val(values.to_date || "");
		$container.find('.ntd-filter[data-key="priority"]').val(values.priority || "");
		$container.find('.ntd-filter[data-key="status"]').val(values.status || "");
		["assigned_to", "department", "project"].forEach((key) => {
			if (state.controls[key] && state.controls[key].set_value) {
				state.controls[key].set_value(values[key] || "");
			}
		});
	};

	const validate_dates = (filters) => {
		if (filters.from_date && filters.to_date && filters.from_date > filters.to_date) {
			return __("From Date cannot be after To Date.");
		}
		return "";
	};

	const set_loading = (loading) => {
		state.loading = loading;
		$container.find(".ntd-refresh, .ntd-apply, .ntd-clear").prop("disabled", !!loading);
	};

	const show_filter_error = (message) => {
		const $err = $container.find(".ntd-filter-error");
		if (message) {
			$err.text(message).show();
		} else {
			$err.hide().text("");
		}
	};

	const destroy_chart = (chart_type) => {
		const existing = state.chart_instances[chart_type];
		if (existing && typeof existing.destroy === "function") {
			try {
				existing.destroy();
			} catch (e) {
				// ignore stale chart cleanup errors
			}
		}
		delete state.chart_instances[chart_type];
		$container.find(`#ntd-chart-${chart_type}`).empty();
	};

	const open_nav = (nav) => {
		if (!nav || typeof nav !== "object") {
			return;
		}
		if (nav.kind === "report" && nav.report) {
			frappe.set_route("query-report", nav.report);
			return;
		}
		if (nav.kind === "view" && nav.view) {
			if (typeof options.on_view_navigate === "function") {
				options.on_view_navigate(nav);
				return;
			}
			frappe.route_options = {
				nave_tasks_nav: nav,
			};
			frappe.set_route("nave-tasks");
		}
	};

	const render_kpis = (payload) => {
		const cards = (payload && payload.card_list) || [];
		const map = (payload && payload.cards) || {};
		const html = (cards.length
			? cards
			: Object.keys(map).map((key) => ({ key, label: key, value: map[key] || 0 }))
		)
			.map((card) => {
				const tone = KPI_TONES[card.key] || "";
				const nav = KPI_NAV[card.key] || null;
				const clickable = nav ? "is-clickable" : "is-static";
				const nav_attr = nav ? ` data-kpi="${escape(card.key)}"` : "";
				const role = nav ? ' role="button" tabindex="0"' : "";
				return `
					<div class="ntd-kpi ${tone} ${clickable}"${nav_attr}${role}>
						<div class="ntd-kpi-label">${escape(card.label || card.key)}</div>
						<div class="ntd-kpi-value">${escape(card.value == null ? 0 : card.value)}</div>
					</div>`;
			})
			.join("");
		$container.find(".ntd-kpi-grid").html(html || `<div class="ntd-empty">${__("No KPI data")}</div>`);
	};

	const task_link = (name, title) => {
		const route = `/app/nave-task/${encodeURIComponent(name || "")}`;
		return `<a href="${route}">${escape(title || name || "")}</a>`;
	};

	const render_widget = (widget_type, payload, error) => {
		const $body = $container.find(`[data-widget="${widget_type}"] .ntd-widget-body`);
		if (error) {
			$body.html(`<div class="ntd-error">${__("Unable to load widget.")}</div>`);
			return;
		}
		const items = (payload && payload.items) || [];
		if (!items.length) {
			$body.html(`<div class="ntd-empty">${__("No tasks found")}</div>`);
			return;
		}
		const show_overdue = Object.prototype.hasOwnProperty.call(items[0], "overdue_days");
		const rows = items
			.map((item) => {
				const overdue_cell = show_overdue
					? `<td>${escape(item.overdue_days == null ? "" : item.overdue_days)}</td>`
					: "";
				return `
					<tr>
						<td>${task_link(item.name, item.title)}</td>
						<td>${escape(item.assigned_to)}</td>
						<td><span class="ntd-badge">${escape(item.status)}</span></td>
						<td>${escape(item.priority)}</td>
						<td>${escape(item.due_date || "")}</td>
						<td>${escape(item.project || "")}</td>
						<td>${escape(item.department || "")}</td>
						${overdue_cell}
					</tr>`;
			})
			.join("");
		$body.html(`
			<table class="ntd-table">
				<thead>
					<tr>
						<th>${__("Title")}</th>
						<th>${__("Assigned")}</th>
						<th>${__("Status")}</th>
						<th>${__("Priority")}</th>
						<th>${__("Due")}</th>
						<th>${__("Project")}</th>
						<th>${__("Dept")}</th>
						${show_overdue ? `<th>${__("Overdue Days")}</th>` : ""}
					</tr>
				</thead>
				<tbody>${rows}</tbody>
			</table>
		`);
	};

	const has_chart_values = (payload) => {
		const datasets = (payload && payload.datasets) || [];
		return datasets.some((ds) => (ds.values || []).some((v) => Number(v || 0) !== 0));
	};

	const render_chart = (spec, payload, error) => {
		const $box = $container.find(`#ntd-chart-${spec.type}`);
		const $note = $container.find(`[data-chart="${spec.type}"] .ntd-chart-note`);
		destroy_chart(spec.type);

		if (error) {
			$box.html(`<div class="ntd-error">${__("Unable to load chart.")}</div>`);
			$note.hide();
			return;
		}

		const notes = [];
		if (spec.note && payload && payload.meta && payload.meta.historical_status) {
			notes.push(payload.meta.historical_status);
		}
		if (payload && payload.meta && payload.meta.limitation) {
			notes.push(payload.meta.limitation);
		}
		if (payload && payload.meta && payload.meta.truncated) {
			const total = payload.meta.total_groups || "";
			notes.push(
				__("Showing top {0} of {1} groups.", [
					payload.meta.returned_groups || 25,
					total || "?",
				])
			);
		}
		if (notes.length) {
			$note.html(escape(notes.join(" "))).show();
		} else {
			$note.hide().text("");
		}

		if (!payload || !(payload.labels || []).length || !has_chart_values(payload)) {
			$box.html(`<div class="ntd-empty">${__("No data available")}</div>`);
			return;
		}

		if (!window.frappe || !frappe.Chart) {
			$box.html(`<div class="ntd-empty">${__("Chart component unavailable")}</div>`);
			return;
		}

		$box.empty();
		try {
			state.chart_instances[spec.type] = new frappe.Chart(`#ntd-chart-${spec.type}`, {
				title: "",
				data: {
					labels: payload.labels || [],
					datasets: (payload.datasets || []).map((ds) => ({
						name: ds.name,
						values: ds.values || [],
					})),
				},
				type: spec.chart_type || "bar",
				height: 260,
				colors: ["#1683d8", "#16a36a", "#f59e0b", "#e34b4b", "#7c3aed"],
				barOptions: { stacked: 0, spaceRatio: 0.3 },
				axisOptions: { xIsSeries: 1 },
				tooltipOptions: { formatTooltipY: (d) => d },
			});
		} catch (e) {
			console.error("NAVE Task Dashboard chart error", spec.type, e);
			$box.html(`<div class="ntd-error">${__("Unable to render chart.")}</div>`);
		}
	};

	const load_metadata = async () => {
		const meta = await call_method(API.metadata);
		state.metadata = meta || {};
		fill_select($container.find('.ntd-filter[data-key="priority"]'), meta.priorities || []);
		fill_select($container.find('.ntd-filter[data-key="status"]'), meta.statuses || []);
		return meta;
	};

	const load_dashboard = async () => {
		if (state.loading) {
			return;
		}
		const filters = read_filters();
		const date_error = validate_dates(filters);
		show_filter_error(date_error);
		if (date_error) {
			return;
		}

		const request_id = ++state.request_id;
		set_loading(true);
		$container.find(".ntd-global-error").hide().text("");
		$container.find(".ntd-kpi-grid").html(`<div class="ntd-loading">${__("Loading KPIs...")}</div>`);
		WIDGETS.forEach((w) => {
			$container
				.find(`[data-widget="${w.type}"] .ntd-widget-body`)
				.html(`<div class="ntd-loading">${__("Loading...")}</div>`);
		});
		CHARTS.forEach((c) => {
			destroy_chart(c.type);
			$container
				.find(`#ntd-chart-${c.type}`)
				.html(`<div class="ntd-loading">${__("Loading...")}</div>`);
		});

		state.filters = filters;

		// Widgets use due/status logic from the backend; omit creation-date range
		// so Due Today / Overdue are not clipped by chart default year bounds.
		const widget_filters = Object.assign({}, filters);
		delete widget_filters.from_date;
		delete widget_filters.to_date;

		try {
			const kpi_promise = call_method(API.kpi, { filters }).then(
				(message) => ({ ok: true, message }),
				(error) => ({ ok: false, error })
			);
			const widget_promises = WIDGETS.map((w) =>
				call_method(API.widget, {
					widget_type: w.type,
					filters: widget_filters,
					limit: 10,
				}).then(
					(message) => ({ type: w.type, ok: true, message }),
					(error) => ({ type: w.type, ok: false, error })
				)
			);
			const chart_promises = CHARTS.map((c) =>
				call_method(API.chart, { chart_type: c.type, filters }).then(
					(message) => ({ type: c.type, ok: true, message }),
					(error) => ({ type: c.type, ok: false, error })
				)
			);

			const [kpi_result, ...rest] = await Promise.all([
				kpi_promise,
				...widget_promises,
				...chart_promises,
			]);

			if (request_id !== state.request_id) {
				return;
			}

			if (kpi_result.ok) {
				render_kpis(kpi_result.message || {});
			} else {
				$container
					.find(".ntd-kpi-grid")
					.html(`<div class="ntd-error">${__("Unable to load KPI cards.")}</div>`);
				console.error("NAVE Task Dashboard KPI error", kpi_result.error);
			}

			rest.slice(0, WIDGETS.length).forEach((result) => {
				render_widget(result.type, result.message, result.ok ? null : result.error);
				if (!result.ok) {
					console.error("NAVE Task Dashboard widget error", result.type, result.error);
				}
			});

			rest.slice(WIDGETS.length).forEach((result) => {
				const spec = CHARTS.find((c) => c.type === result.type);
				if (!spec) {
					return;
				}
				render_chart(spec, result.message, result.ok ? null : result.error);
				if (!result.ok) {
					console.error("NAVE Task Dashboard chart error", result.type, result.error);
				}
			});

			$container
				.find(".ntd-last-refreshed")
				.text(`${__("Last refreshed")}: ${frappe.datetime.now_datetime()}`);
		} catch (error) {
			if (request_id !== state.request_id) {
				return;
			}
			console.error("NAVE Task Dashboard load error", error);
			const message =
				(error && error.message) ||
				__("You do not have permission to access this dashboard, or the request failed.");
			$container.find(".ntd-global-error").text(message).show();
		} finally {
			if (request_id === state.request_id) {
				set_loading(false);
			}
		}
	};

	const bind_events = () => {
		$container.find(".ntd-apply").on("click", () => load_dashboard());
		$container.find(".ntd-refresh").on("click", () => load_dashboard());
		$container.find(".ntd-clear").on("click", () => {
			write_filters(default_filters());
			show_filter_error("");
			load_dashboard();
		});

		// Single delegated handler — avoid duplicate bindings on refresh.
		$container.off("click.ntdNav").on("click.ntdNav", ".ntd-kpi.is-clickable", function () {
			const key = $(this).data("kpi");
			open_nav(KPI_NAV[key]);
		});
		$container.on("click.ntdNav", ".ntd-shortcut[data-report]", function () {
			const report = $(this).data("report");
			open_nav({ kind: "report", report });
		});
		$container.on("click.ntdNav", ".ntd-panel.is-clickable[data-chart] > h4", function () {
			const chart_type = $(this).closest("[data-chart]").data("chart");
			open_nav(CHART_NAV[chart_type]);
		});
	};

	const boot = async () => {
		add_styles();
		$container.html(shell_html());
		make_link_control(".ntd-ctrl-assigned_to", "assigned_to", "User", __("Assigned To"));
		make_link_control(".ntd-ctrl-department", "department", "Department", __("Department"));
		make_link_control(".ntd-ctrl-project", "project", "Project", __("Project"));
		write_filters(default_filters());
		bind_events();

		try {
			await load_metadata();
			await load_dashboard();
		} catch (error) {
			console.error("NAVE Task Dashboard boot error", error);
			$container.find(".ntd-global-error")
				.text(__("Access denied or dashboard metadata could not be loaded."))
				.show();
			set_loading(false);
		}
	};


	const destroy = () => {
		state.request_id += 1;
		CHARTS.forEach((c) => destroy_chart(c.type));
		$container.empty();
	};

	const api = {
		refresh: () => load_dashboard(),
		destroy,
		// Exposed for tests / parent page wiring.
		KPI_NAV,
		REPORT_SHORTCUTS,
		CHART_NAV,
		open_nav,
	};

	boot();
	return api;
};
