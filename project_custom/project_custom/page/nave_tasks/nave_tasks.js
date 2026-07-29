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

	const action_visibility = (task) => {
		const closed = task.status === "Closed";
		const cancelled = task.status === "Cancelled";
		const manage = can_manage_task(task);
		const update = can_submit_update(task);
		return {
			open_task: true,
			view_updates: true,
			reply: !cancelled,
			submit_update: update && !cancelled && (!closed || manage),
			reassign: manage && !cancelled,
			close_task: manage && !closed && !cancelled,
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
			set_view($(this).data("view"));
		});
		page.main.find(".nt-refresh").on("click", () => load_current(true));
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
		} else {
			APP.state._due_before = "";
			APP.state._due_after = "";
		}
		if (key === "recently_updated") {
			APP.state._due_before = "";
			APP.state._due_after = "";
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
					.map(
						(row) => `
					<div class="nt-update-row">
						<div class="nt-badges">
							<span class="nt-badge">${escape(row.update_type || "Progress Update")}</span>
							<span class="nt-badge status-${escape(row.status)}">${escape(row.status || "-")}</span>
						</div>
						<div><b>Task:</b> ${escape(row.task)}</div>
						<div><b>By:</b> ${escape(row.update_by || row.employee || "-")}</div>
						<div><b>When:</b> ${escape(row.updated_on || "-")}</div>
						<div class="nt-timeline-text" style="margin-top:8px;">${escape(row.update_text || "")}</div>
						${
							row.attachment
								? `<a class="nt-attach-link" href="${escape(
										row.attachment
								  )}" target="_blank" rel="noopener">Attachment</a>`
								: ""
						}
						<div style="margin-top:8px;">
							<button class="btn btn-default btn-sm nt-act" data-act="open" data-task="${escape(
								row.task
							)}">Open Task</button>
						</div>
					</div>`
					)
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

	const timeline_html = (items) => {
		if (!items.length) {
			return `<div class="nt-empty">No updates yet. Start the discussion with a reply or progress update.</div>`;
		}
		return `
			<div class="nt-timeline">
				${items
					.map((item) => {
						const who =
							item.sender_full_name ||
							item.update_by ||
							item.employee_name ||
							item.employee ||
							"User";
						const initial = String(who).trim().charAt(0).toUpperCase() || "?";
						const attach = item.attachment || "";
						const is_image = /\.(png|jpe?g|gif|webp)$/i.test(attach);
						const type = item.update_type || "Progress Update";
						return `
						<div class="nt-timeline-item ${type_css_class(type)}">
							<div class="nt-timeline-avatar">${escape(initial)}</div>
							<div class="nt-timeline-bubble">
								<div class="nt-timeline-meta">
									<strong>${escape(who)}</strong>
									<span class="nt-role-badge role-${escape(
										(item.display_role || "Employee").toLowerCase()
									)}">${escape(item.display_role || "Employee")}</span>
									<span class="nt-badge">${escape(type)}</span>
									<span>${escape(item.datetime || item.updated_on || "")}</span>
									${
										item.sender_user_id
											? `<span class="nt-muted">${escape(item.sender_user_id)}</span>`
											: ""
									}
									${
										item.employee_name
											? `<span class="nt-muted">${escape(item.employee_name)}</span>`
											: ""
									}
									${item.status ? `<span class="nt-badge status-${escape(item.status)}">${escape(item.status)}</span>` : ""}
									${item.progress != null ? `<span>${escape(item.progress)}%</span>` : ""}
								</div>
								<div class="nt-timeline-text">${escape(item.update_text || "")}</div>
								${
									attach
										? `<a class="nt-attach-link" href="${escape(
												attach
										  )}" target="_blank" rel="noopener">Download attachment</a>`
										: ""
								}
								${
									attach && is_image
										? `<img class="nt-attach-preview" src="${escape(
												attach
										  )}" alt="Attachment preview">`
										: ""
								}
							</div>
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
			<div class="nt-composer">
				<h4>Post to conversation</h4>
				<textarea class="form-control nt-composer-message" rows="3" placeholder="Write a message…"></textarea>
				<div class="nt-composer-row">
					<select class="form-control nt-composer-type">
						${types
							.map((t) => `<option value="${escape(t)}">${escape(t)}</option>`)
							.join("")}
					</select>
					<input type="text" class="form-control nt-composer-attachment" placeholder="Attachment URL / file path" readonly>
					<button type="button" class="btn btn-default btn-sm nt-composer-attach">Attach</button>
					<button type="button" class="btn btn-primary btn-sm nt-composer-submit">Submit</button>
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
		dialog.show();
		dialog.fields_dict.body.$wrapper.html(
			`<div class="nt-loading"><span class="nt-spinner"></span> Loading task…</div>`
		);

		const render_detail = async () => {
			try {
				const payload = await call(APP.VIEW_API.timeline, { task_name });
				const task = payload.task || {};
				const actions = action_visibility(task);
				const action_buttons = [];
				if (actions.submit_update) {
					action_buttons.push(
						`<button class="btn btn-primary btn-sm nt-detail-act" data-act="update">Submit Update</button>`
					);
				}
				if (actions.reassign) {
					action_buttons.push(
						`<button class="btn btn-default btn-sm nt-detail-act" data-act="reassign">Reassign</button>`
					);
				}
				if (actions.close_task) {
					action_buttons.push(
						`<button class="btn btn-danger btn-sm nt-detail-act" data-act="close">Close Task</button>`
					);
				}
				action_buttons.push(
					`<a class="btn btn-default btn-sm" href="/app/nave-task/${encodeURIComponent(
						task.name
					)}" target="_blank" rel="noopener">Open Form</a>`
				);

				const show_composer = actions.reply || actions.submit_update;
				dialog.fields_dict.body.$wrapper.html(`
					<div class="nt-detail-grid">
						<div class="nt-detail-section">
							<h4>${escape(task.subject || task_name)}</h4>
							<div class="nt-badges">
								<span class="nt-badge status-${escape(task.status)}">${escape(task.status)}</span>
								<span class="nt-badge priority-${escape(task.priority)}">${escape(task.priority)}</span>
								${due_badges(task).join("")}
							</div>
							<div class="nt-task-desc">${escape(task.description || "No description")}</div>
							<div class="nt-meta">
								<div><b>ID:</b> ${escape(task.name)}</div>
								<div><b>Assignee:</b> ${escape(task.assigned_to || "-")}</div>
								<div><b>Created by:</b> ${escape(task.assigned_by || task.owner || "-")}</div>
								<div><b>Project:</b> ${escape(task.project || "-")}</div>
								<div><b>Due:</b> ${escape(task.due_date || "-")}</div>
								<div><b>Progress:</b> ${escape(task.progress || 0)}%</div>
								<div><b>Overdue:</b> ${as_int(task.is_overdue) ? "Yes" : "No"}</div>
								<div><b>Latest:</b> ${escape(task.latest_update || "-")}</div>
							</div>
							<div class="nt-actions" style="margin-top:12px;">${action_buttons.join("")}</div>
						</div>
						<div class="nt-detail-section">
							<h4>Discussion timeline</h4>
							${timeline_html(payload.timeline || [])}
							${show_composer ? composer_html(payload.allowed_update_types || []) : ""}
						</div>
					</div>
				`);

				dialog.fields_dict.body.$wrapper.find(".nt-detail-act").on("click", function () {
					const act = $(this).data("act");
					dialog.hide();
					if (act === "update") open_update_dialog(task);
					if (act === "reassign") open_reassign_dialog(task.name);
					if (act === "close") open_close_dialog(task.name);
				});

				const $wrap = dialog.fields_dict.body.$wrapper;
				$wrap.find(".nt-composer-attach").on("click", () => {
					new frappe.ui.FileUploader({
						restrictions: {
							allowed_file_types: [
								"image/*",
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
						},
					});
				});

				$wrap.find(".nt-composer-submit").on("click", async () => {
					const message = $wrap.find(".nt-composer-message").val();
					const update_type = $wrap.find(".nt-composer-type").val();
					const attachment = $wrap.find(".nt-composer-attachment").val();
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
						},
						freeze: true,
						freeze_message: "Posting…",
						callback(r) {
							if (!r.message?.ok) return;
							frappe.show_alert({ message: "Posted to conversation", indicator: "green" });
							render_detail();
							load_current(true);
						},
					});
				});

				if (focus_timeline) {
					dialog.$wrapper.find(".nt-timeline").get(0)?.scrollIntoView({ behavior: "smooth" });
				}
			} catch (e) {
				dialog.fields_dict.body.$wrapper.html(
					`<div class="nt-error">Unable to load task details.</div>`
				);
			}
		};

		await render_detail();
	};

	const open_update_dialog = (task) => {
		if (task.status === "Closed" && !can_manage_task(task)) {
			frappe.msgprint("Closed tasks cannot accept normal updates.");
			return;
		}
		const dialog = new frappe.ui.Dialog({
			title: `Update ${task.name || ""}`,
			fields: [
				{
					fieldname: "status",
					fieldtype: "Select",
					label: "Status",
					options: "Open\nWorking\nPending\nCompleted",
					default: task.status === "Closed" ? "Open" : task.status || "Working",
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
		return args;
	};

	const load_dashboard = async () => {
		set_loading("Loading dashboard…");
		try {
			const counts = await call(APP.VIEW_API.dashboard);
			APP.state.counts = counts;
			render_dashboard(counts);
		} catch (e) {
			set_error("Unable to load dashboard counters.");
		}
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
