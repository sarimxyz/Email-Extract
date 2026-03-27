# Copyright (c) 2025, sarim and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class FCCabSettings(Document):
	def validate(self):
		prompt = self.prompt or ""
		if "{email_text}" not in prompt:
			frappe.throw(
				"FC Cab Settings.prompt must include the placeholder `{email_text}`.",
				title="Invalid Cab Settings",
			)
