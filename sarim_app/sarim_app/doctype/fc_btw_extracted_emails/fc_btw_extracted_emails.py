from frappe.model.document import Document
import frappe
from bs4 import BeautifulSoup
from anthropic import Anthropic
import json
import re
from sarim_app.sarim_app.services.booking_filter import prefilter_booking_email
from sarim_app.sarim_app.services.detect_missing_fields import detect_missing_fields

# Build an HTML + plain text body listing the booking row and missing fields
# def build_missing_info_email_body(trip, row):
#     # row is a child row doc (table_lftf)
#     missing_list = row.missing_fields_list or ""
#     html = f"""
#     <p>Hello,</p>
#     <p>We are missing details for booking <b>{row.booking_number}</b> in Trip <b>{trip.name}</b>.</p>
#     <p><b>Passenger:</b> {row.passenger_name or ''} <br>
#        <b>Missing fields:</b> {missing_list or 'None'}</p>
#     <p>Please reply to this same email (do NOT create a new email) with the missing details for booking <b>{row.booking_number}</b>.
#        Your reply will be auto-applied to the booking row.</p>
#     <hr>
#     <small>Reference: TR-{trip.name} | Booking: {row.booking_number}</small>
#     """
#     # plain text fallback
#     text = f"""Hello,

# We are missing details for booking {row.booking_number} in Trip {trip.name}.

# Passenger: {row.passenger_name or ''}
# Missing fields: {missing_list or 'None'}

# Please reply to this same email (do NOT create a new email) with the missing details for booking {row.booking_number}.
# Your reply will be auto-applied to the booking row.

# Reference: TR-{trip.name} | Booking: {row.booking_number}
# """
#     return html, text
def format_missing_fields_readable(missing_info):
    """
    Convert {"bookings": [{"missing_fields_list": [...]}, ...]} 
    into readable multi-line string for users.
    """
    if not missing_info or "bookings" not in missing_info:
        return "All bookings complete ✅"

    lines = []
    for idx, b in enumerate(missing_info.get("bookings", []), start=1):
        fields = b.get("missing_fields_list", [])
        if isinstance(fields, list):
            fields = ", ".join(fields)
        elif isinstance(fields, str):
            # in case stored as string already
            fields = fields.strip()
        fields = fields if fields else "None (Complete)"
        lines.append(f"Booking {idx} → {fields}")
    return "\n".join(lines)
def build_missing_info_email_body(trip, row):
    missing = row.missing_fields_list or "None"

    html = f"""
    <p>Hello,</p>

    <p>Thank you for contacting us. We appreciate your prompt communication regarding your booking.</p>

    <p>We still need a few details for your booking <b>{row.booking_number}</b> under Trip <b>{trip.name}</b>.</p>

    <p><b>Current details we have:</b></p>

    <ul>
        <li><b>Passenger:</b> {row.passenger_name or '-'}
        <li><b>Phone:</b> {row.passenger_number or '-'}
        <li><b>Pickup:</b> {row.pickup_location or '-'}
        <li><b>Drop:</b> {row.drop_location or '-'}
        <li><b>Date:</b> {row.pickup_date or '-'}
        <li><b>Time:</b> {row.pickup_time or '-'}
        <li><b>Reporting Time:</b> {row.reporting_time or '-'}
    </ul>

    <p><b>Missing:</b> {missing}</p>

    <p>Please reply to this same email (do NOT start a new thread) with the missing or corrected details.</p>

    <p>Example reply format:<br>
    <code>Pickup Location: New Town<br>Time: 6:30 AM</code></p>

    <hr>
    <small>Reference: TR-{trip.name} | Booking: {row.booking_number}</small>
    """
    return html
#     text = f"""
# Hello,

# Thank you for contacting us. We appreciate your prompt communication regarding your booking.

# We still need a few details for booking {row.booking_number} under Trip {trip.name}.

