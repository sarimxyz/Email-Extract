# Copyright (c) 2026, fab_cars and contributors
# For license information, please see license.txt

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_field


def execute():
	"""Add `initial_sync_completed_at` on Email Account (Fab Cars ingestion cutoff)."""
	create_custom_field(
		"Email Account",
		{
			"fieldname": "initial_sync_completed_at",
			"label": "Initial Sync Completed At",
			"fieldtype": "Datetime",
			"insert_after": "last_received_at",
			"read_only": 1,
			"description": (
				"Fab Cars: set automatically before the first inbound pull. "
				"Inbound emails with received time at or before this (UTC) are not ingested into FC Raw Email Log."
			),
		},
	)
