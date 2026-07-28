frappe.pages["nave-tasks"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: "My Tasks",
		single_column: true,
	});

	page.add_inner_button("← Nave Home", () => {
		frappe.set_route("nave-home");
	});

	const escape = (value) =>
		frappe.utils.escape_html(String(value || ""));

	const add_styles = () => {
		if (document.getElementById("nave-task-page-style")) return;

		$(`<style id="nave-task-page-style">
			.nave-task-page {
				min-height: calc(100vh - 90px);
				padding: 22px;
				background: linear-gradient(135deg, #f0f7ff, #f7fff9);
				border-radius: 16px;
			}
			.task-header {
				display: flex;
				justify-content: space-between;
				align-items: center;
				gap: 16px;
				padding: 22px;
				margin-bottom: 20px;
				background: #fff;
				border-radius: 16px;
				box-shadow: 0 5px 18px rgba(19, 59, 104, .08);
			}
			.task-header h2 {
				margin: 0;
				color: #123b68;
				font-weight: 800;
			}
			.task-header p {
				margin: 5px 0 0;
				color: #64748b;
			}
			.task-filters {
				display: flex;
				gap: 10px;
				margin-bottom: 18px;
				flex-wrap: wrap;
			}
			.task-filter {
				border: 0;
				border-radius: 20px;
				padding: 8px 16px;
				background: #fff;
				color: #334155;
				box-shadow: 0 2px 8px rgba(19, 59, 104, .08);
			}
			.task-filter.active {
				background: #123b68;
				color: #fff;
			}
			.task-grid {
				display: grid;
				grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
				gap: 16px;
			}
			.task-card {
				background: #fff;
				border-radius: 15px;
				padding: 18px;
				border-top: 4px solid #1683d8;
				box-shadow: 0 5px 18px rgba(19, 59, 104, .08);
			}
			.task-card.overdue {
				border-top-color: #ef4444;
			}
			.task-card.completed {
				border-top-color: #16a36a;
			}
			.task-title {
				font-size: 18px;
				font-weight: 750;
				color: #123b68;
				margin-bottom: 8px;
			}
			.task-description {
				color: #64748b;
				min-height: 42px;
				margin-bottom: 14px;
			}
			.task-meta {
				display: grid;
				grid-template-columns: 1fr 1fr;
				gap: 8px;
				font-size: 13px;
				color: #475569;
				margin-bottom: 14px;
			}
			.task-progress {
				height: 9px;
				background: #e8edf4;
				border-radius: 10px;
				overflow: hidden;
				margin: 8px 0;
			}
			.task-progress-bar {
				height: 100%;
				background: linear-gradient(90deg, #1683d8, #16a36a);
			}
			.task-footer {
				display: flex;
				justify-content: space-between;
				align-items: center;
				margin-top: 14px;
			}
			.task-status {
				padding: 5px 10px;
				border-radius: 15px;
				background: #eef6ff;
				color: #1265a8;
				font-size: 12px;
				font-weight: 700;
			}
			.task-empty {
				background: #fff;
				padding: 45px;
				text-align: center;
				border-radius: 16px;
				color: #64748b;
			}
			@media (max-width: 700px) {
				.nave-task-page { padding: 12px; }
				.task-header { align-items: flex-start; }
				.task-grid { grid-template-columns: 1fr; }
			}
		</style>`).appendTo("head");
	};

	let tasks = [];
	let active_filter = "All";

	const render = () => {
		const visible_tasks = tasks.filter((task) => {
			if (active_filter === "All") return true;
			if (active_filter === "Overdue") return Boolean(task.is_overdue);
			return task.status === active_filter;
		});

		const cards = visible_tasks.map((task) => {
			const card_class = task.is_overdue
				? "overdue"
				: task.status === "Completed"
					? "completed"
					: "";

			return `
				<div class="task-card ${card_class}">
					<div class="task-title">${escape(task.subject)}</div>
					<div class="task-description">
						${escape(task.description || "No description")}
					</div>

					<div class="task-meta">
						<div><b>ID:</b> ${escape(task.name)}</div>
						<div><b>Priority:</b> ${escape(task.priority)}</div>
						<div><b>Due:</b> ${escape(task.due_date || "-")}</div>
						<div><b>Project:</b> ${escape(task.project || "-")}</div>
					</div>

					<div>
						<b>${Number(task.progress || 0)}% Complete</b>
						<div class="task-progress">
							<div class="task-progress-bar"
								style="width:${Number(task.progress || 0)}%">
							</div>
						</div>
					</div>

					<div class="task-footer">
						<span class="task-status">${escape(task.status)}</span>
						<button class="btn btn-primary task-update"
							data-task="${escape(task.name)}">
							Submit Update
						</button>
					</div>
				</div>`;
		}).join("");

		page.main.html(`
			<div class="nave-task-page">
				<div class="task-header">
					<div>
						<h2>📋 My Tasks</h2>
						<p>View assigned work and submit progress updates.</p>
					</div>
					<button class="btn btn-primary task-refresh">Refresh</button>
				</div>

				<div class="task-filters">
					${["All", "Open", "Working", "Pending", "Completed", "Overdue"]
						.map((filter) => `
							<button class="task-filter ${
								filter === active_filter ? "active" : ""
							}" data-filter="${filter}">
								${filter}
							</button>`)
						.join("")}
				</div>

				${cards
					? `<div class="task-grid">${cards}</div>`
					: `<div class="task-empty">No tasks found.</div>`}
			</div>
		`);

		page.main.find(".task-refresh").on("click", load_tasks);

		page.main.find(".task-filter").on("click", function () {
			active_filter = $(this).data("filter");
			render();
		});

		page.main.find(".task-update").on("click", function () {
			open_update_dialog($(this).data("task"));
		});
	};

	const open_update_dialog = (task_name) => {
		const task = tasks.find((row) => row.name === task_name);
		if (!task) return;

		const dialog = new frappe.ui.Dialog({
			title: `Update ${task.name}`,
			fields: [
				{
					fieldname: "status",
					fieldtype: "Select",
					label: "Status",
					options: "Open\nWorking\nPending\nCompleted",
					default: task.status,
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
					label: "Progress Update / Reply",
					reqd: 1,
				},
				{
					fieldname: "pending_reason",
					fieldtype: "Small Text",
					label: "Pending Reason",
				},
				{
					fieldname: "support_required",
					fieldtype: "Check",
					label: "Support Required",
				},
				{
					fieldname: "attachment",
					fieldtype: "Attach",
					label: "Attachment",
				},
			],
			primary_action_label: "Submit Update",
			primary_action(values) {
				frappe.call({
					method: "project_custom.api.nave_task.submit_update",
					args: {
						task_name,
						...values,
					},
					freeze: true,
					freeze_message: "Submitting task update...",
					callback(response) {
						if (!response.message?.ok) return;

						dialog.hide();
						frappe.show_alert({
							message: "Task update submitted",
							indicator: "green",
						});
						load_tasks();
					},
				});
			},
		});

		dialog.show();
	};

	const load_tasks = () => {
		frappe.call({
			method: "project_custom.api.nave_task.get_my_tasks",
			freeze: true,
			freeze_message: "Loading tasks...",
			callback(response) {
				tasks = response.message || [];
				render();
			},
		});
	};

	add_styles();
	load_tasks();
};
