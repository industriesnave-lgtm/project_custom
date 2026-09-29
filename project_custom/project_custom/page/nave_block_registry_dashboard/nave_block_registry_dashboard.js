frappe.pages["nave-block-registry-dashboard"].on_page_load = function (wrapper) {
        const page = frappe.ui.make_app_page({
                parent: wrapper,
                title: "NAVE Block Registry Dashboard",
                single_column: true,
        });

        page.add_inner_button("← Nave Home", () => {
                frappe.set_route("nave-home");
        });

        page.add_inner_button("View All", () => {
                frappe.route_options = {};
                frappe.set_route("List", "NAVE Block Registry");
        });

        page.set_primary_action("+ Add Block", () => {
                frappe.new_doc("NAVE Block Registry");
        });

        const escape = (value) =>
                frappe.utils.escape_html(String(value || ""));

        const open_list = (filters = {}) => {
                frappe.route_options = filters;
                frappe.set_route("List", "NAVE Block Registry");
        };

        const add_styles = () => {
                if (document.getElementById("nave-block-dashboard-style")) {
                        return;
                }

                $(`<style id="nave-block-dashboard-style">
                        .nave-block-dashboard {
                                padding: 22px;
                                min-height: calc(100vh - 90px);
                                background: #f4f7fb;
                                border-radius: 16px;
                        }

                        .nave-block-header {
                                display: flex;
                                align-items: center;
                                justify-content: space-between;
                                gap: 20px;
                                padding: 22px 24px;
                                margin-bottom: 20px;
                                background: #fff;
                                border-radius: 14px;
                                box-shadow: 0 5px 18px rgba(18, 59, 104, 0.08);
                        }

                        .nave-block-brand {
                                display: flex;
                                align-items: center;
                                gap: 18px;
                        }

                        .nave-block-logo {
                                width: 145px;
                                max-height: 62px;
                                object-fit: contain;
                        }

                        .nave-block-header h2 {
                                margin: 0;
                                color: #123b68;
                                font-weight: 800;
                        }

                        .nave-block-header p {
                                margin: 5px 0 0;
                                color: #64748b;
                        }

                        .nave-block-shield {
                                display: flex;
                                align-items: center;
                                justify-content: center;
                                width: 64px;
                                height: 64px;
                                border-radius: 16px;
                                background: #fef2f2;
                                font-size: 34px;
                        }

                        .nave-block-kpis {
                                display: grid;
                                grid-template-columns:
                                        repeat(auto-fit, minmax(170px, 1fr));
                                gap: 15px;
                                margin-bottom: 20px;
                        }

                        .nave-block-kpi {
                                padding: 19px;
                                background: #fff;
                                border-top: 4px solid #1683d8;
                                border-radius: 13px;
                                box-shadow: 0 5px 18px rgba(18, 59, 104, 0.07);
                                cursor: pointer;
                                transition: transform 0.12s ease,
                                        box-shadow 0.12s ease;
                        }

                        .nave-block-kpi:hover {
                                transform: translateY(-2px);
                                box-shadow: 0 8px 20px rgba(18, 59, 104, 0.12);
                        }

                        .nave-block-kpi.active {
                                border-top-color: #dc2626;
                        }

                        .nave-block-kpi.person {
                                border-top-color: #7c3aed;
                        }

                        .nave-block-kpi.supplier {
                                border-top-color: #f59e0b;
                        }

                        .nave-block-kpi.customer {
                                border-top-color: #1683d8;
                        }

                        .nave-block-kpi.revoked {
                                border-top-color: #64748b;
                        }

                        .nave-block-kpi-label {
                                color: #64748b;
                                font-size: 13px;
                                font-weight: 650;
                        }

                        .nave-block-kpi-value {
                                margin-top: 8px;
                                color: #123b68;
                                font-size: 30px;
                                font-weight: 800;
                        }

                        .nave-block-panel {
                                padding: 21px;
                                background: #fff;
                                border-radius: 14px;
                                box-shadow: 0 5px 18px rgba(18, 59, 104, 0.07);
                        }

                        .nave-block-panel-header {
                                display: flex;
                                align-items: center;
                                justify-content: space-between;
                                gap: 15px;
                                margin-bottom: 15px;
                        }

                        .nave-block-panel h4 {
                                margin: 0;
                                color: #123b68;
                                font-weight: 750;
                        }

                        .nave-block-link {
                                color: #1683d8;
                                font-weight: 700;
                                cursor: pointer;
                        }

                        .nave-block-table {
                                width: 100%;
                                border-collapse: collapse;
                        }

                        .nave-block-table th,
                        .nave-block-table td {
                                padding: 11px 9px;
                                border-bottom: 1px solid #e8edf4;
                                text-align: left;
                                vertical-align: middle;
                        }

                        .nave-block-table th {
                                color: #64748b;
                                font-size: 12px;
                                text-transform: uppercase;
                        }

                        .nave-block-row {
                                cursor: pointer;
                        }

                        .nave-block-row:hover {
                                background: #f8fafc;
                        }

                        .nave-block-status {
                                display: inline-block;
                                padding: 4px 9px;
                                border-radius: 20px;
                                font-size: 12px;
                                font-weight: 700;
                        }

                        .nave-block-status.Active {
                                background: #fef2f2;
                                color: #dc2626;
                        }

                        .nave-block-status.Revoked {
                                background: #f1f5f9;
                                color: #64748b;
                        }

                        .nave-block-empty {
                                padding: 35px;
                                color: #64748b;
                                text-align: center;
                        }

                        @media (max-width: 700px) {
                                .nave-block-dashboard {
                                        padding: 12px;
                                }

                                .nave-block-header {
                                        align-items: flex-start;
                                        flex-direction: column;
                                }

                                .nave-block-logo {
                                        width: 120px;
                                }

                                .nave-block-panel {
                                        overflow-x: auto;
                                }
                        }
                </style>`).appendTo("head");
        };

        const render_recent = (items) => {
                if (!items || !items.length) {
                        return `
                                <tr>
                                        <td colspan="6" class="nave-block-empty">
                                                No Block Registry records found.
                                        </td>
                                </tr>
                        `;
                }

                return items.map((item) => `
                        <tr class="nave-block-row"
                                data-name="${escape(item.name)}">
                                <td><strong>${escape(item.party_name)}</strong></td>
                                <td>${escape(item.party_type)}</td>
                                <td>
                                        <span class="nave-block-status ${escape(item.status)}">
                                                ${escape(item.status)}
                                        </span>
                                </td>
                                <td>${escape(item.reason_category || "-")}</td>
                                <td>${escape(item.block_date || "-")}</td>
                                <td>${escape(item.name)}</td>
                        </tr>
                `).join("");
        };

        const render = (data) => {
                add_styles();

                page.main.html(`
                        <div class="nave-block-dashboard">
                                <div class="nave-block-header">
                                        <div class="nave-block-brand">
                                                <img class="nave-block-logo"
                                                        src="/assets/project_custom/images/nave-logo.png"
                                                        alt="Nave Industries">
                                                <div>
                                                        <h2>NAVE Block Registry</h2>
                                                        <p>
                                                                Central control for blocked persons,
                                                                suppliers and customers
                                                        </p>
                                                </div>
                                        </div>
                                        <div class="nave-block-shield">🚫</div>
                                </div>

                                <div class="nave-block-kpis">
                                        <div class="nave-block-kpi active"
                                                data-filter="active">
                                                <div class="nave-block-kpi-label">
                                                        Active Blocks
                                                </div>
                                                <div class="nave-block-kpi-value">
                                                        ${data.active || 0}
                                                </div>
                                        </div>

                                        <div class="nave-block-kpi person"
                                                data-filter="person">
                                                <div class="nave-block-kpi-label">
                                                        Blocked Persons
                                                </div>
                                                <div class="nave-block-kpi-value">
                                                        ${data.persons || 0}
                                                </div>
                                        </div>

                                        <div class="nave-block-kpi supplier"
                                                data-filter="supplier">
                                                <div class="nave-block-kpi-label">
                                                        Blocked Suppliers
                                                </div>
                                                <div class="nave-block-kpi-value">
                                                        ${data.suppliers || 0}
                                                </div>
                                        </div>

                                        <div class="nave-block-kpi customer"
                                                data-filter="customer">
                                                <div class="nave-block-kpi-label">
                                                        Blocked Customers
                                                </div>
                                                <div class="nave-block-kpi-value">
                                                        ${data.customers || 0}
                                                </div>
                                        </div>

                                        <div class="nave-block-kpi revoked"
                                                data-filter="revoked">
                                                <div class="nave-block-kpi-label">
                                                        Revoked Blocks
                                                </div>
                                                <div class="nave-block-kpi-value">
                                                        ${data.revoked || 0}
                                                </div>
                                        </div>
                                </div>

                                <div class="nave-block-panel">
                                        <div class="nave-block-panel-header">
                                                <h4>Recent Block Registry Records</h4>
                                                <span class="nave-block-link"
                                                        data-action="view-all">
                                                        View All →
                                                </span>
                                        </div>

                                        <table class="nave-block-table">
                                                <thead>
                                                        <tr>
                                                                <th>Name</th>
                                                                <th>Party Type</th>
                                                                <th>Status</th>
                                                                <th>Reason</th>
                                                                <th>Block Date</th>
                                                                <th>Reference</th>
                                                        </tr>
                                                </thead>
                                                <tbody>
                                                        ${render_recent(data.recent)}
                                                </tbody>
                                        </table>
                                </div>
                        </div>
                `);

                page.main.find(".nave-block-kpi").on("click", function () {
                        const filter = $(this).data("filter");

                        if (filter === "active") {
                                open_list({ status: "Active" });
                        } else if (filter === "person") {
                                open_list({
                                        status: "Active",
                                        party_type: "Person",
                                });
                        } else if (filter === "supplier") {
                                open_list({
                                        status: "Active",
                                        party_type: "Supplier / Vendor",
                                });
                        } else if (filter === "customer") {
                                open_list({
                                        status: "Active",
                                        party_type: "Customer",
                                });
                        } else if (filter === "revoked") {
                                open_list({ status: "Revoked" });
                        }
                });

                page.main.find('[data-action="view-all"]').on("click", () => {
                        open_list({});
                });

                page.main.find(".nave-block-row").on("click", function () {
                        const name = $(this).data("name");

                        if (name) {
                                frappe.set_route(
                                        "Form",
                                        "NAVE Block Registry",
                                        name,
                                );
                        }
                });
        };

        const load_dashboard = () => {
                page.main.html(`
                        <div class="text-muted" style="padding:30px;">
                                Loading Block Registry...
                        </div>
                `);

                frappe.call({
                        method:
                                "project_custom.block_registry_dashboard.get_dashboard_data",
                        callback: (response) => {
                                render(response.message || {});
                        },
                        error: () => {
                                page.main.html(`
                                        <div class="nave-block-empty">
                                                Unable to load Block Registry Dashboard.
                                        </div>
                                `);
                        },
                });
        };

        load_dashboard();
};
