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

                for b in bookings:
                    trip.append("table_lftf", {
                        "passenger_name": b.get("passenger_name") or "",
                        "passenger_number": b.get("passenger_number") or "",
                        "pickup_location": b.get("pickup_location") or "",
                        "drop_location": b.get("drop_location") or "",
                        "pickup_date": b.get("pickup_date") or "",
                        "pickup_time": b.get("pickup_time") or "",
                        "drop_time": b.get("drop_time") or "",
                        "reporting_time": b.get("reporting_time") or "",
                        "passenger_specific_request": b.get("passenger_specific_request") or ""
                    })
                trip.insert()
                frappe.db.commit()

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
