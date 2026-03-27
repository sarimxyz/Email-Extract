# Copyright (c) 2026, fab_cars and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class FCRawEmailLog(Document):
	def autoname(self):
		"""
		Deterministic naming for idempotency.

		We prefer using `email_hash` (sha256 hex) as the document name because it is stable
		and safe as a primary key. If `email_hash` isn't present, fall back to timestamp-based naming.
		"""

		email_hash = (self.email_hash or "").strip()
		if email_hash:
			self.name = f"FCR_{email_hash}"
			return

		# Fallback: still deterministic-ish, but will not be unique across collisions.
		self.name = f"FCR_{frappe.utils.now_datetime().strftime('%Y%m%d_%H%M%S_%f')}"
