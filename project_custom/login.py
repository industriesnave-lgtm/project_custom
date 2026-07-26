import frappe


def redirect_to_nave_home(login_manager):
    if login_manager.user and login_manager.user != "Guest":
        frappe.local.flags.home_page = "/desk/nave-home"
