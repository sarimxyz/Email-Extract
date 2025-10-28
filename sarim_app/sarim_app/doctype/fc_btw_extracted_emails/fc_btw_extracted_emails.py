from frappe.model.document import Document
import frappe
from bs4 import BeautifulSoup
from anthropic import Anthropic
import json

class FC_BTW_Extracted_Emails(Document):
     def autoname(self):
        """
        Naming pattern:
        sender_dd-mm-yyyy_HH-MM AM/PM
        If duplicate, add suffix (_2, _3, etc.)
        """

        sender = (self.sender or "unknown").strip()
        timestamp = self.received_date.strftime("%d-%m-%Y_%I-%M %p")
        base_name = f"{sender}_{timestamp}"

        # Count existing with same base prefix
        existing_count = frappe.db.count(
            "FC_BTW_Extracted_Emails",
            {"name": ["like", f"{base_name}%"]}
        )

        # Final unique name
        self.name = base_name if existing_count == 0 else f"{base_name}_{existing_count + 1}"

def detect_missing_fields(data):
    # Must-have passenger-level fields
    REQUIRED_PASSENGER_FIELDS = ["passenger_name", "pickup_date", "pickup_location"]

    # Optional but preferred passenger-level fields
    # OPTIONAL_PASSENGER_FIELDS = ["passenger_number", "pickup_time", "reporting_time"]

    # Must-have outer fields (top-level)
    REQUIRED_TRIP_FIELDS = ["point_of_contact", "booked_by", "billed_to"]

    missing = {
        "bookings": [],   # per-passenger missing data
        "trip_level": []  # top-level missing data
    }

    # --- Check passenger-level fields ---
    bookings = data.get("bookings", [])
    if isinstance(bookings, dict):
        bookings = [bookings]

    for idx, b in enumerate(bookings):
        missing_fields = []

        # required passenger fields
        for f in REQUIRED_PASSENGER_FIELDS:
            if not b.get(f):
                missing_fields.append(f)

        # number fallback logic (use POC number if no passenger number)
        if not b.get("passenger_number"):
            if not data.get("point_of_contact", {}).get("number"):
                missing_fields.append("passenger_number")

        # pickup_time/reporting_time fallback
        if not b.get("pickup_time") and not b.get("reporting_time"):
            missing_fields.append("pickup_time/reporting_time")

        if missing_fields:
            missing["bookings"].append({
                "index": idx + 1,
                "missing_fields": missing_fields
            })

    # --- Check outer fields ---
    for f in REQUIRED_TRIP_FIELDS:
        if not data.get(f) or not any(data[f].values()):
            missing["trip_level"].append(f)

    return missing


