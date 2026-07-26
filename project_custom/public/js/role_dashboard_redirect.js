frappe.after_ajax(() => {
	const route = frappe.get_route();
	const is_desk_home = route.length === 0 || !route[0];

	if (
		frappe.session.user !== "Guest" &&
		is_desk_home
	) {
		frappe.set_route("nave-home");
	}
});
