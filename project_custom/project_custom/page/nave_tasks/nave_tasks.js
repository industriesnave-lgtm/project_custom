frappe.pages["nave-tasks"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: "NAVE Tasks",
		single_column: true,
	});

	page.add_inner_button(__("Nave Home"), () => frappe.set_route("nave-home"));

	const APP = {
		page,
		$view: null,
		state: {
			view: "dashboard",
			page_no: 1,
			page_length: 12,
			total: 0,
			items: [],
			loading: false,
			error: "",
			counts: null,
			dashboard_controller: null,
			filters: {
				search: "",
				status: "",
				priority: "",
				project: "",
				assigned_user: "",
				creator: "",
				due_date: "",
			},
			employee_department: null,
			_due_before: "",
			_due_after: "",
			_modified_after: "",
		},
		VIEW_API: {
			my_tasks: "project_custom.api.nave_task.get_my_tasks",
			created_by_me: "project_custom.api.nave_task.get_tasks_created_by_me",
			all_tasks: "project_custom.api.nave_task.get_all_tasks",
			overdue_tasks: "project_custom.api.nave_task.get_overdue_tasks",
			task_updates: "project_custom.api.nave_task.get_task_updates_list",
			dashboard: "project_custom.api.nave_task.get_dashboard_counts",
			timeline: "project_custom.api.nave_task.get_task_timeline",
			recurring_tasks: "project_custom.api.nave_task.get_recurring_tasks",
		},
		NAV: [
			{ id: "dashboard", label: "Dashboard" },
			{ id: "my_tasks", label: "My Tasks" },
			{ id: "created_by_me", label: "Created by Me" },
			{ id: "all_tasks", label: "All Tasks" },
			{ id: "overdue_tasks", label: "Overdue Tasks" },
			{ id: "recurring_tasks", label: "Recurring Tasks" },
			{ id: "task_updates", label: "Task Updates" },
		],
	};

	const escape = (value) => frappe.utils.escape_html(String(value == null ? "" : value));

	const as_int = (value) => {
		const n = parseInt(value, 10);
		return Number.isNaN(n) ? 0 : n;
	};

	const today_str = () => frappe.datetime.get_today();

	const add_days = (date_str, days) => frappe.datetime.add_days(date_str, days);

	const ensure_styles = () => {
		if (document.getElementById("nave-tasks-css")) return;
		const link = document.createElement("link");
		link.id = "nave-tasks-css";
		link.rel = "stylesheet";
		link.href = "/assets/project_custom/css/nave_tasks.css";
		document.head.appendChild(link);
	};

	const current_user = () => frappe.session.user;

	const is_admin = () =>
		current_user() === "Administrator" || frappe.user.has_role("System Manager");

	const is_director = () => frappe.user.has_role("NAVE Task Director");

	const is_manager = () => frappe.user.has_role("NAVE Task Manager");

	const is_manager_level = () => is_admin() || is_director() || is_manager();

	const can_manage_task = (task) => {
		const user = current_user();
		if (is_admin() || is_director()) return true;
		if (task.owner === user || task.assigned_by === user) return true;
		if (
			is_manager() &&
			APP.state.employee_department &&
			task.department === APP.state.employee_department
		) {
			return true;
		}
		return false;
	};

	const can_submit_update = (task) => {
		const user = current_user();
		if (is_admin() || is_director()) return true;
		if (task.assigned_to === user) return true;
		if (
			is_manager() &&
			APP.state.employee_department &&
			task.department === APP.state.employee_department
		) {
			return true;
		}
		return false;
	};

	// Creator and assignee always get conversation reply access (permission rules unchanged).
	const can_reply_on_task = (task) => {
		if (task.status === "Cancelled") return false;
		const user = current_user();
		if (is_admin() || is_director()) return true;
		if (task.assigned_to === user) return true;
		if (task.owner === user || task.assigned_by === user) return true;
		if (
			is_manager() &&
			APP.state.employee_department &&
			task.department === APP.state.employee_department
		) {
			return true;
		}
		return false;
	};

	const allowed_next_statuses = (task) => {
		const status = task.status || "Open";
		const manage = can_manage_task(task);
		const manager_level = is_manager_level() && manage;
		const map = {
			Open: ["Working"],
			Working: ["Pending", "Completed"],
			Pending: ["Working", "Completed"],
			Completed: [
				...(manage ? ["Closed"] : []),
				...(manager_level ? ["Working"] : []),
			],
			Closed: manager_level ? ["Working"] : [],
		};
		const next = map[status] || [];
		return [status, ...next.filter((s) => s !== status)];
	};

	const action_visibility = (task) => {
		const closed = task.status === "Closed";
		const cancelled = task.status === "Cancelled";
		const completed = task.status === "Completed";
		const manage = can_manage_task(task);
		const update = can_submit_update(task);
		const manager_level = is_manager_level();
		return {
			open_task: true,
			view_updates: true,
			reply: can_reply_on_task(task),
			submit_update: update && !cancelled && (!closed || (manager_level && manage)),
			reassign: manage && !cancelled,
			close_task: manage && completed,
			reopen_task: manage && manager_level && (completed || closed),
			allowed_next_statuses: allowed_next_statuses(task),
		};
	};

	const due_badges = (task) => {
		const badges = [];
		if (as_int(task.is_overdue)) {
			badges.push(`<span class="nt-badge overdue">Overdue</span>`);
			return badges;
		}
		if (!task.due_date || ["Completed", "Closed", "Cancelled"].includes(task.status)) {
			return badges;
		}
		const today = today_str();
		if (task.due_date === today) {
			badges.push(`<span class="nt-badge due-today">Due Today</span>`);
		} else if (task.due_date > today && task.due_date <= add_days(today, 7)) {
			badges.push(`<span class="nt-badge due-soon">Due Soon</span>`);
		}
		return badges;
	};

	const call = (method, args = {}) =>
		new Promise((resolve, reject) => {
			frappe.call({
				method,
				args,
				callback(r) {
					if (r.exc) {
						reject(r.exc);
						return;
					}
					resolve(r.message);
				},
				error(err) {
					reject(err);
				},
			});
		});

	const set_loading = (msg = "Loading…") => {
		APP.$view.html(`
			<div class="nt-loading">
				<span class="nt-spinner"></span>
				<span>${escape(msg)}</span>
			</div>
		`);
	};

	const set_error = (msg) => {
		APP.$view.html(`<div class="nt-error">${escape(msg || "Something went wrong.")}</div>`);
	};

	const shell = () => {
		page.main.html(`
			<div class="nave-tasks-app">
				<aside class="nt-sidebar">
					<div class="nt-brand">
						<img src="/assets/project_custom/images/nave-task-management.svg" alt="NAVE Tasks">
						<div>
							<h1>NAVE Tasks</h1>
							<p>Professional task workspace</p>
						</div>
					</div>
					<div class="nt-nav"></div>
				</aside>
				<section class="nt-main">
					<div class="nt-mobile-nav"></div>
					<div class="nt-topbar">
						<div>
							<h2 class="nt-title">Dashboard</h2>
							<p class="nt-subtitle">Permission-aware overview of your work.</p>
						</div>
						<div class="nt-top-actions">
							<button type="button" class="btn btn-primary nt-new-task">+ New Task</button>
							<button class="btn btn-default nt-refresh">Refresh</button>
						</div>
					</div>
					<div class="nt-panel nt-view"></div>
				</section>
			</div>
		`);

		APP.$view = page.main.find(".nt-view");
		const $nav = page.main.find(".nt-nav");
		const $mobile = page.main.find(".nt-mobile-nav");

		APP.NAV.forEach((item) => {
			const btn = $(
				`<button type="button" class="nt-nav-btn" data-view="${item.id}">${escape(
					item.label
				)}</button>`
			);
			$nav.append(btn.clone(true));
			$mobile.append(btn);
		});

		page.main.find(".nt-nav-btn").on("click", function () {
			APP.state._due_before = "";
			APP.state._due_after = "";
			APP.state._modified_after = "";
			set_view($(this).data("view"));
		});
		page.main.find(".nt-refresh").on("click", () => load_current(true));
		page.main.find(".nt-new-task").on("click", () => open_new_task_dialog());
	};

	const update_nav = () => {
		page.main.find(".nt-nav-btn").each(function () {
			$(this).toggleClass("active", $(this).data("view") === APP.state.view);
		});
		const meta = APP.NAV.find((n) => n.id === APP.state.view);
		page.main.find(".nt-title").text(meta ? meta.label : "NAVE Tasks");
	};

	const filter_bar_html = (opts = {}) => {
		const show_assignee = opts.assignee !== false;
		const show_creator = opts.creator !== false;
		const f = APP.state.filters;
		return `
			<div class="nt-filters">
				<input class="form-control nt-filter" data-key="search" placeholder="Search subject…" value="${escape(
					f.search
				)}">
				<select class="form-control nt-filter" data-key="status">
					<option value="">All statuses</option>
					${["Open", "Working", "Pending", "Completed", "Closed", "Cancelled"]
						.map(
							(s) =>
								`<option value="${s}" ${f.status === s ? "selected" : ""}>${s}</option>`
						)
						.join("")}
				</select>
				<select class="form-control nt-filter" data-key="priority">
					<option value="">All priorities</option>
					${["Low", "Medium", "High", "Urgent"]
						.map(
							(s) =>
								`<option value="${s}" ${
									f.priority === s ? "selected" : ""
								}>${s}</option>`
						)
						.join("")}
				</select>
				<input class="form-control nt-filter" data-key="project" placeholder="Project" value="${escape(
					f.project
				)}">
				${
					show_assignee
						? `<input class="form-control nt-filter" data-key="assigned_user" placeholder="Assigned user" value="${escape(
								f.assigned_user
						  )}">`
						: `<input class="form-control" disabled value="Assigned: me">`
				}
				${
					show_creator
						? `<input class="form-control nt-filter" data-key="creator" placeholder="Creator" value="${escape(
								f.creator
						  )}">`
						: `<input class="form-control nt-filter" data-key="due_date" type="date" value="${escape(
								f.due_date
						  )}">`
				}
				${
					show_creator
						? `<input class="form-control nt-filter" data-key="due_date" type="date" value="${escape(
								f.due_date
						  )}">`
						: ""
				}
			</div>
		`;
	};

	const bind_filters = () => {
		page.main.find(".nt-filter").on("change", function () {
			const key = $(this).data("key");
			APP.state.filters[key] = $(this).val();
			APP.state.page_no = 1;
			APP.state.items = [];
			load_current(true);
		});
		let search_timer = null;
		page.main.find('.nt-filter[data-key="search"]').on("input", function () {
			const value = $(this).val();
			clearTimeout(search_timer);
			search_timer = setTimeout(() => {
				APP.state.filters.search = value;
				APP.state.page_no = 1;
				APP.state.items = [];
				load_current(true);
			}, 350);
		});
	};

	const task_card_html = (task) => {
		const actions = action_visibility(task);
		const progress = Number(task.progress || 0);
		const classes = [
			"nt-task-card",
			as_int(task.is_overdue) ? "overdue" : "",
			task.status === "Completed" ? "completed" : "",
			task.status === "Closed" ? "closed" : "",
		]
			.filter(Boolean)
			.join(" ");

		const badges = [
			`<span class="nt-badge status-${escape(task.status)}">${escape(task.status)}</span>`,
			`<span class="nt-badge priority-${escape(task.priority)}">${escape(
				task.priority || "-"
			)}</span>`,
			...due_badges(task),
		].join("");

		const buttons = [];
		if (actions.open_task) {
			buttons.push(
				`<button class="btn btn-default btn-sm nt-act" data-act="open" data-task="${escape(
					task.name
				)}">Open Task</button>`
			);
		}
		if (actions.submit_update) {
			buttons.push(
				`<button class="btn btn-primary btn-sm nt-act" data-act="update" data-task="${escape(
					task.name
				)}">Submit Update</button>`
			);
		}
		if (actions.view_updates) {
			buttons.push(
				`<button class="btn btn-default btn-sm nt-act" data-act="timeline" data-task="${escape(
					task.name
				)}">View Updates</button>`
			);
		}
		if (actions.reply) {
			buttons.push(
				`<button class="btn btn-default btn-sm nt-act" data-act="reply" data-task="${escape(
					task.name
				)}">Reply</button>`
			);
		}
		if (actions.reassign) {
			buttons.push(
				`<button class="btn btn-default btn-sm nt-act" data-act="reassign" data-task="${escape(
					task.name
				)}">Reassign</button>`
			);
		}
		if (actions.close_task) {
			buttons.push(
				`<button class="btn btn-danger btn-sm nt-act" data-act="close" data-task="${escape(
					task.name
				)}">Close Task</button>`
			);
		}

		return `
			<article class="${classes}" data-task-id="${escape(task.name)}">
				<h3 class="nt-task-title">${escape(task.subject)}</h3>
				<div class="nt-task-desc">${escape(task.description || "No description")}</div>
				<div class="nt-badges">${badges}</div>
				<div class="nt-meta">
					<div><b>ID:</b> ${escape(task.name)}</div>
					<div><b>Assignee:</b> ${escape(task.assigned_to || "-")}</div>
					<div><b>Created by:</b> ${escape(task.assigned_by || task.owner || "-")}</div>
					<div><b>Project:</b> ${escape(task.project || "-")}</div>
					<div><b>Due:</b> ${escape(task.due_date || "-")}</div>
					<div><b>Priority:</b> ${escape(task.priority || "-")}</div>
				</div>
				<div class="nt-progress-label">
					<span>Progress</span><span>${progress}%</span>
				</div>
				<div class="nt-progress"><span style="width:${Math.max(0, Math.min(100, progress))}%"></span></div>
				<div class="nt-actions">${buttons.join("")}</div>
			</article>
		`;
	};

	const bind_task_actions = () => {
		page.main.find(".nt-act").on("click", function () {
			const act = $(this).data("act");
			const name = $(this).data("task");
			const task = APP.state.items.find((t) => t.name === name) || { name };
			if (act === "open") open_task_detail(name);
			if (act === "update") open_update_dialog(task);
			if (act === "timeline") open_task_detail(name, true);
			if (act === "reply") open_reply_dialog(name);
			if (act === "reassign") open_reassign_dialog(name);
			if (act === "close") open_close_dialog(name);
		});
	};

	const render_task_list = (append = false) => {
		const title_bits = filter_bar_html({
			assignee: APP.state.view !== "my_tasks",
			creator: !["my_tasks", "created_by_me"].includes(APP.state.view),
		});

		if (!append) {
			if (!APP.state.items.length && !APP.state.loading) {
				APP.$view.html(`
					${title_bits}
					<div class="nt-empty">No tasks found for this view.</div>
				`);
				bind_filters();
				return;
			}
			APP.$view.html(`
				${title_bits}
				<div class="nt-task-grid">${APP.state.items.map(task_card_html).join("")}</div>
				<div class="nt-load-more-wrap" style="text-align:center;margin-top:14px;"></div>
			`);
		} else {
			APP.$view.find(".nt-task-grid").append(APP.state.items.slice(-APP.state.page_length).map(task_card_html).join(""));
		}

		const loaded = APP.state.items.length;
		const more = loaded < APP.state.total;
		const $wrap = APP.$view.find(".nt-load-more-wrap");
		$wrap.html(
			more
				? `<button class="btn btn-default nt-load-more">Load More (${loaded} / ${APP.state.total})</button>`
				: `<div class="nt-empty" style="padding:12px;">Showing ${loaded} task(s).</div>`
		);
		$wrap.find(".nt-load-more").on("click", () => {
			APP.state.page_no += 1;
			load_task_view(true);
		});
		bind_filters();
		bind_task_actions();
	};

	const render_dashboard = (counts) => {
		const cards = [
			{ key: "open", label: "Open", cls: "" },
			{ key: "working", label: "Working", cls: "" },
			{ key: "pending", label: "Pending", cls: "pending" },
			{ key: "overdue", label: "Overdue", cls: "overdue" },
			{ key: "completed", label: "Completed", cls: "completed" },
		];
		const secondary = [
			{ key: "due_today", label: "Due Today" },
			{ key: "due_within_7_days", label: "Due Within 7 Days" },
			{ key: "recently_updated", label: "Recently Updated" },
		];

		APP.$view.html(`
			<div class="nt-dashboard-grid">
				${cards
					.map(
						(c) => `
					<button type="button" class="nt-stat-card ${c.cls}" data-counter="${c.key}">
						<div class="label">${c.label}</div>
						<div class="value">${escape(counts[c.key] ?? 0)}</div>
					</button>`
					)
					.join("")}
			</div>
			<div class="nt-secondary-stats">
				${secondary
					.map(
						(c) => `
					<button type="button" class="nt-stat-card" data-counter="${c.key}">
						<div class="label">${c.label}</div>
						<div class="value">${escape(counts[c.key] ?? 0)}</div>
					</button>`
					)
					.join("")}
			</div>
		`);

		APP.$view.find("[data-counter]").on("click", function () {
			const key = $(this).data("counter");
			navigate_from_counter(key);
		});
	};

	const navigate_from_counter = (key) => {
		APP.state.filters = {
			search: "",
			status: "",
			priority: "",
			project: "",
			assigned_user: "",
			creator: "",
			due_date: "",
		};
		APP.state._due_before = "";
		APP.state._due_after = "";
		APP.state._modified_after = "";

		if (key === "overdue") {
			set_view("overdue_tasks");
			return;
		}
		if (key === "open") APP.state.filters.status = "Open";
		if (key === "working") APP.state.filters.status = "Working";
		if (key === "pending") APP.state.filters.status = "Pending";
		if (key === "completed") APP.state.filters.status = "Completed";
		if (key === "due_today") APP.state.filters.due_date = today_str();
		if (key === "due_within_7_days") {
			APP.state.filters.due_date = "";
			APP.state._due_before = add_days(today_str(), 7);
			APP.state._due_after = today_str();
		}
		if (key === "recently_updated") {
			// Match get_dashboard_counts: modified >= (today - 7 days) 00:00:00
			APP.state._modified_after = `${add_days(today_str(), -7)} 00:00:00`;
		}
		set_view("all_tasks");
	};

	const render_updates = () => {
		if (!APP.state.items.length) {
			APP.$view.html(`<div class="nt-empty">No task updates found.</div>`);
			return;
		}
		APP.$view.html(`
			<div class="nt-update-list">
				${APP.state.items
					.map((row) => {
						const title = row.task_subject || row.task || "Task";
						const sender =
							row.sender_full_name || row.update_by || row.employee || "—";
						const when = row.display_time || row.updated_on || "—";
						const message = row.update_text || row.latest_update || "";
						return `
					<div class="nt-update-row" data-task="${escape(row.task || "")}">
						<div class="nt-badges">
							<span class="nt-badge">${escape(row.update_type || "Update")}</span>
							<span class="nt-badge status-${escape(row.status)}">${escape(
							row.status || "-"
						)}</span>
						</div>
						<div class="nt-update-task-title"><b>${escape(title)}</b></div>
						<div class="nt-update-meta">
							<span><b>By:</b> ${escape(sender)}</span>
							<span><b>When:</b> ${escape(when)}</span>
						</div>
						<div class="nt-timeline-text" style="margin-top:8px;">${escape(message)}</div>
						<div style="margin-top:8px;">
							<button class="btn btn-default btn-sm nt-act" data-act="open" data-task="${escape(
								row.task
							)}">Open Task</button>
						</div>
					</div>`;
					})
					.join("")}
			</div>
			<div class="nt-load-more-wrap" style="text-align:center;margin-top:14px;"></div>
		`);
		const loaded = APP.state.items.length;
		const more = loaded < APP.state.total;
		const $wrap = APP.$view.find(".nt-load-more-wrap");
		$wrap.html(
			more
				? `<button class="btn btn-default nt-load-more">Load More (${loaded} / ${APP.state.total})</button>`
				: ""
		);
		$wrap.find(".nt-load-more").on("click", () => {
			APP.state.page_no += 1;
			load_updates_view(true);
		});
		bind_task_actions();
	};

	const render_recurring_list = () => {
		if (!APP.state.items.length && !APP.state.loading) {
			APP.$view.html(`
				<div class="nt-empty">No recurring task templates found.</div>
			`);
			return;
		}

		const cards = APP.state.items
			.map((task) => {
				const active = as_int(task.recurrence_active);
				const manage = can_manage_task(task);
				const buttons = [
					`<button class="btn btn-default btn-sm nt-rec-act" data-act="open" data-task="${escape(
						task.name
					)}">Open Template</button>`,
					`<button class="btn btn-default btn-sm nt-rec-act" data-act="generated" data-task="${escape(
						task.name
					)}">View Generated Tasks</button>`,
				];
				if (manage) {
					if (active) {
						buttons.push(
							`<button class="btn btn-default btn-sm nt-rec-act" data-act="disable" data-task="${escape(
								task.name
							)}">Disable</button>`
						);
						buttons.push(
							`<button class="btn btn-primary btn-sm nt-rec-act" data-act="generate" data-task="${escape(
								task.name
							)}">Generate Now</button>`
						);
					} else {
						buttons.push(
							`<button class="btn btn-primary btn-sm nt-rec-act" data-act="enable" data-task="${escape(
								task.name
							)}">Enable</button>`
						);
					}
				}
				return `
				<article class="nt-task-card ${active ? "" : "closed"}">
					<h3 class="nt-task-title">${escape(task.subject)}</h3>
					<div class="nt-badges">
						<span class="nt-badge">${escape(task.recurrence_frequency || "-")}</span>
						<span class="nt-badge ${active ? "status-Working" : "status-Closed"}">
							${active ? "Active" : "Disabled"}
						</span>
					</div>
					<div class="nt-meta">
						<div><b>Template:</b> ${escape(task.name)}</div>
						<div><b>Assignee:</b> ${escape(task.assigned_to || "-")}</div>
						<div><b>Project:</b> ${escape(task.project || "-")}</div>
						<div><b>Start:</b> ${escape(task.recurrence_start_date || "-")}</div>
						<div><b>End:</b> ${escape(task.recurrence_end_date || "-")}</div>
						<div><b>Last generated:</b> ${escape(task.last_generated_date || "-")}</div>
						<div><b>Next creation:</b> ${escape(task.next_creation_date || "-")}</div>
						<div><b>Due after days:</b> ${escape(task.recurrence_due_after_days ?? 0)}</div>
					</div>
					<div class="nt-actions">${buttons.join("")}</div>
				</article>`;
			})
			.join("");

		APP.$view.html(`
			<div class="nt-task-grid">${cards}</div>
			<div class="nt-load-more-wrap" style="text-align:center;margin-top:14px;"></div>
		`);

		const loaded = APP.state.items.length;
		const more = loaded < APP.state.total;
		const $wrap = APP.$view.find(".nt-load-more-wrap");
		$wrap.html(
			more
				? `<button class="btn btn-default nt-load-more">Load More (${loaded} / ${APP.state.total})</button>`
				: `<div class="nt-empty" style="padding:12px;">Showing ${loaded} template(s).</div>`
		);
		$wrap.find(".nt-load-more").on("click", () => {
			APP.state.page_no += 1;
			load_recurring_view(true);
		});

		APP.$view.find(".nt-rec-act").on("click", function () {
			const act = $(this).data("act");
			const name = $(this).data("task");
			if (act === "open") open_task_detail(name);
			if (act === "generated") open_generated_tasks(name);
			if (act === "enable") {
				frappe.call({
					method: "project_custom.api.nave_task.enable_recurring_task",
					args: { task_name: name },
					freeze: true,
					callback(r) {
						if (r.message?.ok) {
							frappe.show_alert({ message: "Recurrence enabled", indicator: "green" });
							load_current(true);
						}
					},
				});
			}
			if (act === "disable") {
				frappe.confirm("Disable recurrence for this template?", () => {
					frappe.call({
						method: "project_custom.api.nave_task.disable_recurring_task",
						args: { task_name: name },
						freeze: true,
						callback(r) {
							if (r.message?.ok) {
								frappe.show_alert({
									message: "Recurrence disabled",
									indicator: "green",
								});
								load_current(true);
							}
						},
					});
				});
			}
			if (act === "generate") {
				frappe.call({
					method: "project_custom.api.nave_task.generate_recurring_task_now",
					args: { task_name: name },
					freeze: true,
					freeze_message: "Generating task…",
					callback(r) {
						if (r.message?.ok) {
							frappe.show_alert({
								message: "Generate Now completed",
								indicator: "green",
							});
							load_current(true);
						}
					},
				});
			}
		});
	};

	const open_generated_tasks = async (template_name) => {
		const dialog = new frappe.ui.Dialog({
			title: `Generated Tasks · ${template_name}`,
			size: "large",
			fields: [{ fieldtype: "HTML", fieldname: "body" }],
		});
		dialog.show();
		dialog.fields_dict.body.$wrapper.html(
			`<div class="nt-loading"><span class="nt-spinner"></span> Loading…</div>`
		);
		try {
			const result = await call("project_custom.api.nave_task.get_generated_tasks", {
				template_name,
				page: 1,
				page_length: 50,
			});
			const rows = result?.data || [];
			if (!rows.length) {
				dialog.fields_dict.body.$wrapper.html(
					`<div class="nt-empty">No generated tasks yet.</div>`
				);
				return;
			}
			dialog.fields_dict.body.$wrapper.html(`
				<div class="nt-update-list">
					${rows
						.map(
							(row) => `
						<div class="nt-update-row">
							<div><b>${escape(row.subject)}</b></div>
							<div>ID: ${escape(row.name)}</div>
							<div>Occurrence: ${escape(row.recurrence_occurrence_date || "-")}</div>
							<div>Due: ${escape(row.due_date || "-")} · Status: ${escape(row.status || "-")}</div>
							<button class="btn btn-default btn-sm nt-open-gen" data-task="${escape(
								row.name
							)}" style="margin-top:8px;">Open Task</button>
						</div>`
						)
						.join("")}
				</div>
			`);
			dialog.fields_dict.body.$wrapper.find(".nt-open-gen").on("click", function () {
				dialog.hide();
				open_task_detail($(this).data("task"));
			});
		} catch (e) {
			dialog.fields_dict.body.$wrapper.html(
				`<div class="nt-error">Unable to load generated tasks.</div>`
			);
		}
	};

	const load_recurring_view = async (append = false) => {
		if (!append) set_loading("Loading recurring templates…");
		try {
			const result = await call(APP.VIEW_API.recurring_tasks, {
				page: APP.state.page_no,
				page_length: APP.state.page_length,
			});
			const rows = result?.data || [];
			APP.state.total = result?.total || 0;
			APP.state.items = append ? APP.state.items.concat(rows) : rows;
			render_recurring_list();
		} catch (e) {
			set_error("Unable to load recurring tasks.");
		}
	};

	const type_css_class = (update_type) => {
		const map = {
			Reply: "nt-type-reply",
			"Manager Instruction": "nt-type-manager",
			"Internal Note": "nt-type-internal",
			System: "nt-type-system",
			"Status Change": "nt-type-system",
			Reassignment: "nt-type-system",
			Close: "nt-type-system",
			"Recurrence Event": "nt-type-system",
			"Completion Update": "nt-type-completion",
			"Progress Update": "nt-type-progress",
			"Clarification Required": "nt-type-clarification",
		};
		return map[update_type || "Reply"] || "nt-type-reply";
	};

	const display_time = (item) =>
		item.display_time || item.datetime || item.updated_on || "";

	const attachment_html = (item) => {
		const attach = item.attachment || "";
		if (!attach) return "";
		const kind = item.attachment_kind || "";
		const is_image = kind === "photo" || /\.(png|jpe?g|gif|webp)$/i.test(attach);
		const is_video = kind === "video" || /\.(mp4|webm|mov|m4v)$/i.test(attach);
		const label =
			kind === "pdf"
				? "PDF"
				: kind === "excel"
				? "Excel"
				: kind === "video"
				? "Video"
				: kind === "photo"
				? "Photo"
				: "Attachment";
		let preview = "";
		if (is_image) {
			preview = `<img class="nt-chat-attach-preview" src="${escape(attach)}" alt="">`;
		} else if (is_video) {
			preview = `<video class="nt-chat-attach-preview" controls src="${escape(attach)}"></video>`;
		}
		return `
			<div class="nt-chat-attach">
				<a class="nt-chat-attach-link" href="${escape(attach)}" target="_blank" rel="noopener">${escape(
			label
		)}</a>
				${preview}
			</div>`;
	};

	const message_row_html = (item, { is_reply = false } = {}) => {
		const who = item.sender_full_name || "User";
		const initial = String(who).trim().charAt(0).toUpperCase() || "?";
		const type = item.update_type || "Reply";
		const mine = item.is_mine ? "nt-chat-mine" : "nt-chat-theirs";
		const ticks =
			item.delivery_state === "seen"
				? `<span class="nt-chat-ticks seen" title="${escape(
						item.seen_display || "Seen"
				  )}">✓✓</span>`
				: `<span class="nt-chat-ticks sent" title="Sent">✓</span>`;
		const chip = item.progress_chip
			? `<span class="nt-progress-chip">${escape(item.progress_chip)}</span>`
			: "";
		const quote =
			item.parent_snippet && !is_reply
				? `<div class="nt-chat-quote"><span class="nt-chat-quote-name">${escape(
						item.parent_sender_name || "Reply"
				  )}</span><span class="nt-chat-quote-text">${escape(
						item.parent_snippet
				  )}</span></div>`
				: "";
		const type_label =
			type && !["Reply", "Progress Update"].includes(type)
				? `<span class="nt-chat-type">${escape(type)}</span>`
				: "";

		return `
			<div class="nt-chat-msg ${mine} ${type_css_class(type)} ${
			is_reply ? "nt-chat-reply-msg" : ""
		}" data-update="${escape(item.name || "")}">
				<div class="nt-chat-avatar">${escape(initial)}</div>
				<div class="nt-chat-bubble">
					<div class="nt-chat-head">
						<span class="nt-chat-name">${escape(who)}</span>
						<span class="nt-role-badge role-${escape(
							(item.display_role || "Employee").toLowerCase()
						)}">${escape(item.display_role || "Employee")}</span>
						${type_label}
						<span class="nt-chat-time">${escape(display_time(item))}</span>
					</div>
					${quote}
					${chip}
					<div class="nt-chat-text">${escape(item.update_text || "")}</div>
					${attachment_html(item)}
					<div class="nt-chat-foot">
						<button type="button" class="nt-chat-reply-btn" data-parent="${escape(
							item.name || ""
						)}" data-snippet="${escape(item.update_text || "")}" data-who="${escape(
			who
		)}">Reply</button>
						${item.is_mine ? ticks : ""}
					</div>
				</div>
			</div>`;
	};

	const timeline_html = (items) => {
		if (!items.length) {
			return `<div class="nt-empty">No messages yet. Start the conversation below.</div>`;
		}
		return `
			<div class="nt-chat-feed">
				${items
					.map((item) => {
						const replies = item.replies || [];
						return `
						<div class="nt-chat-thread">
							${message_row_html(item)}
							${
								replies.length
									? `<div class="nt-chat-replies">${replies
											.map((r) => message_row_html(r, { is_reply: true }))
											.join("")}</div>`
									: ""
							}
						</div>`;
					})
					.join("")}
			</div>
		`;
	};

	const composer_html = (allowed_types = []) => {
		const types = allowed_types.length
			? allowed_types
			: ["Reply", "Progress Update", "Clarification Required", "Completion Update"];
		return `
			<div class="nt-chat-composer">
				<div class="nt-chat-reply-banner" hidden>
					<div class="nt-chat-reply-banner-text"></div>
					<button type="button" class="nt-chat-reply-cancel" title="Cancel reply">×</button>
				</div>
				<textarea class="form-control nt-composer-message" rows="2" placeholder="Write a message… (Enter to send, Shift+Enter for new line)"></textarea>
				<input type="hidden" class="nt-composer-parent" value="">
				<input type="hidden" class="nt-composer-attachment" value="">
				<div class="nt-chat-composer-bar">
					<select class="form-control nt-composer-type" title="Message type">
						${types
							.map((t) => `<option value="${escape(t)}">${escape(t)}</option>`)
							.join("")}
					</select>
					<button type="button" class="btn btn-default btn-sm nt-composer-attach" title="Attach">Attach</button>
					<span class="nt-composer-attach-name nt-muted"></span>
					<button type="button" class="btn btn-primary btn-sm nt-composer-submit">Send</button>
				</div>
			</div>
		`;
	};

	const open_task_detail = async (task_name, focus_timeline = false) => {
		const dialog = new frappe.ui.Dialog({
			title: `Task ${task_name}`,
			size: "extra-large",
			fields: [{ fieldtype: "HTML", fieldname: "body" }],
		});
		dialog.$wrapper.addClass("nt-conversation-dialog");
		dialog.show();
		dialog.fields_dict.body.$wrapper.html(
			`<div class="nt-loading"><span class="nt-spinner"></span> Loading conversation…</div>`
		);

		const render_detail = async () => {
			try {
				const payload = await call(APP.VIEW_API.timeline, { task_name });
				const task = payload.task || {};
				const actions = action_visibility(task);
				const assignee_label = task.assigned_to_name || task.assigned_to || "—";
				const action_buttons = [];
				if (actions.submit_update) {
					action_buttons.push(
						`<button class="btn btn-primary btn-sm nt-detail-act" data-act="update">Submit Progress</button>`
					);
				}
				if (actions.reassign) {
					action_buttons.push(
						`<button class="btn btn-default btn-sm nt-detail-act" data-act="reassign">Reassign</button>`
					);
				}
				action_buttons.push(
					`<a class="btn btn-default btn-sm" href="/app/nave-task/${encodeURIComponent(
						task.name
					)}" target="_blank" rel="noopener">Open Full Form</a>`
				);

				const show_composer = actions.reply || actions.submit_update;
				dialog.fields_dict.body.$wrapper.html(`
					<div class="nt-conversation">
						<aside class="nt-conversation-summary">
							<div class="nt-summary-title">${escape(task.subject || task_name)}</div>
							<div class="nt-summary-id">${escape(task.name || task_name)}</div>
							<div class="nt-badges">
								<span class="nt-badge status-${escape(task.status)}">${escape(task.status || "")}</span>
								<span class="nt-badge priority-${escape(task.priority)}">${escape(
					task.priority || ""
				)}</span>
							</div>
							<div class="nt-summary-rows">
								<div><span>Progress</span><b>${escape(task.progress || 0)}%</b></div>
								<div><span>Due</span><b>${escape(task.due_date || "—")}</b></div>
								<div><span>Assigned To</span><b>${escape(assignee_label)}</b></div>
								<div><span>Project</span><b>${escape(task.project || "—")}</b></div>
							</div>
							<div class="nt-summary-actions">${action_buttons.join("")}</div>
						</aside>
						<section class="nt-conversation-main">
							<div class="nt-conversation-scroll">
								${timeline_html(payload.timeline || [])}
							</div>
							${show_composer ? composer_html(payload.allowed_update_types || []) : ""}
						</section>
					</div>
				`);

				const $wrap = dialog.fields_dict.body.$wrapper;
				const $scroll = $wrap.find(".nt-conversation-scroll");
				$scroll.scrollTop($scroll.prop("scrollHeight"));

				// Mark visible messages as seen (non-blocking).
				frappe.call({
					method: "project_custom.api.nave_task.mark_timeline_seen",
					args: { task_name },
				});

				$wrap.find(".nt-detail-act").on("click", function () {
					const act = $(this).data("act");
					dialog.hide();
					if (act === "update") open_update_dialog(task);
					if (act === "reassign") open_reassign_dialog(task.name);
				});

				const clear_reply_target = () => {
					$wrap.find(".nt-composer-parent").val("");
					$wrap.find(".nt-chat-reply-banner").attr("hidden", true);
					$wrap.find(".nt-chat-reply-banner-text").text("");
				};

				const set_reply_target = (parent, who, snippet) => {
					$wrap.find(".nt-composer-parent").val(parent || "");
					$wrap.find(".nt-chat-reply-banner").attr("hidden", false);
					$wrap
						.find(".nt-chat-reply-banner-text")
						.text(`Replying to ${who || "message"}: ${(snippet || "").slice(0, 80)}`);
					$wrap.find(".nt-composer-type").val("Reply");
					$wrap.find(".nt-composer-message").trigger("focus");
				};

				$wrap.on("click", ".nt-chat-reply-btn", function () {
					set_reply_target(
						$(this).data("parent"),
						$(this).data("who"),
						$(this).data("snippet")
					);
				});
				$wrap.find(".nt-chat-reply-cancel").on("click", clear_reply_target);

				$wrap.find(".nt-composer-attach").on("click", () => {
					new frappe.ui.FileUploader({
						restrictions: {
							allowed_file_types: [
								"image/*",
								"video/*",
								".pdf",
								".doc",
								".docx",
								".xls",
								".xlsx",
								".csv",
							],
						},
						on_success(file) {
							const path = file.file_url || file.name;
							$wrap.find(".nt-composer-attachment").val(path);
							$wrap.find(".nt-composer-attach-name").text(file.file_name || path);
						},
					});
				});

				const send_message = () => {
					const message = $wrap.find(".nt-composer-message").val();
					const update_type = $wrap.find(".nt-composer-type").val();
					const attachment = $wrap.find(".nt-composer-attachment").val();
					const parent_update = $wrap.find(".nt-composer-parent").val();
					if (!(message || "").trim()) {
						frappe.msgprint("Please enter a message.");
						return;
					}
					frappe.call({
						method: "project_custom.api.nave_task.post_task_message",
						args: {
							task_name,
							message,
							update_type,
							attachment: attachment || undefined,
							parent_update: parent_update || undefined,
						},
						freeze: true,
						freeze_message: __("Sending…"),
						callback(r) {
							if (!r.message?.ok) return;
							frappe.show_alert({ message: __("Sent"), indicator: "green" });
							render_detail();
							load_current(true);
						},
					});
				};

				$wrap.find(".nt-composer-submit").on("click", send_message);
				$wrap.find(".nt-composer-message").on("keydown", function (e) {
					if (e.key === "Enter" && !e.shiftKey) {
						e.preventDefault();
						send_message();
					}
				});

				if (focus_timeline) {
					$scroll.get(0)?.scrollIntoView({ behavior: "smooth", block: "end" });
				}
			} catch (e) {
				dialog.fields_dict.body.$wrapper.html(
					`<div class="nt-error">Unable to load task conversation.</div>`
				);
			}
		};

		await render_detail();
	};

	const open_new_task_dialog = () => {
		const dialog = new frappe.ui.Dialog({
			title: __("New Task"),
			fields: [
				{
					fieldname: "subject",
					fieldtype: "Data",
					label: __("Task Title"),
					reqd: 1,
				},
				{
					fieldname: "assigned_to",
					fieldtype: "Link",
					options: "User",
					label: __("Assign To"),
					reqd: 1,
					get_query: () => ({
						filters: { enabled: 1, user_type: "System User" },
					}),
				},
				{
					fieldname: "project",
					fieldtype: "Link",
					options: "Project",
					label: __("Project"),
				},
				{
					fieldname: "department",
					fieldtype: "Link",
					options: "Department",
					label: __("Department"),
				},
				{
					fieldname: "priority",
					fieldtype: "Select",
					label: __("Priority"),
					options: "Low\nMedium\nHigh\nUrgent",
					default: "Medium",
					reqd: 1,
				},
				{
					fieldname: "due_date",
					fieldtype: "Date",
					label: __("Due Date"),
					reqd: 1,
				},
				{
					fieldname: "description",
					fieldtype: "Small Text",
					label: __("Description"),
				},
				{
					fieldname: "attachment",
					fieldtype: "Attach",
					label: __("Attachment"),
					options: "image/*,video/*,.pdf,.doc,.docx,.xls,.xlsx,.csv",
				},
			],
			primary_action_label: __("Create Task"),
			primary_action(values) {
				if (!(values.subject || "").trim()) {
					frappe.msgprint(__("Task Title is required."));
					return;
				}
				if (!(values.assigned_to || "").trim()) {
					frappe.msgprint(__("Assign To is required."));
					return;
				}
				if (!(values.priority || "").trim()) {
					frappe.msgprint(__("Priority is required."));
					return;
				}
				if (!(values.due_date || "").trim()) {
					frappe.msgprint(__("Due Date is required."));
					return;
				}
				frappe.call({
					method: "project_custom.api.nave_task.create_task",
					args: {
						subject: values.subject,
						assigned_to: values.assigned_to,
						priority: values.priority,
						due_date: values.due_date,
						description: values.description,
						project: values.project,
						department: values.department,
						attachment: values.attachment,
					},
					freeze: true,
					freeze_message: __("Creating task…"),
					callback(r) {
						if (!r.message?.ok) return;
						dialog.hide();
						const task_name = r.message.task;
						frappe.show_alert({
							message: __("Task {0} created", [task_name]),
							indicator: "green",
						});
						load_current(true);
						open_task_detail(task_name, true);
					},
				});
			},
		});
		dialog.show();
	};

	const open_update_dialog = (task) => {
		const actions = action_visibility(task);
		if (!actions.submit_update) {
			frappe.msgprint("You cannot submit an update on this task.");
			return;
		}
		const status_options = (actions.allowed_next_statuses || [task.status]).join("\n");
		const dialog = new frappe.ui.Dialog({
			title: `Update ${task.name || ""}`,
			fields: [
				{
					fieldname: "status",
					fieldtype: "Select",
					label: "Status",
					options: status_options,
					default: task.status || "Working",
					reqd: 1,
				},
				{
					fieldname: "progress",
					fieldtype: "Percent",
					label: "Progress",
					default: task.progress || 0,
					reqd: 1,
				},
				{
					fieldname: "update_text",
					fieldtype: "Small Text",
					label: "Update comment",
					reqd: 1,
				},
				{
					fieldname: "pending_reason",
					fieldtype: "Small Text",
					label: "Pending reason",
					depends_on: "eval:doc.status=='Pending'",
				},
				{
					fieldname: "support_required",
					fieldtype: "Small Text",
					label: "Support required",
					default: task.support_required || "",
				},
				{
					fieldname: "attachment",
					fieldtype: "Attach",
					label: "Attachment",
					options: "image/*,.pdf,.doc,.docx,.xls,.xlsx,.csv",
				},
			],
			primary_action_label: "Submit Update",
			primary_action(values) {
				if (values.status === "Completed") values.progress = 100;
				if (values.status === "Pending" && !(values.pending_reason || "").trim()) {
					frappe.msgprint("Pending reason is required.");
					return;
				}
				frappe.call({
					method: "project_custom.api.nave_task.submit_update",
					args: {
						task_name: task.name,
						status: values.status,
						progress: values.progress,
						update_text: values.update_text,
						pending_reason: values.pending_reason,
						support_required: values.support_required,
						attachment: values.attachment,
					},
					freeze: true,
					freeze_message: "Submitting update…",
					callback(r) {
						if (!r.message?.ok) return;
						dialog.hide();
						frappe.show_alert({ message: "Update submitted", indicator: "green" });
						load_current(true);
					},
				});
			},
		});
		dialog.show();
	};

	const open_reply_dialog = (task_name) => {
		const dialog = new frappe.ui.Dialog({
			title: `Reply · ${task_name}`,
			fields: [
				{
					fieldname: "message",
					fieldtype: "Small Text",
					label: "Reply",
					reqd: 1,
				},
				{
					fieldname: "attachment",
					fieldtype: "Attach",
					label: "Attachment",
					options: "image/*,.pdf,.doc,.docx,.xls,.xlsx,.csv",
				},
			],
			primary_action_label: "Send Reply",
			primary_action(values) {
				frappe.call({
					method: "project_custom.api.nave_task.reply_to_task",
					args: {
						task_name,
						message: values.message,
						attachment: values.attachment,
					},
					freeze: true,
					callback(r) {
						if (!r.message?.ok) return;
						dialog.hide();
						frappe.show_alert({ message: "Reply posted", indicator: "green" });
						load_current(true);
						open_task_detail(task_name, true);
					},
				});
			},
		});
		dialog.show();
	};

	const open_reassign_dialog = (task_name) => {
		const dialog = new frappe.ui.Dialog({
			title: `Reassign · ${task_name}`,
			fields: [
				{
					fieldname: "assigned_to",
					fieldtype: "Link",
					options: "User",
					label: "Assign to user",
					reqd: 1,
					get_query: () => ({
						filters: { enabled: 1, user_type: "System User" },
					}),
				},
				{
					fieldname: "note",
					fieldtype: "Small Text",
					label: "Reassignment comment",
				},
			],
			primary_action_label: "Reassign",
			primary_action(values) {
				frappe.call({
					method: "project_custom.api.nave_task.reassign_task",
					args: {
						task_name,
						assigned_to: values.assigned_to,
						note: values.note,
					},
					freeze: true,
					callback(r) {
						if (!r.message?.ok) return;
						dialog.hide();
						frappe.show_alert({ message: "Task reassigned", indicator: "green" });
						load_current(true);
					},
				});
			},
		});
		dialog.show();
	};

	const open_close_dialog = (task_name) => {
		const dialog = new frappe.ui.Dialog({
			title: `Close Task · ${task_name}`,
			fields: [
				{
					fieldtype: "HTML",
					options:
						"<p>Closing removes this task from active work. This action is recorded permanently.</p>",
				},
				{
					fieldname: "remarks",
					fieldtype: "Small Text",
					label: "Closing comment",
				},
			],
			primary_action_label: "Confirm Close",
			primary_action(values) {
				frappe.confirm("Close this task?", () => {
					frappe.call({
						method: "project_custom.api.nave_task.close_task",
						args: {
							task_name,
							remarks: values.remarks,
						},
						freeze: true,
						callback(r) {
							if (!r.message?.ok) return;
							dialog.hide();
							frappe.show_alert({ message: "Task closed", indicator: "green" });
							load_current(true);
						},
					});
				});
			},
		});
		dialog.show();
	};

	const common_task_args = () => {
		const f = APP.state.filters;
		const args = {
			page: APP.state.page_no,
			page_length: APP.state.page_length,
			status: f.status || undefined,
			priority: f.priority || undefined,
			project: f.project || undefined,
			assigned_user: f.assigned_user || undefined,
			creator: f.creator || undefined,
			due_date: f.due_date || undefined,
			search: f.search || undefined,
		};
		if (APP.state._due_before) args.due_before = APP.state._due_before;
		if (APP.state._due_after) args.due_after = APP.state._due_after;
		if (APP.state._modified_after) args.modified_after = APP.state._modified_after;
		return args;
	};

	const load_dashboard = async () => {
		if (
			!frappe.project_custom ||
			typeof frappe.project_custom.mount_nave_task_dashboard !== "function"
		) {
			set_error("Dashboard UI failed to load. Please refresh the page.");
			return;
		}
		if (APP.state.dashboard_controller) {
			APP.state.dashboard_controller.refresh();
			return;
		}
		APP.$view.empty();
		APP.state.dashboard_controller = frappe.project_custom.mount_nave_task_dashboard(
			APP.$view,
			{ embedded: true }
		);
	};

	const load_task_view = async (append = false) => {
		if (!append) set_loading("Loading tasks…");
		try {
			const method = APP.VIEW_API[APP.state.view];
			const result = await call(method, common_task_args());
			const rows = result?.data || [];
			APP.state.total = result?.total || 0;
			APP.state.items = append ? APP.state.items.concat(rows) : rows;
			render_task_list(append);
		} catch (e) {
			set_error("Unable to load tasks for this view.");
		}
	};

	const load_updates_view = async (append = false) => {
		if (!append) set_loading("Loading updates…");
		try {
			const result = await call(APP.VIEW_API.task_updates, {
				page: APP.state.page_no,
				page_length: APP.state.page_length,
			});
			const rows = result?.data || [];
			APP.state.total = result?.total || 0;
			APP.state.items = append ? APP.state.items.concat(rows) : rows;
			render_updates();
		} catch (e) {
			set_error("Unable to load task updates.");
		}
	};

	const load_current = (reset = false) => {
		if (reset) {
			APP.state.page_no = 1;
			APP.state.items = [];
		}
		update_nav();
		if (APP.state.view === "dashboard") return load_dashboard();
		if (APP.state.view === "recurring_tasks") return load_recurring_view(false);
		if (APP.state.view === "task_updates") return load_updates_view(false);
		return load_task_view(false);
	};

	const set_view = (view) => {
		if (APP.state.dashboard_controller && view !== "dashboard") {
			APP.state.dashboard_controller.destroy();
			APP.state.dashboard_controller = null;
		}
		APP.state.view = view;
		APP.state.page_no = 1;
		APP.state.items = [];
		const subtitle = {
			dashboard: "Permission-aware overview of your work.",
			my_tasks: "Tasks assigned to you.",
			created_by_me: "Tasks you created.",
			all_tasks: "All tasks you are permitted to see.",
			overdue_tasks: "Past-due active tasks in your scope.",
			recurring_tasks: "Recurring templates and generated instances.",
			task_updates: "Permanent progress and discussion history.",
		};
		page.main.find(".nt-subtitle").text(subtitle[view] || "");
		load_current(true);
	};

	const bootstrap_department = () => {
		// Best-effort hint for button visibility; server remains the authority.
		frappe.call({
			method: "frappe.client.get_value",
			args: {
				doctype: "Employee",
				filters: { user_id: current_user(), status: "Active" },
				fieldname: "department",
			},
			callback(r) {
				APP.state.employee_department = r.message?.department || null;
			},
		});
	};

	ensure_styles();
	shell();
	bootstrap_department();
	set_view("dashboard");
};
