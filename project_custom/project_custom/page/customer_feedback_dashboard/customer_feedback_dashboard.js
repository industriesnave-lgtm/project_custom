frappe.pages["customer-feedback-dashboard"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: "Customer Feedback Dashboard",
		single_column: true,
	});
	page.add_inner_button("← Nave Home", () => {
		frappe.set_route("nave-home");
	});
	const KPI_NAV = {
		total_feedback: {
			kind: "list",
			doctype: "Customer Feedback",
			filters: () => ({}),
		},
		positive_feedback: {
			kind: "list",
			doctype: "Customer Feedback",
			filters: () => ({ follow_up_status: "Positive" }),
		},
		low_rating: {
			kind: "list",
			doctype: "Customer Feedback",
			filters: () => ({ follow_up_status: "Urgent" }),
		},
		google_review_pending: {
			kind: "list",
			doctype: "Customer Feedback",
			filters: () => ({ google_review_status: "Pending" }),
		},
		// average_rating: no meaningful single list destination
	};

	const open_kpi_nav = (nav) => {
		if (!nav || nav.kind !== "list" || !nav.doctype) {
			return;
		}
		const filters =
			typeof nav.filters === "function" ? nav.filters() : nav.filters || {};
		frappe.route_options = filters;
		frappe.set_route("List", nav.doctype);
	};

	const escape = (value) =>
		frappe.utils.escape_html(String(value || ""));

	const addStyles = () => {
		if (document.getElementById("nave-feedback-dashboard-style")) {
			return;
		}

		$(`<style id="nave-feedback-dashboard-style">
			.feedback-dashboard {
				padding: 22px;
				min-height: calc(100vh - 90px);
				background: #f4f7fb;
				border-radius: 16px;
			}
			.feedback-dashboard-header {
				display: flex;
				align-items: center;
				justify-content: space-between;
				gap: 20px;
				padding: 20px 24px;
				margin-bottom: 20px;
				background: #fff;
				border-radius: 14px;
				box-shadow: 0 5px 18px rgba(18, 59, 104, 0.08);
			}
			.feedback-dashboard-brand {
				display: flex;
				align-items: center;
				gap: 18px;
			}
			.feedback-dashboard-logo {
				width: 145px;
				max-height: 62px;
				object-fit: contain;
			}
			.feedback-dashboard-header h2 {
				margin: 0;
				color: #123b68;
				font-weight: 800;
			}
			.feedback-dashboard-header p {
				margin: 4px 0 0;
				color: #64748b;
			}
			.feedback-kpi-grid {
				display: grid;
				grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
				gap: 15px;
				margin-bottom: 20px;
			}
			.feedback-kpi {
				padding: 19px;
				background: #fff;
				border-top: 4px solid #1683d8;
				border-radius: 13px;
				box-shadow: 0 5px 18px rgba(18, 59, 104, 0.07);
			}
			.feedback-kpi.is-clickable {
				cursor: pointer;
				transition: transform 0.12s ease, box-shadow 0.12s ease;
			}
			.feedback-kpi.is-clickable:hover {
				transform: translateY(-1px);
				box-shadow: 0 8px 20px rgba(18, 59, 104, 0.12);
			}
			.feedback-kpi.is-static {
				cursor: default;
			}
			.feedback-kpi.success { border-top-color: #16a36a; }
			.feedback-kpi.warning { border-top-color: #f59e0b; }
			.feedback-kpi.alert { border-top-color: #e34b4b; }
			.feedback-kpi-label {
				color: #64748b;
				font-size: 13px;
				font-weight: 650;
			}
			.feedback-kpi-value {
				margin-top: 8px;
				color: #123b68;
				font-size: 28px;
				font-weight: 800;
			}
			.feedback-dashboard-grid {
				display: grid;
				grid-template-columns: 1.4fr 1fr;
				gap: 18px;
				margin-bottom: 20px;
			}
			.feedback-panel {
				padding: 21px;
				background: #fff;
				border-radius: 14px;
				box-shadow: 0 5px 18px rgba(18, 59, 104, 0.07);
			}
			.feedback-panel h4 {
				margin: 0 0 16px;
				color: #123b68;
				font-weight: 750;
			}
			.feedback-breakdown-row {
				display: grid;
				grid-template-columns: minmax(120px, 1fr) 2fr 45px;
				align-items: center;
				gap: 10px;
				margin-bottom: 12px;
			}
			.feedback-breakdown-label {
				overflow: hidden;
				color: #475569;
				text-overflow: ellipsis;
				white-space: nowrap;
			}
			.feedback-breakdown-track {
				height: 9px;
				overflow: hidden;
				background: #e8edf4;
				border-radius: 10px;
			}
			.feedback-breakdown-fill {
				height: 100%;
				background: #1683d8;
				border-radius: 10px;
			}
			.feedback-table {
				width: 100%;
				border-collapse: collapse;
			}
			.feedback-table th,
			.feedback-table td {
				padding: 11px 8px;
				border-bottom: 1px solid #e8edf4;
				text-align: left;
				vertical-align: top;
			}
			.feedback-table th {
				color: #64748b;
				font-size: 12px;
				text-transform: uppercase;
			}
			.feedback-text {
				max-width: 330px;
				white-space: normal;
			}
			.feedback-status {
				display: inline-block;
				padding: 4px 8px;
				border-radius: 20px;
				background: #eff6ff;
				color: #1683d8;
				font-size: 12px;
				font-weight: 700;
			}
			.feedback-status.Urgent {
				background: #fef2f2;
				color: #dc2626;
			}
			.feedback-status.Review-Required {
				background: #fff7ed;
				color: #d97706;
			}
			.feedback-status.Positive {
				background: #ecfdf5;
				color: #15803d;
			}
			@media (max-width: 900px) {
				.feedback-dashboard-grid {
					grid-template-columns: 1fr;
				}
			}
			@media (max-width: 700px) {
				.feedback-dashboard { padding: 12px; }
				.feedback-dashboard-header {
					align-items: flex-start;
					flex-direction: column;
				}
				.feedback-dashboard-logo { width: 120px; }
				.feedback-panel { overflow-x: auto; }
			}
		</style>`).appendTo("head");
	};

	const renderBreakdown = (items) => {
		if (!items || !items.length) {
			return `<div class="text-muted">No feedback available.</div>`;
		}

		const maximum = Math.max(...items.map((item) => item.value), 1);

		return items
			.map(
				(item) => `
					<div class="feedback-breakdown-row">
						<div class="feedback-breakdown-label"
							title="${escape(item.label)}">
							${escape(item.label)}
						</div>
						<div class="feedback-breakdown-track">
							<div class="feedback-breakdown-fill"
								style="width:${(item.value / maximum) * 100}%">
							</div>
						</div>
						<strong>${item.value}</strong>
					</div>`
			)
			.join("");
	};

	const renderRecentFeedback = (items) => {
		if (!items || !items.length) {
			return `
				<tr>
					<td colspan="7" class="text-muted">
						No feedback submitted yet.
					</td>
				</tr>`;
		}

		return items
			.map((item) => {
				const statusClass = escape(
					(item.follow_up_status || "").replaceAll(" ", "-")
				);

				return `
					<tr>
						<td>
							<a class="feedback-doc-link" href="/desk/customer-feedback/${encodeURIComponent(
								item.name
							)}" data-doctype="Customer Feedback" data-name="${escape(
					item.name
				)}">
								${escape(item.name)}
							</a>
						</td>
						<td>${escape(item.customer_company)}</td>
						<td>${escape(item.project_site)}</td>
						<td>${escape(item.service_type)}</td>
						<td>${item.overall_rating} / 5</td>
						<td class="feedback-text">${escape(item.feedback)}</td>
						<td>
							<span class="feedback-status ${statusClass}">
								${escape(item.follow_up_status)}
							</span>
						</td>
					</tr>`;
			})
			.join("");
	};

	const renderDashboard = (data) => {
		page.main.html(`
			<div class="feedback-dashboard">
				<div class="feedback-dashboard-header">
					<div class="feedback-dashboard-brand">
						<img class="feedback-dashboard-logo"
							src="/assets/project_custom/images/nave-logo.png"
							alt="Nave Industries">
						<div>
							<h2>Customer Feedback Dashboard</h2>
							<p>Customer satisfaction and follow-up overview</p>
						</div>
					</div>
					<button class="btn btn-primary feedback-refresh">
						Refresh
					</button>
				</div>

				<div class="feedback-kpi-grid">
					<div class="feedback-kpi is-clickable" data-kpi="total_feedback" role="button" tabindex="0">
						<div class="feedback-kpi-label">Total Feedback</div>
						<div class="feedback-kpi-value">
							${data.total_feedback || 0}
						</div>
					</div>
					<div class="feedback-kpi success is-static">
						<div class="feedback-kpi-label">Average Rating</div>
						<div class="feedback-kpi-value">
							${data.average_rating || 0} / 5
						</div>
					</div>
					<div class="feedback-kpi success is-clickable" data-kpi="positive_feedback" role="button" tabindex="0">
						<div class="feedback-kpi-label">Positive Feedback</div>
						<div class="feedback-kpi-value">
							${data.positive_feedback_percent || 0}%
						</div>
					</div>
					<div class="feedback-kpi alert is-clickable" data-kpi="low_rating" role="button" tabindex="0">
						<div class="feedback-kpi-label">Low Rating</div>
						<div class="feedback-kpi-value">
							${data.low_rating_count || 0}
						</div>
					</div>
					<div class="feedback-kpi warning is-clickable" data-kpi="google_review_pending" role="button" tabindex="0">
						<div class="feedback-kpi-label">Google Review Pending</div>
						<div class="feedback-kpi-value">
							${data.google_review_pending || 0}
						</div>
					</div>
				</div>

				<div class="feedback-dashboard-grid">
					<div class="feedback-panel">
						<h4>Monthly Rating Trend</h4>
						<div id="feedback-monthly-chart"></div>
					</div>
					<div class="feedback-panel">
						<h4>Service Type Breakdown</h4>
						${renderBreakdown(data.service_breakdown)}
					</div>
				</div>

				<div class="feedback-dashboard-grid">
					<div class="feedback-panel">
						<h4>Project / Site Breakdown</h4>
						${renderBreakdown(data.project_breakdown)}
					</div>
					<div class="feedback-panel">
						<h4>Quick Links</h4>
						<p>
							<a class="feedback-route-link" href="/desk/customer-feedback"
								data-route='["List","Customer Feedback"]'>
								View All Feedback
							</a>
						</p>
						<p>
							<a class="feedback-route-link" href="/desk/customer-feedback-settings"
								data-route='["Form","Customer Feedback Settings","Customer Feedback Settings"]'>
								Feedback Settings
							</a>
						</p>
						<p>
							<a href="/feedback" target="_blank" rel="noopener">
								Open Public Feedback Portal
							</a>
						</p>
					</div>
				</div>

				<div class="feedback-panel">
					<h4>Recent Feedback</h4>
					<table class="feedback-table">
						<thead>
							<tr>
								<th>ID</th>
								<th>Customer</th>
								<th>Project / Site</th>
								<th>Service</th>
								<th>Rating</th>
								<th>Feedback</th>
								<th>Follow-up</th>
							</tr>
						</thead>
						<tbody>
							${renderRecentFeedback(data.recent_feedback)}
						</tbody>
					</table>
				</div>
			</div>
		`);

		page.main.find(".feedback-refresh").on("click", loadDashboard);

		page.main
			.off("click.feedbackKpi keydown.feedbackKpi")
			.on("click.feedbackKpi", ".feedback-kpi.is-clickable", function () {
				const key = $(this).attr("data-kpi");
				open_kpi_nav(KPI_NAV[key]);
			})
			.on("keydown.feedbackKpi", ".feedback-kpi.is-clickable", function (e) {
				if (e.key !== "Enter" && e.key !== " ") {
					return;
				}
				if (e.key === " ") {
					e.preventDefault();
				}
				const key = $(this).attr("data-kpi");
				open_kpi_nav(KPI_NAV[key]);
			});

		page.main.find(".feedback-route-link").on("click", function (e) {
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

		page.main.find(".feedback-doc-link").on("click", function (e) {
			const doctype = $(this).attr("data-doctype");
			const name = $(this).attr("data-name");
			if (!doctype || !name) {
				return;
			}
			e.preventDefault();
			frappe.set_route("Form", doctype, name);
		});

		const trend = data.monthly_trend || [];

		if (trend.length && window.frappe.Chart) {
			new frappe.Chart("#feedback-monthly-chart", {
				data: {
					labels: trend.map((item) => item.month),
					datasets: [
						{
							name: "Average Rating",
							values: trend.map(
								(item) => item.average_rating
							),
						},
						{
							name: "Feedback Count",
							values: trend.map((item) => item.count),
						},
					],
				},
				type: "line",
				height: 250,
				colors: ["#1683d8", "#16a36a"],
				lineOptions: {
					regionFill: 1,
					hideDots: 0,
				},
				axisOptions: {
					xAxisMode: "tick",
					yAxisMode: "tick",
				},
			});
		} else {
			$("#feedback-monthly-chart").html(
				'<div class="text-muted">No monthly trend available.</div>'
			);
		}
	};

	const loadDashboard = () => {
		frappe.call({
			method:
				"project_custom.api.customer_feedback_dashboard.get_dashboard_data",
			freeze: true,
			freeze_message: "Loading customer feedback dashboard...",
			callback: ({ message }) => renderDashboard(message || {}),
		});
	};

	addStyles();
	loadDashboard();
};