# Current info:
# Passenger: {row.passenger_name or '-'}
# Phone: {row.passenger_number or '-'}
# Pickup: {row.pickup_location or '-'}
# Drop: {row.drop_location or '-'}
# Date: {row.pickup_date or '-'}
# Time: {row.pickup_time or '-'}
# Reporting Time: {row.reporting_time or '-'}

# Missing: {missing}

# Please reply to this same email only with corrected/missing fields.
# Example:
# Pickup Location: New Town
# Time: 6:30 AM

# Reference: TR-{trip.name} | Booking: {row.booking_number}
# """
    

# def build_missing_info_email_body(trip, row):
#     missing = row.missing_fields_list or "None"

#     html = f"""
#     <p>Hello,</p>

#     <p>We need a few details for your booking <b>{row.booking_number}</b> under Trip <b>{trip.name}</b>.</p>

#     <p><b>Current details we have:</b></p>

#     <ul>
#         <li><b>Passenger:</b> {row.passenger_name or '-'}
#         <li><b>Phone:</b> {row.passenger_number or '-'}
#         <li><b>Pickup:</b> {row.pickup_location or '-'}
#         <li><b>Drop:</b> {row.drop_location or '-'}
#         <li><b>Date:</b> {row.pickup_date or '-'}
#         <li><b>Time:</b> {row.pickup_time or '-'}
#         <li><b>Reporting Time:</b> {row.reporting_time or '-'}
#     </ul>

#     <p><b>Missing:</b> {missing}</p>

#     <p>Please reply to this same email (do NOT start a new email) with corrected/missing details.</p>

#     <p>Example reply style:<br>
#     <code>Pickup Location: New Town<br>Time: 6:30 AM</code></p>

#     <hr>
#     <small>Reference: TR-{trip.name} | Booking: {row.booking_number}</small>
#     """

#     text = f"""
# Hello,

# We need some remaining details for booking {row.booking_number} under Trip {trip.name}.

# Current info:
# Passenger: {row.passenger_name or '-'}
# Phone: {row.passenger_number or '-'}
# Pickup: {row.pickup_location or '-'}
# Drop: {row.drop_location or '-'}
# Date: {row.pickup_date or '-'}
# Time: {row.pickup_time or '-'}
# Reporting Time: {row.reporting_time or '-'}

# Missing: {missing}

# Reply to this same email only with corrected/missing fields.
# Example:
# Pickup Location: New Town
# Time: 6:30 AM

# Reference: TR-{trip.name} | Booking: {row.booking_number}
# """
#     return html, text

# Send single mail per booking row, linked to Trip Request
# def send_missing_info_mail_for_row(trip, row):
#     html_body, text_body = build_missing_info_email_body(trip, row)
#     subject = f"Trip Request Update - {trip.name} | Booking: {row.booking_number}"
#     # Use reference_doctype pointing to Trip Request so replies get linked
#     try:
#         frappe.sendmail(
#             recipients=[trip.poc_email or trip.booked_by_email],
#             subject=subject,
#             message=html_body,
#             delayed=False,
#             reference_doctype="FC_BTW_Trip_Requests",
#             reference_name=trip.name,
#             now=True
#         )
#         frappe.db.commit()
#         frappe.msgprint(f"Sent missing-info mail for {row.booking_number} -> {trip.name}")
#         frappe.logger().info(f"Sent missing-info mail: {subject} -> {trip.name}")
#         return True
#     except Exception as e:
#         frappe.log_error(f"Failed to send missing mail for {trip.name} {row.booking_number}: {str(e)}", "Missing Mail Send Error")
#         return False
def send_missing_info_mail_for_row(trip, row):
    html = build_missing_info_email_body(trip, row)
    subject = f"Trip Request Update - {trip.name} | Booking: {row.booking_number}"

    try:
        frappe.sendmail(
            recipients=[trip.poc_email or trip.booked_by_email],
            subject=subject,
            message=html,
            reference_doctype="FC_BTW_Trip_Requests",
            reference_name=trip.name,
            delayed=False
        )

        frappe.db.commit()
        frappe.logger().info(f"📩 Missing info mail sent: {subject}")
        return True

    except Exception as e:
        frappe.log_error(
            f"Send mail failed for {trip.name} / {row.booking_number}: {str(e)}",
            "Missing Mail Error"
        )
        return False


