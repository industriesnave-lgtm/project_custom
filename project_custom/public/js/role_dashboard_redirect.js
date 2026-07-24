frappe.after_ajax(() => {
	const sales_roles = ["Sales User", "Sales Manager"];
	const user_roles = frappe.user_roles || [];

	const is_sales_user = sales_roles.some((role) =>
		user_roles.includes(role)
	);

	const route = frappe.get_route();
	const is_desk_home = route.length === 0;

	if (
		is_sales_user &&
		frappe.session.user !== "Administrator" &&
		is_desk_home
	) {
		frappe.set_route("nave-sales-dashboard");
	}
});
