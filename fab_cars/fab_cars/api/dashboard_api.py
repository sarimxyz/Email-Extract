# Copyright (c) 2025, sarim and contributors
# For license information, please see license.txt

import frappe
from frappe import _


@frappe.whitelist(allow_guest=False)
def get_dashboard_data(filters=None):
	"""API endpoint to get dashboard data"""
	try:
		# Import the report function
		from fab_cars.fab_cars.report.dashboard_report.dashboard_report import execute

		# Parse filters
		if isinstance(filters, str):
			import json

			filters = json.loads(filters)

		# Execute the report
		columns, data, message, chart, number_cards, total_count = execute(filters or {})

		return {
			"columns": columns,
			"data": data,
			"number_cards": number_cards,
			"total_count": total_count,
			"has_data": (total_count > 0) if total_count is not None else (len(data) > 0 if data else False),
		}

	except Exception as e:
		frappe.log_error(f"Error in dashboard API: {e!s}")
		return {"error": str(e), "columns": [], "data": [], "number_cards": [], "has_data": False}
