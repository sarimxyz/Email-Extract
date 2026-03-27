# Copyright (c) 2026, fab_cars and contributors
# For license information, please see license.txt

import frappe
from frappe.email.doctype.email_account.email_account import EmailAccount as FrappeEmailAccount


class EmailAccount(FrappeEmailAccount):
	"""Extends Frappe to record a one-time ingestion cutoff before the first inbound pull."""

	def receive(self):
		self._fab_cars_set_initial_sync_cutoff_once_before_pull()
		super().receive()

	def _fab_cars_set_initial_sync_cutoff_once_before_pull(self):
		if not getattr(self, "enable_incoming", None):
			return
		if not frappe.db.has_column("Email Account", "initial_sync_completed_at"):
			return
		if frappe.db.get_value("Email Account", self.name, "initial_sync_completed_at"):
			return
		frappe.db.set_value(
			"Email Account",
			self.name,
			"initial_sync_completed_at",
			frappe.utils.now_datetime(),
			update_modified=False,
		)
		frappe.db.commit()
