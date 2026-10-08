frappe.pages["project-financial-dashboard"].on_page_load = function (wrapper) {
    frappe.require(
        "/assets/project_custom/css/project_financial_dashboard.css"
    );
    const page = frappe.ui.make_app_page({
        parent: wrapper,
        title: "Project Financial Dashboard",
        single_column: true,
    });

    page.add_inner_button("← Nave Home", () => {
        frappe.set_route("nave-home");
    });

    const escape = (value) =>
        frappe.utils.escape_html(String(value ?? ""));

    const money = (value) => format_currency(value || 0);

    const $root = $(`
        <div class="nfd-dashboard">
            <div class="nfd-header">
                <div>
                    <h2>Project Financial Overview</h2>
                    <p>Monthly Billing & Expense Monitoring</p>
                </div>
                <span class="nfd-header-tag">Financial Dashboard</span>
            </div>

            <div class="nfd-filter-bar">
                <div class="nfd-month"></div>
                <div class="nfd-project"></div>
                <button class="btn btn-primary nfd-refresh">Refresh</button>
            </div>

            <div class="nfd-summary"></div>

            <div class="nfd-panel">
                <h4>Monthly Billing Breakdown</h4>
                <div class="nfd-chart"></div>
            </div>

            <div class="nfd-panel">
                <h4>Project-wise Financial Details</h4>
                <div class="nfd-billing-table"></div>
                <button class="btn btn-default nfd-open-billing">
                    View Full Billing Report
                </button>
            </div>

            <div class="nfd-panel">
                <h4>Unbilled Expense Monitoring</h4>
                <p>Current alert-cycle data</p>
                <div class="nfd-unbilled-summary"></div>
                <div class="nfd-unbilled-table"></div>
                <button class="btn btn-default nfd-open-unbilled">
                    View Unbilled Expense Report
                </button>
            </div>
        </div>
    `);
    page.main.empty().append($root);

    const month_control = frappe.ui.form.make_control({
        parent: $root.find(".nfd-month")[0],
        df: {
            fieldtype: "Date",
            fieldname: "month_year",
            label: "Month-Year",
        },
        render_input: true,
    });

    month_control.set_value(frappe.datetime.get_today());

    const project_control = frappe.ui.form.make_control({
        parent: $root.find(".nfd-project")[0],
        df: {
            fieldtype: "Link",
            fieldname: "project",
            options: "Project",
            label: "Project",
        },
        render_input: true,
    });

    const render_table = (columns, rows) => {
        if (!rows.length) {
            return '<div class="text-muted" style="padding:16px">No records found.</div>';
        }

        const headers = columns.map(col =>
            `<th>${escape(col.label)}</th>`
        ).join("");

        const body = rows.map(row => {
            const cells = columns.map(col => {
                const value = row[col.fieldname];

                const display = col.fieldtype === "Currency"
                    ? escape(money(value))
                    : col.fieldtype === "Check"
                        ? (Number(value) ? "Yes" : "No")
                        : escape(value);

                return `<td>${display}</td>`;
            }).join("");

            return `<tr>${cells}</tr>`;
        }).join("");

        return `
            <div style="overflow-x:auto">
                <table class="table table-bordered table-striped">
                    <thead><tr>${headers}</tr></thead>
                    <tbody>${body}</tbody>
                </table>
            </div>
        `;
    };

    const load_dashboard = async () => {
        const $button = $root.find(".nfd-refresh");
        $button.prop("disabled", true).text("Loading...");

        try {
            const response = await frappe.call({
                method: "project_custom.project_financial_dashboard.get_dashboard_data",
                args: {
                    month_year: month_control.get_value(),
                    project: project_control.get_value(),
                },
            });

            const result = response.message || {};
            const billing = result.billing || {};
            const unbilled = result.unbilled || {};
            const summary = billing.summary || {};

            const kpi_card = (label, value, icon, color) => `
                <div class="nfd-kpi-card">
                    <div class="nfd-kpi-icon" style="background:${color}15;color:${color}">
                        ${icon}
                    </div>
                    <div class="nfd-kpi-label">${escape(label)}</div>
                    <div class="nfd-kpi-value">${escape(value)}</div>
                </div>
            `;

            $root.find(".nfd-summary").html(`
                <div class="nfd-kpi-grid">
                    ${kpi_card("Service Billing", money(summary.service_billing), "⚙", "#2563eb")}
                    ${kpi_card("Supply Billing", money(summary.supply_billing), "📦", "#059669")}
                    ${kpi_card("Total Billing", money(summary.total_billing), "₹", "#7c3aed")}
                    ${kpi_card("Unbilled Alerts", (unbilled.data || []).length, "⚠", "#d97706")}
                </div>
            `);

            const service = Number(summary.service_billing || 0);
            const supply = Number(summary.supply_billing || 0);
            const max_billing = Math.max(service, supply, 1);

            const chart_bar = (label, amount, color) => {
                const width = Math.max(
                    0,
                    Math.min(100, (amount / max_billing) * 100)
                );

                return `
                    <div class="nfd-chart-row">
                        <div class="nfd-chart-label">
                            <span>${escape(label)}</span>
                            <strong>${escape(money(amount))}</strong>
                        </div>
                        <div class="nfd-chart-track">
                            <div class="nfd-chart-fill"
                                 style="width:${width}%;background:${color}">
                            </div>
                        </div>
                    </div>
                `;
            };

            $root.find(".nfd-chart").html(`
                ${chart_bar("Service Billing", service, "#2563eb")}
                ${chart_bar("Supply Billing", supply, "#059669")}
            `);

            $root.find(".nfd-billing-table").html(
                render_table(billing.columns || [], billing.data || [])
            );

            const alerts = unbilled.data || [];
            const total_unbilled = alerts.reduce(
                (sum, row) =>
                    sum + Number(row.current_unbilled_amount || 0),
                0
            );

            $root.find(".nfd-unbilled-summary").text(
                `Alerts: ${alerts.length} | Current Unbilled: ${money(total_unbilled)}`
            );

            $root.find(".nfd-unbilled-table").html(
                alerts.length
                    ? render_table(unbilled.columns || [], alerts)
                    : `<div class="nfd-empty-state">
                           <div class="nfd-empty-icon">✓</div>
                           <strong>No Active Unbilled Alerts</strong>
                           <p>No projects currently appear in the unbilled alert report.</p>
                       </div>`
            );

        } catch (error) {
            console.error("Financial Dashboard Error:", error);
            frappe.msgprint({
                title: __("Dashboard Error"),
                message: __("Unable to load dashboard data. Check permissions and server logs."),
                indicator: "red",
            });
        } finally {
            $button.prop("disabled", false).text("Refresh");
        }
    };

    $root.find(".nfd-refresh").on("click", load_dashboard);

    $root.find(".nfd-open-billing").on("click", () => {
        frappe.route_options = {
            month_year: month_control.get_value(),
            project: project_control.get_value() || undefined,
        };
        frappe.set_route("query-report", "Monthly Project Billing");
    });

    $root.find(".nfd-open-unbilled").on("click", () => {
        frappe.route_options = {
            project: project_control.get_value() || undefined,
        };
        frappe.set_route(
            "query-report",
            "NAVE Project Unbilled Expense Alert"
        );
    });

    load_dashboard();
};