def process_received_emails_to_trip_requests():
    """
    1. Fetch all received emails from Communication with subject 'cab booking'
    2. Add them to Extracted Email New
    3. Extract trip data using Claude
    4. Create Trip Request docs automatically
    5. Update Extracted Email New with status and error
    """
    # 1️⃣ Initialize Claude client
    api_key = frappe.local.conf.get("anthropic_api_key")
    client = Anthropic(api_key=api_key)

    communications = frappe.get_all(
        "Communication",
        filters={
            "communication_type": "Communication",
            "sent_or_received": "Received"
        },
        fields=["sender", "subject", "content", "creation", "name"]
    )

    for comm in communications:

        # 3️⃣ Clean email HTML
        plain_text = BeautifulSoup(comm["content"], "html.parser").get_text(separator="\n").strip()
        
        # 4️⃣ Prepare email content (subject + body)
        email_content = f"Subject: {comm['subject']}\n\n{plain_text}"

        # 5️⃣ Check if already processed
        exists = frappe.db.exists(
        "FC_BTW_Extracted_Emails",
        {"sender": comm["sender"], "subject": comm["subject"], "message_body": plain_text}
        )
        if exists:
            continue

        # 6️⃣ FIRST AI CALL: Check if this is a cab booking email
        validation_prompt = f"""
    You are an expert email classifier for identifying CAB / TAXI / VEHICLE BOOKING related emails.

    Your job: Analyze the following email and decide if it is related to any CAB BOOKING, TAXI BOOKING, VEHICLE BOOKING, or TRAVEL REQUEST.

    Email:
    {email_content}

    IMPORTANT RULES:
    - Return ONLY a raw JSON object. No markdown, no text, no code blocks.
    - Format:
    {{"is_cab_booking": true or false, "reason": "short explanation"}}

    CLASSIFY AS TRUE (cab booking) IF email contains **any** of the following:
    - Mentions of cab, taxi, vehicle, car, trip, chauffeur, airport pickup/drop, etc.
    - Passenger names, pickup/drop locations, travel date or time.
    - Booking confirmation, request for cab, or trip details.
    - Vendor or company sending cab booking confirmations.
    - Attachments or booking details even if short.

    CLASSIFY AS FALSE (not cab booking) IF:
    - It's OTP, marketing, newsletter, or unrelated service mail.
    - It's about invoices, password resets, or welcome messages.

    Even if the email looks partially like a booking (e.g., “Request for vehicle” or “trip details”), still mark TRUE.
    Be lenient — better to classify possibly true than to miss one.

    Return result strictly as JSON:
    {{"is_cab_booking": true, "reason": "mentions pickup and drop details"}}
    """
        try:
                validation_response = client.messages.create(
                    model="claude-4-sonnet-20250514",
                    max_tokens=1024,
                    messages=[{"role": "user", "content": validation_prompt}]
                )
                validation_output = validation_response.content[0].text.strip()
                print(validation_output)
                validation_data = json.loads(validation_output)
                if not validation_data.get("is_cab_booking", False):
                    continue
        except Exception as e:
                frappe.log_error(f"AI Validation Error for {comm['name']}: {str(e)}", "Cab Booking - Validation Error")
                continue

            # 7️⃣ Create Extracted Email
        try:
                email_doc = frappe.get_doc({
                    "doctype": "FC_BTW_Extracted_Emails",
                    "source_email_id": comm["name"],
                    "sender": comm["sender"],
                    "subject": comm["subject"],
                    "message_body": plain_text,
                    "received_date": comm["creation"],
                    "communication_link": comm["name"]
                })
                email_doc.insert()
                frappe.db.commit()
                print(f"✅ Created extracted email: {comm['name']}")
        except Exception as ex:
                frappe.log_error(f"Failed to create extracted email {comm['name']}: {str(ex)}", "Cab Booking - Insert Error")
                print(f"❌ Failed to create extracted email {comm['name']}: {str(ex)}")
                continue
        
        # Fetch prompt from Cab Settings
        cab_settings = frappe.get_single("FC_BTW_Cab_Settings")
        template_prompt = cab_settings.prompt

        # Replace placeholder {email_text} with actual email content
        prompt = template_prompt.replace("{email_text}", plain_text)

        # 6️⃣ Call Claude
        try:
            response = client.messages.create(
                model="claude-4-sonnet-20250514",
                max_tokens=4096,
                messages=[{"role": "user", "content": prompt}]
            )
            ai_output = response.content[0].text.strip()
            prompt_tokens = response.usage.input_tokens
            completion_tokens = response.usage.output_tokens
            total_tokens = prompt_tokens + completion_tokens
            try:
                data = json.loads(ai_output)
            except Exception as e:
                frappe.log_error(f"JSON Parse Error for {comm['name']}: {str(e)}", "Cab Booking - JSON Error")
                continue

            missing_info = detect_missing_fields(data)
            print(json.dumps(missing_info, indent=2))
            is_partial = bool(missing_info["bookings"] or missing_info["trip_level"])
            email_doc.is_partial_booking = 1 if is_partial else 0
            email_doc.missing_fields = json.dumps(missing_info)
            email_doc.save()
            frappe.db.commit()
        except Exception as e:
            email_doc.trip_request_status = "Failed"
            email_doc.trip_request_error = f"Claude API call failed: {str(e)}"
            email_doc.save()
            frappe.db.commit()
            continue
              
        # 7️⃣ Parse JSON
        try:
            data = json.loads(ai_output)
        except json.JSONDecodeError as e:
            email_doc.trip_request_status = "Failed"
            email_doc.trip_request_error = f"JSON decode error: {str(e)}"
            email_doc.has_multiple_bookings = False
            email_doc.number_of_bookings = 0
            email_doc.save()
            frappe.db.commit()
            continue

        # ✅ JSON parsed successfully → update Extracted Email immediately
        email_doc.has_multiple_bookings = data.get("has_multiple_bookings", False)
        email_doc.number_of_bookings = data.get("number_of_bookings", 0)
        email_doc.save()
        frappe.db.commit()
        base_name = email_doc.name

        # 8️⃣ Insert into Trip Request
        try:  
                trip = frappe.get_doc({
                    "doctype": "FC_BTW_Trip_Requests",
                    "trip_name":base_name,
                    "summary": data.get("summary") or "",
                    "is_partial_booking": 1 if is_partial else 0,
                    "missing_fields_json": json.dumps(missing_info),
                    "overall_trip_status": "Partial" if is_partial else "Complete",
                    "required_vehicle_type": data.get("vehicle_type") or "",
                    "city": data.get("city") or "",
                    "miscellaneous_requirements": data.get("miscellaneous_requirements") or "",
                    "duty_type":data.get("duty_type") or "",
                    "request_type":data.get("request_type") or "",
                    "special_request":data.get("special_request") or "",
                    "remarks":data.get("remarks") or "",
                    "notes":data.get("notes") or "",
                    # Booked By contact details
                    "booked_by_name": data.get("booked_by", {}).get("name") or "",
                    "booked_by_email": data.get("booked_by", {}).get("email") or "",
                    "booked_by_number": data.get("booked_by", {}).get("number") or "",
                    # Billed To contact details
                    "billed_to_name": data.get("billed_to", {}).get("name") or "",
                    "billed_to_email": data.get("billed_to", {}).get("email") or "",
                    "billed_to_number": data.get("billed_to", {}).get("number") or "",
                    # Point of Contact details
                    "poc_name": data.get("point_of_contact", {}).get("name") or "",
                    "poc_email": data.get("point_of_contact", {}).get("email") or "",
                    "poc_number": data.get("point_of_contact", {}).get("number") or "",
                    "mail_link": comm["name"],
                    "email_message_body": plain_text,
                    "ai_json_response": ai_output,
                    "ai_token_usage": total_tokens
                })

                bookings = data.get("bookings", [])
                if isinstance(bookings, dict):  # safety for single object
                    bookings = [bookings]

                # ✅ Generate booking numbers and add missing field tracking
                for idx, b in enumerate(bookings):
                    # Find missing fields for THIS specific booking
                    booking_missing = []
                    if missing_info["bookings"]:
                        for missing_booking in missing_info["bookings"]:
                            if missing_booking["index"] == idx + 1:
                                booking_missing = missing_booking["missing_fields"]
                                break
                    
                    # ✅ Generate globally unique booking number
                    # Get last booking number from database
                    last_booking = frappe.db.sql("""
                        SELECT MAX(CAST(SUBSTRING_INDEX(SUBSTRING(booking_number, 2), '-', 1) AS UNSIGNED)) as max_num
                        FROM `tabFC_TR_MultipleBooking_CT`
                        WHERE booking_number LIKE '#%'
                    """, as_dict=True)

                    next_num = 1
                    if last_booking and last_booking[0].get("max_num"):
                        next_num = int(last_booking[0]["max_num"]) + 1

                    # Add row index to make it guaranteed unique
                    booking_number = f"#{next_num}R{idx + 1}"
                    
                    trip.append("table_lftf", {
                        "booking_number": booking_number, 
                        "passenger_name": b.get("passenger_name") or "",
                        "passenger_number": b.get("passenger_number") or "",
                        "pickup_location": b.get("pickup_location") or "",
                        "drop_location": b.get("drop_location") or "",
                        "pickup_date": b.get("pickup_date") or "",
                        "pickup_time": b.get("pickup_time") or "",
                        "drop_time": b.get("drop_time") or "",
                        "reporting_time": b.get("reporting_time") or "",
                        "passenger_specific_request": b.get("passenger_specific_request") or "",
                        
                        "booking_status": "Partial" if booking_missing else "Complete",
                        "missing_fields_list": ", ".join(booking_missing) if booking_missing else ""
                    })
                trip.insert()
                frappe.db.commit()

                trip.reload()
                # ✅ Ensure missing fields reflect correctly inside the child table
                for idx, row in enumerate(trip.table_lftf):
                    booking_missing = []
                    for missing_booking in missing_info.get("bookings", []):
                        if missing_booking.get("index") == idx + 1:
                            booking_missing = missing_booking.get("missing_fields", [])
                            break

                    # Update fields for this row
                    row.missing_fields_list = ", ".join(booking_missing) if booking_missing else ""
                    row.booking_status = "Partial" if booking_missing else "Complete"

                # ✅ Save trip again to persist child-level updates
                trip.save(ignore_permissions=True)
                frappe.db.commit()
                print("✅ Updated missing fields list for child table:", [r.missing_fields_list for r in trip.table_lftf])

                # ✅ Update Extracted Email
                email_doc.trip_request_status = "Successful"
                email_doc.trip_request_error = ""
                email_doc.save()
                frappe.db.commit()

        except Exception as ex:
                email_doc.trip_request_status = "Failed"
                email_doc.trip_request_error = str(ex)
                email_doc.save()
                frappe.db.commit()
