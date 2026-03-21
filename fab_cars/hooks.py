app_name = "fab_cars"
app_title = "Fab Cars"
app_publisher = "sarim"
app_description = "App to manage car bookings"
app_email = "sarim.khan@clapgrow.com"
app_license = "mit"

# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "fab_cars",
# 		"logo": "/assets/fab_cars/logo.png",
# 		"title": "Sarim App",
# 		"route": "/fab_cars",
# 		"has_permission": "fab_cars.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/fab_cars/css/fab_cars.css"
# app_include_js = "/assets/fab_cars/js/fab_cars.js"

# include js, css files in header of web template
# web_include_css = "/assets/fab_cars/css/fab_cars.css"
# web_include_js = "/assets/fab_cars/js/fab_cars.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "fab_cars/public/scss/website"

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
# app_include_icons = "fab_cars/public/icons.svg"

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

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "fab_cars.utils.jinja_methods",
# 	"filters": "fab_cars.utils.jinja_filters"
# }

# Installation
# ------------

after_install = "fab_cars.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "fab_cars.uninstall.before_uninstall"
# after_uninstall = "fab_cars.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "fab_cars.utils.before_app_install"
# after_app_install = "fab_cars.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "fab_cars.utils.before_app_uninstall"
# after_app_uninstall = "fab_cars.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "fab_cars.notifications.get_notification_config"

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

# DocType Class
# ---------------
# Override standard doctype classes

# override_doctype_class = {
# 	"ToDo": "custom_app.overrides.CustomToDo"
# }

# Document Events
# ---------------
# Hook on document methods and events

doc_events = {
	"Communication": {
		"after_insert": "fab_cars.fab_cars.email_ingestion_service.sync_tasks.enqueue_ingestion_from_communication"
	},
	# # Keep the auto-generated workspace sidebar in sync when Page titles change.
	# "Page": {
	#     "on_update": "fab_cars.hooks_handlers.clear_workspace_sidebar_cache_on_page_update"
	# },
}

make_email_body_message = ["fab_cars.hooks_handlers.ensure_references_header_for_threading"]

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"fab_cars.tasks.all"
# 	],
# 	"daily": [
# 		"fab_cars.tasks.daily"
# 	],
# 	"hourly": [
# 		"fab_cars.tasks.hourly"
# 	],
# 	"weekly": [
# 		"fab_cars.tasks.weekly"
# 	],
# 	"monthly": [
# 		"fab_cars.tasks.monthly"
# 	],
# }

#
# Legacy cron polling is disabled.
# Real-time ingestion is handled by `email_ingestion_service` + the `ingest_email` API.
#
# We still use scheduler events for:
# 1) Faster email pulls (so Communication arrives quickly)
# 2) Retrying failed extractions
scheduler_events = {
	"cron": {
		"*/5 * * * *": [
			"fab_cars.fab_cars.email_ingestion_service.sync_tasks.fast_pull_emails",
			"fab_cars.fab_cars.email_ingestion_service.sync_tasks.retry_failed_ingestions",
		]
	}
}


# Testing
# -------

# before_tests = "fab_cars.install.before_tests"

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "fab_cars.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "fab_cars.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["fab_cars.utils.before_request"]
# after_request = ["fab_cars.utils.after_request"]

# Job Events
# ----------
# before_job = ["fab_cars.utils.before_job"]
# after_job = ["fab_cars.utils.after_job"]

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
# 	"fab_cars.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }
