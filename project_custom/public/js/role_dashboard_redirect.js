(() => {
	const STANDALONE_DASHBOARD_RE = /\/(desk|app)\/nave-task-dashboard\/?$/;

	const redirectStandaloneDashboard = () => {
		if (frappe.session.user === "Guest") {
			return;
		}
		const path = window.location.pathname.replace(/\/+$/, "") || "/";
		if (STANDALONE_DASHBOARD_RE.test(path)) {
			// Prefer consolidated NAVE Tasks entry; keep bookmarks working.
			window.location.replace("/desk/nave-tasks");
		}
	};

	const redirectToNaveHome = () => {
		const path = window.location.pathname.replace(/\/+$/, "");

		if (
			frappe.session.user !== "Guest" &&
			(path === "/desk" || path === "/app")
		) {
			window.location.replace("/desk/nave-home");
		}
	};

	const run = () => {
		redirectStandaloneDashboard();
		redirectToNaveHome();
	};

	if (document.readyState === "loading") {
		document.addEventListener("DOMContentLoaded", run);
	} else {
		run();
	}

	// SPA route changes (Awesome Bar / set_route) without full reload.
	if (window.frappe && frappe.router && typeof frappe.router.on === "function") {
		frappe.router.on("change", redirectStandaloneDashboard);
	}
	document.addEventListener("page-change", redirectStandaloneDashboard);
})();