# Helper to extract booking_number from subject - robust for common patterns
# def extract_booking_from_subject(subject):


def extract_booking_from_subject(subject):
    if not subject:
        return None

    # exact match for: <email>_<DD-MM-YYYY>_<HH-MM> <AM|PM>-R<number>
    pattern = r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+_\d{2}-\d{2}-\d{4}_\d{2}-\d{2}\s(?:AM|PM)-R\d+"

    m = re.search(pattern, subject)
    if m:
        return m.group(0).strip()

    return None



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
        limit=20
    )

    for comm in communications:

        # 3️⃣ Clean email HTML
        plain_text = BeautifulSoup(comm["content"], "html.parser").get_text(separator="\n").strip()
          # ✅ Skip reply emails — they should NOT come to booking extractor
        subject = (comm.get("subject") or "").lower()
        if subject.startswith("re:") or comm.get("in_reply_to"):
            print(f"↩️ Reply skipped from booking pipeline: {comm.get('name')}")
            continue
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
                            # "booking_number": row.booking_number,
                            "missing_fields_list": booking_missing
                        })

                # ✅ Update the main trip doc’s missing_fields and overall status
                # trip.missing_fields = json.dumps({"bookings": updated_missing})
                # trip.is_partial_booking = 1 if updated_missing else 0
                # trip.overall_trip_status = "Partial" if updated_missing else "Complete"

                # email_doc.missing_fields = json.dumps({"bookings": updated_missing})
                # email_doc.is_partial_booking = 1 if updated_missing else 0
                # email_doc.save(ignore_permissions=True)
                readable_missing = format_missing_fields_readable({"bookings": updated_missing})

                # ✅ Update the main trip doc’s missing_fields and overall status
                trip.missing_fields = readable_missing
                trip.is_partial_booking = 1 if updated_missing else 0
                trip.overall_trip_status = "Partial" if updated_missing else "Complete"
                trip.save(ignore_permissions=True)
                frappe.db.commit()

                # ✅ Sync the Extracted Email doc too
                email_doc.missing_fields = readable_missing
                email_doc.is_partial_booking = trip.is_partial_booking
                email_doc.save(ignore_permissions=True)
                frappe.db.commit()
                # trip.save(ignore_permissions=True)
                # frappe.db.commit()

                # ▶ Send missing-info mail for each partial booking row
                try:
                    partial_rows = [r for r in trip.table_lftf if (r.booking_status == "Partial" or (r.missing_fields_list and r.missing_fields_list.strip()))]
                    if partial_rows:
                        print(f"📨 Sending missing-info mails for {len(partial_rows)} partial booking(s)")
                    for row in partial_rows:
                        sent_ok = send_missing_info_mail_for_row(trip, row)
                        # optionally store last_sent_comm link in child row (if you want to track Communication.name)
                        # you can fetch last sent communication to this trip & subject below, if needed.
                        if sent_ok:
                            # mark we attempted sending (useful to avoid re-sending duplicates)
                            row.db_set("missing_mail_sent", 1)  # add this field if not present in child table (boolean)
                    # Commit final state
                    trip.save(ignore_permissions=True)
                    frappe.db.commit()
                except Exception as e:
                    frappe.log_error(f"Failed while sending missing mails for trip {trip.name}: {str(e)}", "Missing Mail Send Error")
                    print("Failed to send missing mails:", str(e))

                # process_replies_for_trip(trip)

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

def process_replies_for_all_trips():
    """Process all trips with partial booking automatically (scheduler entrypoint)."""
    trips = frappe.get_all(
        "FC_BTW_Trip_Requests",
        filters={"is_partial_booking": 1},
        fields=["name"]
    )
    print("Trips found:", trips)

    if not trips:
        frappe.logger().info("🚫 No pending partial trips found.")
        return

    for t in trips:
        trip = frappe.get_doc("FC_BTW_Trip_Requests", t.name)
        process_replies_for_trip(trip)


