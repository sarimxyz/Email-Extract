import frappe


def execute(filters=None):
	filters = filters or {}

	from_date = filters.get("from_date")
	to_date = filters.get("to_date")
	trip_status = filters.get("trip_request_status")
	start = int(filters.get("start") or 0)
	page_length = int(filters.get("page_length") or 20)
	if page_length < 1:
		page_length = 20
	if start < 0:
		start = 0

	# Number cards (DB-side aggregation; no Python full scans).
	number_cards = get_number_cards(from_date, to_date, trip_status=trip_status)

	columns = [
		{"label": "Email Sender", "fieldname": "sender", "fieldtype": "Data", "width": 200},
		{"label": "Email Subject", "fieldname": "subject", "fieldtype": "Data", "width": 250},
		{"label": "Received Date", "fieldname": "received_date", "fieldtype": "Datetime", "width": 160},
		{
			"label": "Extracted Email",
			"fieldname": "extracted_email",
			"fieldtype": "Link",
			"options": "FC Raw Email Log",
			"width": 200,
		},
		{
			"label": "Trip Request",
			"fieldname": "trip_request",
			"fieldtype": "Link",
			"options": "FC Trip Request",
			"width": 200,
		},
		{"label": "Trip Status", "fieldname": "trip_request_status", "fieldtype": "Data", "width": 120},
		{"label": "City", "fieldname": "city", "fieldtype": "Data", "width": 120},
		{"label": "Vehicle Type", "fieldname": "vehicle_type", "fieldtype": "Data", "width": 120},
		{"label": "Remarks", "fieldname": "remarks", "fieldtype": "Small Text", "width": 200},
	]

	data = []

	# DB-side filtering + pagination.
	where_clauses = []
	params: dict = {}

	if trip_status:
		where_clauses.append("r.status = %(trip_status)s")
		params["trip_status"] = trip_status

	if from_date and to_date:
		# Date inputs are `YYYY-MM-DD`; expand to full-day range.
		params["from_dt"] = f"{from_date} 00:00:00"
		params["to_dt"] = f"{to_date} 23:59:59"
		where_clauses.append("r.received_at BETWEEN %(from_dt)s AND %(to_dt)s")

	where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"

	# Total count for pagination controls.
	total_count = frappe.db.sql(
		f"""
		SELECT COUNT(*) as cnt
		FROM `tabFC Raw Email Log` r
		WHERE {where_sql}
		""",
		params,
		as_dict=True,
	)
	total_count = int(total_count[0].get("cnt") or 0) if total_count else 0

	rows = frappe.db.sql(
		f"""
		SELECT
			r.name,
			r.sender,
			r.subject,
			r.received_at,
			r.status as trip_request_status,
			t.name as trip_request,
			t.city as city,
			t.required_vehicle_type as vehicle_type,
			t.remarks as remarks
		FROM `tabFC Raw Email Log` r
		LEFT JOIN `tabFC Trip Request` t
			ON t.mail_link = r.name
		WHERE {where_sql}
		ORDER BY r.received_at desc, r.name desc
		LIMIT %(limit)s OFFSET %(offset)s
		""",
		{**params, "limit": page_length, "offset": start},
		as_dict=True,
	)

	for row in rows or []:
		data.append(
			{
				"sender": row.sender or "",
				"subject": row.subject or "",
				"received_date": row.received_at,
				"extracted_email": row.name,
				"trip_request": row.trip_request or "",
				"trip_request_status": row.trip_request_status or "",
				"city": row.city or "",
				"vehicle_type": row.vehicle_type or "",
				"remarks": row.remarks or "",
			}
		)

	return columns, data, None, None, number_cards, total_count


def get_number_cards(from_date=None, to_date=None, trip_status=None):
	"""Aggregate counts for dashboard number cards via DB-side filters."""
	where_clauses = []
	params: dict = {}

	if trip_status:
		where_clauses.append("r.status = %(trip_status)s")
		params["trip_status"] = trip_status

	if from_date and to_date:
		params["from_dt"] = f"{from_date} 00:00:00"
		params["to_dt"] = f"{to_date} 23:59:59"
		where_clauses.append("r.received_at BETWEEN %(from_dt)s AND %(to_dt)s")

	where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"

	total_emails_received = frappe.db.sql(
		f"SELECT COUNT(*) as cnt FROM `tabFC Raw Email Log` r WHERE {where_sql}",
		params,
		as_dict=True,
	)
	total_emails_received = int(total_emails_received[0].get("cnt") or 0) if total_emails_received else 0

	# Respect the same status filter, but only consider successful/failed as "extracted".
	total_emails_extracted = frappe.db.sql(
		f"""
		SELECT COUNT(*) as cnt
		FROM `tabFC Raw Email Log` r
		WHERE {where_sql}
			AND r.status IN ('Successful', 'Failed')
		""",
		params,
		as_dict=True,
	)
	total_emails_extracted = int(total_emails_extracted[0].get("cnt") or 0) if total_emails_extracted else 0

	total_trip_requests = frappe.db.sql(
		f"""
		SELECT COUNT(*) as cnt
		FROM `tabFC Trip Request` t
		INNER JOIN `tabFC Raw Email Log` r
			ON t.mail_link = r.name
		WHERE {where_sql}
		""",
		params,
		as_dict=True,
	)
	total_trip_requests = int(total_trip_requests[0].get("cnt") or 0) if total_trip_requests else 0

	return [
		{"value": total_emails_received, "label": "Total Emails Received", "datatype": "Int"},
		{"value": total_emails_extracted, "label": "Total Emails Extracted", "datatype": "Int"},
		{"value": total_trip_requests, "label": "Total Trip Requests", "datatype": "Int"},
	]
