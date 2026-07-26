import frappe


def redirect_to_nave_home(login_manager):
    user = login_manager.user

    if user and user != "Guest":
        frappe.cache.hset(
            "redirect_after_login",
            user,
            "/desk/nave-home",
        )