def process_replies_for_trip(trip):
    """Update trip child rows based on received mail replies."""
    try:
        # get received replies linked to this Trip Request
        replies = frappe.get_all(
            "Communication",
            filters={
                "sent_or_received": "Received",
                "reference_doctype": "FC_BTW_Trip_Requests",
                "reference_name": trip.name
            },
            fields=["name", "subject", "sender", "content", "in_reply_to", "creation"],
            order_by="creation desc"
        )

        if not replies:
            frappe.logger().info(f"📭 No replies for Trip {trip.name}")
            return

        for r in replies:
            # comm_doc = frappe.get_doc("Communication", r["name"])
            reply_subject = r.get("subject") or ""
            reply_content = BeautifulSoup(r.get("content") or "", "html.parser").get_text("\n").strip()

            # --- 1️⃣ Identify booking number ---
            booking_number = extract_booking_from_subject(reply_subject)
            # if not booking_number:
            #     m = re.search(r"Booking[:\s]*([A-Za-z0-9@._%+\-]+-R\d+)", reply_content, flags=re.IGNORECASE)
            #     if m:
            #         booking_number = m.group(1).strip()

            if not booking_number:
                frappe.log_error(
                    f"Reply {r['name']} couldn't be mapped to booking (no booking number): {reply_subject}",
                    "Reply Mapping Failed"
                )
                continue

            # --- 2️⃣ Find corresponding booking row ---
            trip.reload()
            found_row = next((row for row in trip.table_lftf if row.booking_number == booking_number), None)

            if not found_row:
                frappe.log_error(
                    f"Reply {r['name']} maps to booking {booking_number} but no child row found in {trip.name}",
                    "Reply Mapping Failed"
                )
                continue

            # --- 3️⃣ Extract fields from reply ---
            reply_data = extract_fields_from_reply(reply_content)

            # --- 4️⃣ Update only missing fields ---
            updated = False
            fields_to_update = [
                "passenger_name","passenger_number", "pickup_location", "drop_location",
                "pickup_date", "pickup_time", "reporting_time"
            ]

            for f in fields_to_update:
                val = reply_data.get(f)
                if val and not getattr(found_row, f):
                    found_row.set(f, val)
                    updated = True

            # --- 5️⃣ Re-evaluate missing fields for this row ---
            mini_bookings = [{
                "booking_number": found_row.booking_number,
                "passenger_name": found_row.passenger_name,
                "passenger_number": found_row.passenger_number,
                "pickup_location": found_row.pickup_location,
                "drop_location": found_row.drop_location,
                "pickup_date": found_row.pickup_date,
                "pickup_time": found_row.pickup_time,
                "reporting_time": found_row.reporting_time
            }]

            final_missing = detect_missing_fields({"bookings": mini_bookings})
            missing_for_row = []
            for mb in final_missing.get("bookings", []):
                if mb.get("booking_number") == found_row.booking_number:
                    missing_for_row = mb.get("missing_fields", [])
                    break

            found_row.missing_fields_list = ", ".join(missing_for_row) if missing_for_row else ""
            found_row.booking_status = "Partial" if missing_for_row else "Complete"

            # --- Save after row update ---
            if updated or True:
                trip.save(ignore_permissions=True)
                frappe.db.commit()
                frappe.logger().info(f"✅ Updated trip {trip.name} booking {found_row.booking_number} from reply {r['name']}")

        # --- 6️⃣ Update overall trip-level status ---
        trip.reload()
        any_partial = any(
            r.booking_status == "Partial" or (r.missing_fields_list and r.missing_fields_list.strip())
            for r in trip.table_lftf
        )

        trip.is_partial_booking = 1 if any_partial else 0
        trip.overall_trip_status = "Partial" if any_partial else "Complete"
        trip.save(ignore_permissions=True)
        frappe.db.commit()
        trip.reload()
        # --- 7️⃣ Sync linked Extracted Email doc (if exists) ---
        try:
            ee = frappe.get_all(
                "FC_BTW_Extracted_Emails",
                filters={"communication_link": trip.mail_link},
                fields=["name"],
                limit=1
            )
            if ee:
                ee_doc = frappe.get_doc("FC_BTW_Extracted_Emails", ee[0]["name"])
                ee_doc.is_partial_booking = trip.is_partial_booking
                ee_doc.overall_trip_status = trip.overall_trip_status
                ee_doc.save(ignore_permissions=True)
                frappe.db.commit()
        except Exception:
            pass

    except Exception as e:
        frappe.log_error(f"process_replies_for_trip failed for {trip.name}: {str(e)}", "Reply Processing Error")

