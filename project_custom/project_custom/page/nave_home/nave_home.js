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

	const cards = [
		{
			title: "Sales",
			description: "Sales performance, orders and collections",
			icon: "📈",
			color: "#1683d8",
			route: "/desk/nave-sales-dashboard",
			roles: ["Sales User", "Sales Manager"],
		},
		{
			title: "Accounts",
			description: "Accounts, payments and financial reports",
			icon: "💳",
			color: "#7c3aed",
			route: "/app/accounting",
			roles: ["Accounts User", "Accounts Manager"],
		},
		{
			title: "Purchase",
			description: "Suppliers, purchase orders and receipts",
			icon: "🛒",
			color: "#f59e0b",
			route: "/app/buying",
			roles: ["Purchase User", "Purchase Manager"],
		},
		{
			title: "Human Resources",
			description: "Employee, attendance, leave and payroll",
			icon: "👥",
			color: "#16a36a",
			route: "/app/hr",
			roles: ["HR User", "HR Manager"],
		},
		{
			title: "Projects",
			description: "Projects, tasks, costing and progress",
			icon: "📋",
			color: "#0891b2",
			route: "/app/projects",
			roles: ["Projects User", "Projects Manager"],
		},
		{
			title: "Operations",
			description: "Production, stock and quality operations",
			icon: "🏭",
			color: "#173b67",
			route: "/app/manufacturing",
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
			title: "Feedback Dashboard",
			description: "Customer satisfaction and follow-up",
			icon: "⭐",
			color: "#e34b4b",
			route: "/desk/customer-feedback-dashboard",
			roles: ["System Manager"],
		},
	];

	const visible_cards = cards.filter((card) => has_role(card.roles));
	const full_name =
		frappe.boot.user.full_name ||
		frappe.session.user ||
		"Employee";

	const card_html = visible_cards
		.map(
			(card) => `
				<a class="nave-home-card"
					href="${card.route}"
					style="--card-color: ${card.color}">
					<div class="nave-home-icon">${card.icon}</div>
					<div>
						<h3>${frappe.utils.escape_html(card.title)}</h3>
						<p>${frappe.utils.escape_html(card.description)}</p>
						<span>Open Dashboard →</span>
					</div>
				</a>
			`
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
					radial-gradient(circle at top right, #dbeafe 0, transparent 34%),
					radial-gradient(circle at bottom left, #dcfce7 0, transparent 30%),
					#f5f8fc;
			}

			.nave-home-header {
				display: flex;
				align-items: center;
				gap: 24px;
				padding: 24px 28px;
				margin-bottom: 24px;
				border-radius: 20px;
				background: linear-gradient(120deg, #ffffff, #eef6ff);
				box-shadow: 0 8px 25px rgba(23, 59, 103, 0.09);
			}

			.nave-home-logo {
				width: 155px;
				max-height: 68px;
				object-fit: contain;
			}

			.nave-home-header h1 {
				margin: 0;
				color: #173b67;
				font-size: 30px;
				font-weight: 800;
			}

			.nave-home-header p {
				margin: 6px 0 0;
				color: #64748b;
				font-size: 15px;
			}

			.nave-home-grid {
				display: grid;
				grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
				gap: 18px;
			}

			.nave-home-card {
				display: flex;
				gap: 17px;
				align-items: flex-start;
				min-height: 165px;
				padding: 22px;
				color: inherit;
				text-decoration: none !important;
				background: #ffffff;
				border-radius: 18px;
				border-top: 5px solid var(--card-color);
				box-shadow: 0 7px 22px rgba(23, 59, 103, 0.08);
				transition: transform 0.2s ease, box-shadow 0.2s ease;
			}

			.nave-home-card:hover {
				transform: translateY(-5px);
				box-shadow: 0 13px 30px rgba(23, 59, 103, 0.15);
			}

			.nave-home-icon {
				display: grid;
				place-items: center;
				flex: 0 0 58px;
				height: 58px;
				border-radius: 16px;
				background: color-mix(in srgb, var(--card-color) 13%, white);
				font-size: 29px;
			}

			.nave-home-card h3 {
				margin: 2px 0 8px;
				color: #173b67;
				font-size: 20px;
				font-weight: 750;
			}

			.nave-home-card p {
				min-height: 42px;
				margin: 0 0 13px;
				color: #64748b;
				line-height: 1.45;
			}

			.nave-home-card span {
				color: var(--card-color);
				font-weight: 700;
			}

			.nave-home-quick {
				display: flex;
				flex-wrap: wrap;
				gap: 12px;
				margin-top: 24px;
				padding: 18px;
				background: #ffffff;
				border-radius: 16px;
			}

			.nave-home-quick a {
				padding: 9px 15px;
				border-radius: 10px;
				color: #173b67;
				background: #eef4fb;
				font-weight: 650;
				text-decoration: none;
			}

			@media (max-width: 700px) {
				.nave-home {
					padding: 14px;
				}

				.nave-home-header {
					align-items: flex-start;
					flex-direction: column;
					padding: 20px;
				}

				.nave-home-logo {
					width: 125px;
				}

				.nave-home-header h1 {
					font-size: 24px;
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

			<div class="nave-home-grid">
				${card_html}
			</div>

			<div class="nave-home-quick">
				<a href="/app/todo">✓ My ToDo</a>
				<a href="/app/notification-log">🔔 Notifications</a>
				<a href="/app/user-profile">👤 My Profile</a>
				<a href="/feedback" target="_blank">⭐ Feedback Portal</a>
			</div>
		</div>
	`);
};
