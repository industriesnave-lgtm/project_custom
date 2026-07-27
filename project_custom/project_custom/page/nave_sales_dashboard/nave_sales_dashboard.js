frappe.pages["nave-sales-dashboard"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: "Sales Dashboard",
		single_column: true,
	});
page.add_inner_button("← Nave Home", () => {
	frappe.set_route("nave-home");
});

	const currency = (value) => format_currency(value || 0);

	const add_styles = () => {
		if (document.getElementById("nave-sales-dashboard-style")) return;

		$(`<style id="nave-sales-dashboard-style">
			.nave-sales-dashboard {
				background: #f6f8fc;
				min-height: calc(100vh - 90px);
				padding: 24px;
				border-radius: 14px;
			}
			.nave-dashboard-header {
				display: flex;
				align-items: center;
				justify-content: space-between;
				gap: 20px;
				background: #ffffff;
				padding: 18px 24px;
				border-radius: 14px;
				margin-bottom: 22px;
				box-shadow: 0 4px 16px rgba(23, 59, 103, 0.08);
			}
			.nave-brand {
				display: flex;
				align-items: center;
				gap: 16px;
			}
			.nave-logo {
				width: 150px;
				height: auto;
				max-height: 54px;
				object-fit: contain;
			}
			.nave-dashboard-title {
				margin: 0;
				color: #173b67;
				font-size: 24px;
				font-weight: 700;
			}
			.nave-dashboard-subtitle {
				color: #748096;
				margin-top: 4px;
			}
			.nave-kpi-grid {
				display: grid;
				grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
				gap: 16px;
				margin-bottom: 22px;
			}
			.nave-kpi-card {
				background: #fff;
				border-radius: 14px;
				padding: 18px;
				border-top: 4px solid #1683d8;
				box-shadow: 0 4px 16px rgba(23, 59, 103, 0.07);
			}
			.nave-kpi-card.success { border-top-color: #16a36a; }
			.nave-kpi-card.alert { border-top-color: #e34b4b; }
			.nave-kpi-card.warning { border-top-color: #f59e0b; }
			.nave-kpi-label {
				color: #64748b;
				font-size: 13px;
				font-weight: 600;
			}
			.nave-kpi-value {
				color: #173b67;
				font-size: 27px;
				font-weight: 700;
				margin-top: 10px;
			}
			.nave-panel {
				background: #fff;
				padding: 22px;
				border-radius: 14px;
				box-shadow: 0 4px 16px rgba(23, 59, 103, 0.07);
			}
			.nave-panel h4 {
				color: #173b67;
				margin: 0 0 16px;
				font-weight: 700;
			}
			.nave-invoice-table {
				width: 100%;
				border-collapse: collapse;
			}
			.nave-invoice-table th,
			.nave-invoice-table td {
				padding: 12px 8px;
				border-bottom: 1px solid #eef1f6;
				text-align: left;
			}
			.nave-invoice-table th {
				color: #64748b;
				font-size: 12px;
				text-transform: uppercase;
			}
			.nave-status {
				padding: 4px 8px;
				border-radius: 20px;
				background: #eff6ff;
				color: #1683d8;
				font-size: 12px;
				font-weight: 600;
			}
			@media (max-width: 700px) {
				.nave-sales-dashboard { padding: 12px; }
				.nave-dashboard-header { align-items: flex-start; }
				.nave-logo { width: 110px; }
				.nave-dashboard-title { font-size: 20px; }
			}
		</style>`).appendTo("head");
	};

	const render_dashboard = (data) => {
		const cards = [
			["Today Sales", currency(data.today_sales), "success"],
			["This Month Sales", currency(data.month_sales), ""],
			["Pending Sales Order", data.pending_orders || 0, "warning"],
			["Pending Collection", currency(data.pending_collection), "warning"],
			["Overdue Payment", currency(data.overdue_amount), "alert"],
			["Credit Note (This Month)", currency(data.credit_note_amount), "alert"],
		];

		const card_html = cards
			.map(
				([label, value, tone]) => `
					<div class="nave-kpi-card ${tone}">
						<div class="nave-kpi-label">${label}</div>
						<div class="nave-kpi-value">${value}</div>
					</div>`
			)
			.join("");

		const invoice_rows = (data.recent_invoices || [])
			.map(
				(invoice) => `
					<tr>
						<td><a href="/app/sales-invoice/${invoice.name}">${invoice.name}</a></td>
						<td>${frappe.utils.escape_html(invoice.customer || "")}</td>
						<td>${currency(invoice.grand_total)}</td>
						<td>${currency(invoice.outstanding_amount)}</td>
						<td><span class="nave-status">${invoice.status || ""}</span></td>
					</tr>`
			)
			.join("");

		page.main.html(`
			<div class="nave-sales-dashboard">
				<div class="nave-dashboard-header">
					<div class="nave-brand">
						<img class="nave-logo"
							src="/assets/project_custom/images/nave-logo.png"
							alt="Nave Industries"
							onerror="this.style.display='none'">
						<div>
							<h2 class="nave-dashboard-title">Sales Dashboard</h2>
							<div class="nave-dashboard-subtitle">Nave Industries sales performance overview</div>
						</div>
					</div>
					<button class="btn btn-primary nave-refresh">Refresh</button>
				</div>

				<div class="nave-kpi-grid">${card_html}</div>

				<div class="nave-panel">
					<h4>Recent Sales Invoices</h4>
					<table class="nave-invoice-table">
						<thead>
							<tr>
								<th>Invoice</th>
								<th>Customer</th>
								<th>Amount</th>
								<th>Outstanding</th>
								<th>Status</th>
							</tr>
						</thead>
						<tbody>${invoice_rows}</tbody>
					</table>
				</div>
			</div>
		`);

		page.main.find(".nave-refresh").on("click", load_dashboard);
	};

	const load_dashboard = () => {
		frappe.call({
			method: "project_custom.api.sales_dashboard.get_sales_dashboard",
			freeze: true,
			freeze_message: "Loading sales dashboard...",
			callback: ({ message }) => render_dashboard(message || {}),
		});
	};

	add_styles();
	load_dashboard();
};
