import frappe

def execute(filters=None):
    filters = filters or {}

    from_date = filters.get("from_date")
    to_date = filters.get("to_date")
    trip_status = filters.get("trip_request_status")
    
    # Calculate number cards
    number_cards = get_number_cards(from_date, to_date)

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
    if trip_status:
        filters_dict["trip_request_status"] = trip_status

    # Fetch extracted emails (filtered by status only for now)
    extracted_emails = frappe.get_all(
        "FC_BTW_Extracted_Emails",
        filters=filters_dict,
        fields=["name", "sender", "subject", "received_date", "trip_request_status", "communication_link"]
    )
    
    # Filter by date in Python since received_date is a Data field
    if from_date and to_date:
        from frappe.utils import getdate
        filtered_emails = []
        for email in extracted_emails:
            if email.received_date:
                try:
                    email_date = getdate(email.received_date)
                    if getdate(from_date) <= email_date <= getdate(to_date):
                        filtered_emails.append(email)
                except:
                    # If date parsing fails, skip this email
                    continue
        extracted_emails = filtered_emails

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

    return columns, data, None, None, number_cards


def get_number_cards(from_date=None, to_date=None, trip_status=None):
    """Calculate number cards for the dashboard"""
    from frappe.utils import getdate
    
    # Date filter for communications
    comm_filters = {}
    if from_date and to_date:
        comm_filters["creation"] = ["between", [from_date, to_date]]
    
    # Total emails received (from Communication doctype)
    total_emails_received = frappe.db.count("Communication", comm_filters)
    
    # Total emails extracted (from FC_BTW_Extracted_Emails)
    # Since received_date is a Data field, we need to filter manually
    all_extracted_emails = frappe.get_all("FC_BTW_Extracted_Emails", fields=["received_date"])
    total_emails_extracted = len(all_extracted_emails)
    
    if from_date and to_date:
        filtered_count = 0
        for email in all_extracted_emails:
            if email.received_date:
                try:
                    email_date = getdate(email.received_date)
                    if getdate(from_date) <= email_date <= getdate(to_date):
                        filtered_count += 1
                except:
                    continue
        total_emails_extracted = filtered_count
    
    # Total trip requests generated (from FC_BTW_Trip_Requests)
    # Trip requests
    trip_filters = {}
    if from_date and to_date:
        trip_filters["creation"] = ["between", [from_date, to_date]]
    if trip_status:
        trip_filters["trip_request_status"] = trip_status
    total_trip_requests = len(frappe.get_all("FC_BTW_Trip_Requests", filters=trip_filters, fields=["name"]))

    return [
        {"value": total_emails_received, "label": "Total Emails Received", "datatype": "Int"},
        {"value": total_emails_extracted, "label": "Total Emails Extracted", "datatype": "Int"},
        {"value": total_trip_requests, "label": "Total Trip Requests", "datatype": "Int"},
    ]


