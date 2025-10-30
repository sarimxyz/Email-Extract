from frappe.model.document import Document
import frappe
from bs4 import BeautifulSoup
from anthropic import Anthropic
import json
import re
from sarim_app.sarim_app.services.booking_filter import prefilter_booking_email
from sarim_app.sarim_app.services.detect_missing_fields import detect_missing_fields


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
        fields=["sender", "subject", "content", "creation", "name"],
        limit=15
    )

    for comm in communications:

        # 3️⃣ Clean email HTML
        plain_text = BeautifulSoup(comm["content"], "html.parser").get_text(separator="\n").strip()

        # 5️⃣ Check if already processed
        exists = frappe.db.exists("FC_BTW_Extracted_Emails", {"source_email_id": comm["name"]})

        if exists:
            continue

        prefilter_result = prefilter_booking_email(comm["subject"], plain_text)

        if not prefilter_result["is_likely_booking"]:
            print(f"❌ Skipped non-booking mail: {prefilter_result['reason']}")
            continue  # skip Claude API call

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
        email_context = f"""
        Sender: {comm['sender']}
        Subject: {comm['subject']}

        Body:
        {plain_text}
        """

        prompt = template_prompt.replace("{email_text}", email_context)

        # 6️⃣ Call Claude
        try:
            response = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=4096,
                messages=[{"role": "user", "content": prompt}]
            )
            ai_output = response.content[0].text.strip()
            ai_output = ai_output.strip()
            ai_output = re.sub(r"^```(json)?", "", ai_output)
            ai_output = re.sub(r"```$", "", ai_output)
            ai_output = ai_output.strip()
            prompt_tokens = response.usage.input_tokens
            completion_tokens = response.usage.output_tokens
            total_tokens = prompt_tokens + completion_tokens
             # ✅ Step 1: Defensive check before parsing
            if not ai_output or not ai_output.startswith("{"):
                frappe.log_error(
                    f"⚠️ Non-JSON output for {comm['name']}: {ai_output[:500]}",
                    "Cab Booking - JSON Warning"
                )
                continue

            # ✅ Step 2: Safe JSON parse
            try:
                data = json.loads(ai_output)
            except Exception as e:
                frappe.log_error(
                    f"JSON Parse Error for {comm['name']}: {str(e)} | Raw output: {ai_output[:500]}",
                    "Cab Booking - JSON Error"
                )
                continue

            missing_info = detect_missing_fields(data)
            print(json.dumps(missing_info, indent=2))
            is_partial = bool(missing_info["bookings"])
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
                    "missing_fields": json.dumps(missing_info),
                    "overall_trip_status": "Partial",
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
                    booking_number = f"{base_name}-R{idx + 1}"

                    

                    # ✅ Find missing fields for this booking (from missing_info)
                    booking_missing = []
                    if missing_info.get("bookings"):
                        for missing_booking in missing_info["bookings"]:
                            if (
                                missing_booking.get("index") == idx + 1
                                or missing_booking.get("booking_number") == booking_number
                            ):
                                booking_missing = missing_booking.get("missing_fields", [])
                                break
                    # b["booking_number"] = booking_number
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

               # 4️⃣ Re-run missing field detection (now with booking_numbers)
                final_missing_info = detect_missing_fields({
                    "bookings": [
                        {**b, "booking_number": f"{base_name}-R{idx + 1}"} 
                        for idx, b in enumerate(bookings)
                    ]
                })

                # ✅ Update each child row and also the main trip with refreshed missing info
                updated_missing = []

                for row in trip.table_lftf:
                    booking_missing = []
                    for missing_booking in final_missing_info.get("bookings", []):
                        if missing_booking.get("booking_number") == row.booking_number:
                            booking_missing = missing_booking.get("missing_fields", [])
                            break

                    row.missing_fields_list = ", ".join(booking_missing) if booking_missing else ""
                    row.booking_status = "Partial" if booking_missing else "Complete"

                    # also keep track to update parent trip_request
                    if booking_missing:
                        updated_missing.append({
                            "booking_number": row.booking_number,
                            "missing_fields_list": booking_missing
                        })

                # ✅ Update the main trip doc’s missing_fields and overall status
                trip.missing_fields = json.dumps({"bookings": updated_missing})
                trip.is_partial_booking = 1 if updated_missing else 0
                trip.overall_trip_status = "Partial" if updated_missing else "Complete"

                email_doc.missing_fields = json.dumps({"bookings": updated_missing})
                email_doc.is_partial_booking = 1 if updated_missing else 0
                email_doc.save(ignore_permissions=True)

                trip.save(ignore_permissions=True)
                frappe.db.commit()

                print("✅ Final missing fields updated per booking_number:", 
                    [f"{r.booking_number}: {r.missing_fields_list}" for r in trip.table_lftf])

                                # 📨 Send individual missing fields emails per booking
                try:
                    if updated_missing:
                        for missing in updated_missing:
                            booking_num = missing.get("booking_number")
                            fields_list = ", ".join(missing.get("missing_fields_list", [])) if isinstance(missing.get("missing_fields_list"), list) else missing.get("missing_fields_list")

                            html_body = f"""
                            <p>Dear {trip.booked_by_name or 'Customer'},</p>
                            <p>We’ve created your trip request <b>{trip.trip_name}</b>.</p>
                            <p>For booking <b>{booking_num}</b>, the following details are missing:</p>
                            <ul>
                                {''.join([f"<li>{field}</li>" for field in fields_list.split(', ')])}
                            </ul>
                            <p>Please reply to this email with the missing details. Our system will automatically update your booking.</p>
                            <br>
                            <p>Thank you,<br>Cab Booking Team</p>
                            """

                            recipient_email = (
                                trip.booked_by_email
                                or trip.poc_email
                                or trip.billed_to_email
                                or "support@example.com"
                            )

                            frappe.sendmail(
                                recipients=[recipient_email],
                                subject=f"Missing Details for Booking {booking_num}",
                                message=html_body
                            )

                            print(f"📧 Sent missing fields email for {booking_num} → {recipient_email}")

                except Exception as mail_err:
                    frappe.log_error(f"Missing Fields Email Error: {str(mail_err)}", "Cab Booking - Missing Fields Mail")
                    print(f"❌ Failed to send missing field emails: {str(mail_err)}")


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

        # 🧩 Step 9: Auto-update missing Trip Request fields from replies
        try:
            replies = frappe.get_all(
                "Communication",
                filters={
                    "reference_doctype": "Communication",
                    "reference_name": comm["name"],
                    "sent_or_received": "Received"
                },
                fields=["name", "subject", "content", "creation"]
            )

            if replies:
                print(f"📨 Found {len(replies)} reply(s) for {comm['name']}")

            for reply in replies:
                reply_text = BeautifulSoup(reply["content"], "html.parser").get_text(separator="\n").strip()

                prefilter_reply = prefilter_booking_email(reply["subject"], reply_text)
                if not prefilter_reply["is_likely_booking"]:
                    print(f"↪️ Skipping irrelevant reply: {reply['subject']}")
                    continue

                reply_context = f"""
                Sender: {reply['sender']}
                Subject: {reply['subject']}

                Body:
                {reply_text}
                """
                reply_prompt = template_prompt.replace("{email_text}", reply_context)

                response = client.messages.create(
                    model="claude-haiku-4-5-20251001",
                    max_tokens=2048,
                    messages=[{"role": "user", "content": reply_prompt}]
                )
                reply_output = response.content[0].text.strip()
                reply_output = re.sub(r"^```(json)?", "", reply_output)
                reply_output = re.sub(r"```$", "", reply_output).strip()

                try:
                    reply_data = json.loads(reply_output)
                except Exception as e:
                    frappe.log_error(f"Reply JSON parse failed for {reply['name']}: {str(e)}", "Cab Booking Reply Error")
                    continue

                updated = False
                for idx, row in enumerate(trip.table_lftf):
                    booking = None
                    for b in reply_data.get("bookings", []):
                        if (
                            b.get("passenger_name") == row.passenger_name
                            or b.get("booking_number") == row.booking_number
                        ):
                            booking = b
                            break

                    if not booking:
                        continue

                    fields_to_update = [
                        "pickup_location", "drop_location", "pickup_date", "pickup_time",
                        "drop_time", "reporting_time", "passenger_number"
                    ]
                    for f in fields_to_update:
                        val = booking.get(f)
                        if val and not row.get(f):
                            row.set(f, val)
                            updated = True

                if updated:
                    trip.save(ignore_permissions=True)
                    frappe.db.commit()
                    print(f"✅ Trip {trip.name} updated with details from reply {reply['name']}")

        except Exception as e:
            frappe.log_error(f"Reply update failed for {comm['name']}: {str(e)}", "Cab Booking - Reply Update")
            print(f"❌ Reply update failed: {str(e)}")  
