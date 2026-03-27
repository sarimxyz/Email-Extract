import frappe

from fab_cars.fab_cars.llm.cab_settings_prompt import get_default_fc_cab_settings_prompt


def execute():
	"""
	Backfill `FC Cab Settings.prompt` if older installs left it without the
	required `{email_text}` placeholder.
	"""
	cab_settings = frappe.get_single("FC Cab Settings")
	current_prompt = cab_settings.prompt or ""

	if "{email_text}" not in current_prompt:
		cab_settings.prompt = get_default_fc_cab_settings_prompt()
		cab_settings.save(ignore_permissions=True)
		frappe.db.commit()
