app_name = "project_custom"
app_title = "Project Custom"
app_publisher = "Nave Industries"
app_description = "Project Journal Entry Connection"
app_email = "industriesnave@gmail.com"

after_install = "project_custom.install.after_install"

override_doctype_dashboards = {
    "Project": "project_custom.dashboard.get_project_dashboard"
}
app_license = "mit"
app_include_js = "/assets/project_custom/js/role_dashboard_redirect.js"
after_migrate = "project_custom.install.after_migrate"
# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "project_custom",
# 		"logo": "/assets/project_custom/logo.png",
# 		"title": "Project Custom",
# 		"route": "/project_custom",
# 		"has_permission": "project_custom.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/project_custom/css/project_custom.css"
# app_include_js = "/assets/project_custom/js/project_custom.js"

# include js, css files in header of web template
# web_include_css = "/assets/project_custom/css/project_custom.css"
# web_include_js = "/assets/project_custom/js/project_custom.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "project_custom/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "project_custom/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# automatically load and sync documents of this doctype from downstream apps
# importable_doctypes = [doctype_1]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "project_custom.utils.jinja_methods",
# 	"filters": "project_custom.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "project_custom.install.before_install"
# after_install = "project_custom.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "project_custom.uninstall.before_uninstall"
# after_uninstall = "project_custom.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "project_custom.utils.before_app_install"
# after_app_install = "project_custom.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "project_custom.utils.before_app_uninstall"
# after_app_uninstall = "project_custom.utils.after_app_uninstall"

# Build
# ------------------
# To hook into the build process

# after_build = "project_custom.build.after_build"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "project_custom.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# Document Events
# ---------------
# Hook on document methods and events

# doc_events = {
# 	"*": {
# 		"on_update": "method",
# 		"on_cancel": "method",
# 		"on_trash": "method"
# 	}
# }

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"project_custom.tasks.all"
# 	],
# 	"daily": [
# 		"project_custom.tasks.daily"
# 	],
# 	"hourly": [
# 		"project_custom.tasks.hourly"
# 	],
# 	"weekly": [
# 		"project_custom.tasks.weekly"
# 	],
# 	"monthly": [
# 		"project_custom.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "project_custom.install.before_tests"

# Extend DocType Class
# ------------------------------
#
# Specify custom mixins to extend the standard doctype controller.
# extend_doctype_class = {
# 	"Task": "project_custom.custom.task.CustomTaskMixin"
# }

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "project_custom.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "project_custom.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["project_custom.utils.before_request"]
# after_request = ["project_custom.utils.after_request"]

# Job Events
# ----------
# before_job = ["project_custom.utils.before_job"]
# after_job = ["project_custom.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"project_custom.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

# Translation
# ------------
# List of apps whose translatable strings should be excluded from this app's translations.
# ignore_translatable_strings_from = []



doc_events = {
    "Journal Entry": {
        "before_update_after_submit": "project_custom.project_cost.store_previous_project",
        "on_submit": "project_custom.project_cost.recalculate_for_journal_entry",
        "on_update_after_submit": "project_custom.project_cost.recalculate_for_journal_entry",
        "on_cancel": "project_custom.project_cost.recalculate_for_journal_entry",
    }
}