# def extract_fields_from_reply(reply_content):
#     """Extracts common fields from reply using regex (extend with AI later)."""
    
#     reply_data = {}

#     # m_name = re.search(r"(?:name|passenger|mr\.?|ms\.?|mrs\.?)\s*[:\-]?\s*([a-zA-Z\s]+?)(?:\n|$|,|\s{2,}|\d)", reply_content, re.I)
#     # if m_name:
#     #     reply_data["passenger_name"] = m_name.group(1).strip()

#     m_name = re.search(r"(?:name|passenger)\s*[:=]\s*([a-zA-Z\s]+)", reply_content, re.I)
#     if m_name:
#         reply_data["passenger_name"] = m_name.group(1).strip()


#     m_phone = re.search(r"(\+?\d{7,15})", reply_content)
#     if m_phone:
#         reply_data["passenger_number"] = m_phone.group(1)

#     m_pickup = re.search(r"(pickup|pick up|start point|from)\s*(location|point|:|-)?\s*([^\n]+)", reply_content, re.I)
#     if m_pickup:
#         reply_data["pickup_location"] = m_pickup.group(3).strip()

#     m_drop = re.search(r"(drop|destination|to)\s*(location|point|:|-)?\s*([^\n]+)", reply_content, re.I)
#     if m_drop:
#         reply_data["drop_location"] = m_drop.group(3).strip()

#     m_pickup_date = re.search(r"(pickup|journey|travel)\s*(date|on|:|-)?\s*([^\n]+)", reply_content, re.I)
#     if m_pickup_date:
#         reply_data["pickup_date"] = m_pickup_date.group(3).strip()

#     m_pickup_time = re.search(r"(pickup|reporting)\s*(time|at|:|-)?\s*([^\n]+)", reply_content, re.I)
#     if m_pickup_time:
#         reply_data["pickup_time"] = m_pickup_time.group(3).strip()

#     return reply_data

def extract_fields_from_reply(reply_content):
    """
    AI-only field extractor — returns dict with only fields relevant
    to your booking update logic. No regex.
    """

    prompt = f"""
You extract booking details from user email replies.
Return JSON only. Missing fields = null.

Required keys:
- passenger_name
- passenger_number
- pickup_location
- drop_location
- pickup_date
- pickup_time
- reporting_time

Strict Output Format:
{{
 "passenger_name": "...",
 "passenger_number": "...",
 "pickup_location": "...",
 "drop_location": "...",
 "pickup_date": "...",
 "pickup_time": "...",
 "reporting_time": "..."
}}

User reply:
\"\"\"{reply_content}\"\"\"
    """
    api_key = frappe.local.conf.get("anthropic_api_key")
    client = Anthropic(api_key=api_key)
    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=800,
            messages=[{"role": "user", "content": prompt}]
        )

        raw = response.content[0].text.strip()

        # When model adds explanation wrapper, isolate JSON
        if not raw.startswith("{"):
            raw = raw[raw.find("{") : raw.rfind("}") + 1]

        data = json.loads(raw)

        # safety: ensure all keys exist
        for k in ["passenger_name","passenger_number","pickup_location","drop_location",
                  "pickup_date","pickup_time","reporting_time"]:
            data.setdefault(k, None)

        return data
    except Exception as e:
        frappe.log_error(f"AI parse failed: {e}", "Trip Reply Extractor")
        return {}