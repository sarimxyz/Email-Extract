import frappe

def execute(filters=None):
    filters = filters or {}

    from_date = filters.get("from_date")
    to_date = filters.get("to_date")
    trip_status = filters.get("trip_request_status")

    columns = [
        {"label": "Email Sender", "fieldname": "sender", "fieldtype": "Data", "width": 200},
        {"label": "Email Subject", "fieldname": "subject", "fieldtype": "Data", "width": 250},
        {"label": "Received Date", "fieldname": "received_date", "fieldtype": "Datetime", "width": 160},
        {"label": "Extracted Email", "fieldname": "extracted_email", "fieldtype": "Link", "options": "FC_BTW_Extracted_Emails", "width": 200},
        {"label": "Trip Request", "fieldname": "trip_request", "fieldtype": "Link", "options": "FC_BTW_Trip_Requests", "width": 200},
        {"label": "Trip Status", "fieldname": "trip_request_status", "fieldtype": "Data", "width": 120},
        {"label": "City", "fieldname": "city", "fieldtype": "Data", "width": 120},
        {"label": "Vehicle Type", "fieldname": "vehicle_type", "fieldtype": "Data", "width": 120},
        {"label": "Remarks", "fieldname": "remarks", "fieldtype": "Small Text", "width": 200},
    ]

    data = []

    filters_dict = {}
    if from_date and to_date:
        filters_dict["received_date"] = ["between", [from_date, to_date]]
    if trip_status:
        filters_dict["trip_request_status"] = trip_status

    # Fetch extracted emails (filtered by date and/or status)
    extracted_emails = frappe.get_all(
        "FC_BTW_Extracted_Emails",
        filters=filters_dict,
        fields=["name", "sender", "subject", "received_date", "trip_request_status", "communication_link"]
    )

    for email in extracted_emails:
        # Match with trip request
        trip = frappe.db.get_value(
            "FC_BTW_Trip_Requests",
            {"mail_link": email.communication_link},
            ["name", "city", "vehicle_type", "remarks"],
            as_dict=True
        )

        data.append({
            "sender": email.sender,
            "subject": email.subject,
            "received_date": email.received_date,
            "extracted_email": email.name,
            "trip_request": trip.name if trip else "",
            "trip_request_status": email.trip_request_status,
            "city": trip.city if trip else "",
            "vehicle_type": trip.vehicle_type if trip else "",
            "remarks": trip.remarks if trip else ""
        })

    return columns, data
