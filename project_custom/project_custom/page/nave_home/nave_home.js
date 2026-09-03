frappe.pages["nave-home"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: "Nave Home",
		single_column: true,
	});

	const roles = frappe.user_roles || [];
	const is_admin =
		frappe.session.user === "Administrator" ||
		roles.includes("System Manager");

	const has_role = (allowed_roles) =>
		is_admin || allowed_roles.some((role) => roles.includes(role));

	// Prefer frappe.set_route (SPA). href is a /desk fallback for open-in-new-tab.
	const cards = [
		{
			title: "NAVE Tasks",
			description: "Tasks, dashboard KPIs, overdue work and updates",
			icon: "📋",
			color: "#1683d8",
			route: ["nave-tasks"],
			href: "/desk/nave-tasks",
			roles: [
				"Employee",
				"NAVE Task Manager",
				"NAVE Task Director",
				"System Manager",
			],
		},
                {
                        title: "Opportunity Dashboard",
                        description: "Opportunity pipeline, follow-ups and sales progress",
                        icon: "🎯",
                        color: "#7c3aed",
                        route: ["Workspaces", "Opportunity Dashboard"],
                        href: "/desk/opportunity-dashboard",
                        roles: [
                                "Sales User",
                                "Sales Manager",
                                "Nave CRM User",
                                "Nave CRM Manager",
                                "System Manager",
                        ],
                },
		{
			title: "Sales",
			description: "Sales performance, orders and collections",
			icon: "📈",
			color: "#1683d8",
			route: ["nave-sales-dashboard"],
			href: "/desk/nave-sales-dashboard",
			roles: ["Sales User", "Sales Manager"],
		},
		{
			title: "Accounts",
			description: "Accounts, payments and financial reports",
			icon: "💳",
			color: "#7c3aed",
			route: ["List", "Account"],
			href: "/desk/account",
			roles: ["Accounts User", "Accounts Manager"],
		},
		{
			title: "Purchase",
			description: "Suppliers, purchase orders and receipts",
			icon: "🛒",
			color: "#f59e0b",
			route: ["List", "Purchase Order"],
			href: "/desk/purchase-order",
			roles: ["Purchase User", "Purchase Manager"],
		},
		{
			title: "Human Resources",
			description: "Employee, attendance, leave and payroll",
			icon: "👥",
			color: "#16a36a",
			route: ["List", "Employee"],
			href: "/desk/employee",
			roles: ["HR User", "HR Manager"],
		},
		{
			title: "Projects",
			description: "Projects, tasks, costing and progress",
			icon: "📋",
			color: "#0891b2",
			route: ["List", "Project"],
			href: "/desk/project",
			roles: ["Projects User", "Projects Manager"],
		},
		{
			title: "Operations",
			description: "Production, stock and quality operations",
			icon: "🏭",
			color: "#173b67",
			route: ["List", "Work Order"],
			href: "/desk/work-order",
			roles: [
				"Manufacturing User",
				"Manufacturing Manager",
				"Stock User",
				"Stock Manager",
				"Quality User",
				"Quality Manager",
			],
		},
		{
			title: "Project Unbilled Expense Alert",
			description: "Projects with unbilled expense above threshold",
			icon: "₹",
			color: "#b45309",
			route: ["query-report", "NAVE Project Unbilled Expense Alert"],
			href: "/desk/query-report/NAVE%20Project%20Unbilled%20Expense%20Alert",
			roles: [
				"System Manager",
				"Accounts Manager",
				"Projects Manager",
				"NAVE Task Director",
				"NAVE Task Manager",
			],
		},
		{
			title: "Customer Feedback",
			description: "Submitted feedback records and follow-up",
			icon: "💬",
			color: "#e34b4b",
			route: ["List", "Customer Feedback"],
			href: "/desk/customer-feedback",
			roles: ["System Manager"],
		},
	];

	const visible_cards = cards.filter((card) => has_role(card.roles));

	const user_info =
		(frappe.user_info && frappe.user_info(frappe.session.user)) || {};

	const fallback_name = (frappe.session.user || "Employee")
		.split("@")[0]
		.replace(/[._-]+/g, " ")
		.replace(/\b\w/g, (letter) => letter.toUpperCase());

	const full_name =
		user_info.fullname || user_info.full_name || fallback_name;

	const card_html = visible_cards
		.map(
			(card, idx) => `
			<a class="nave-home-card"
				href="${frappe.utils.escape_html(card.href)}"
				data-card-idx="${idx}"
				style="--card-color:${card.color}">
				<div class="nave-home-icon">${card.icon}</div>
				<div>
					<h3>${frappe.utils.escape_html(card.title)}</h3>
					<p>${frappe.utils.escape_html(card.description)}</p>
					<span>Open Module →</span>
				</div>
			</a>`
		)
		.join("");

	page.main.html(`
		<style>
			.layout-main-section {
				background: transparent !important;
			}

			.nave-home {
				min-height: calc(100vh - 100px);
				padding: 28px;
				border-radius: 20px;
				background:
					radial-gradient(
						circle at top right,
						#dbeafe,
						transparent 35%
					),
					radial-gradient(
						circle at bottom left,
						#dcfce7,
						transparent 30%
					),
					#f6f8fc;
			}

			.nave-home-header {
				display: flex;
				align-items: center;
				gap: 28px;
				padding: 28px 36px;
				margin-bottom: 30px;
				border-radius: 20px;
				background: rgba(255, 255, 255, 0.88);
				box-shadow: 0 8px 24px rgba(23, 59, 103, 0.08);
			}

			.nave-home-logo {
				width: 200px;
				height: auto;
				object-fit: contain;
			}

			.nave-home-header h1 {
				margin: 0;
				color: #123f73;
				font-size: 34px;
				font-weight: 800;
			}

			.nave-home-header p {
				margin: 6px 0 0;
				color: #64748b;
				font-size: 17px;
			}

			.nave-home-grid {
				display: grid;
				grid-template-columns:
					repeat(auto-fit, minmax(270px, 1fr));
				gap: 22px;
			}

			.nave-home-card {
				display: flex;
				gap: 20px;
				min-height: 160px;
				padding: 28px;
				border-radius: 20px;
				border-top: 5px solid var(--card-color);
				background: #ffffff;
				color: inherit;
				text-decoration: none !important;
				box-shadow: 0 8px 24px rgba(23, 59, 103, 0.08);
				transition:
					transform 0.2s ease,
					box-shadow 0.2s ease;
				cursor: pointer;
			}

			.nave-home-card:hover {
				transform: translateY(-5px);
				box-shadow: 0 14px 30px rgba(23, 59, 103, 0.14);
			}

			.nave-home-icon {
				display: flex;
				align-items: center;
				justify-content: center;
				flex: 0 0 72px;
				width: 72px;
				height: 72px;
				border-radius: 18px;
				background: color-mix(
					in srgb,
					var(--card-color) 13%,
					white
				);
				font-size: 34px;
			}

			.nave-home-card h3 {
				margin: 2px 0 8px;
				color: #123f73;
				font-size: 25px;
				font-weight: 800;
			}

			.nave-home-card p {
				min-height: 50px;
				margin: 0 0 15px;
				color: #64748b;
				font-size: 16px;
				line-height: 1.5;
			}

			.nave-home-card span {
				color: var(--card-color);
				font-size: 16px;
				font-weight: 750;
			}

			.nave-home-quick {
				display: flex;
				flex-wrap: wrap;
				gap: 14px;
				margin-top: 30px;
				padding: 22px;
				border-radius: 18px;
				background: rgba(255, 255, 255, 0.9);
			}

			.nave-home-quick a {
				padding: 11px 18px;
				border-radius: 10px;
				background: #eef4fb;
				color: #123f73;
				font-weight: 700;
				text-decoration: none;
			}

			.nave-home-empty {
				padding: 30px;
				border-radius: 16px;
				background: white;
				color: #64748b;
				text-align: center;
			}

			@media (max-width: 700px) {
				.nave-home {
					padding: 14px;
				}

				.nave-home-header {
					align-items: flex-start;
					flex-direction: column;
					padding: 22px;
				}

				.nave-home-logo {
					width: 145px;
				}

				.nave-home-header h1 {
					font-size: 25px;
				}

				.nave-home-card {
					padding: 22px;
				}
			}
		</style>

		<div class="nave-home">
			<div class="nave-home-header">
				<img class="nave-home-logo"
					src="/assets/project_custom/images/nave-logo.png"
					alt="Nave Industries">
				<div>
					<h1>Welcome, ${frappe.utils.escape_html(full_name)}</h1>
					<p>Select your department to start working.</p>
				</div>
			</div>

			${
				card_html
					? `<div class="nave-home-grid">${card_html}</div>`
					: `<div class="nave-home-empty">
						No department is assigned to your account.
					   </div>`
			}

			<div class="nave-home-quick">
				<a href="/desk/todo" class="nave-home-quick-link" data-route='["List","ToDo"]'>✓ My ToDo</a>
				<a href="/desk/notification-log" class="nave-home-quick-link" data-route='["List","Notification Log"]'>
					🔔 Notifications
				</a>
				<a href="/feedback" target="_blank" rel="noopener">
					⭐ Feedback Portal
				</a>
			</div>
		</div>
	`);

	page.main.find(".nave-home-card").on("click", function (e) {
		const idx = parseInt($(this).attr("data-card-idx"), 10);
		const card = visible_cards[idx];
		if (!card || !card.route || !card.route.length) {
			return;
		}
		e.preventDefault();
		frappe.set_route(...card.route);
	});

	page.main.find(".nave-home-quick-link").on("click", function (e) {
		const raw = $(this).attr("data-route");
		if (!raw) {
			return;
		}
		e.preventDefault();
		try {
			const route = JSON.parse(raw);
			if (Array.isArray(route) && route.length) {
				frappe.set_route(...route);
			}
		} catch (err) {
			// fall through to href
		}
	});
};
