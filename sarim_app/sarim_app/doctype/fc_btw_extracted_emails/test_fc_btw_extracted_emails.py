# Copyright (c) 2025, sarim and Contributors
# See license.txt

# import frappe
from frappe.tests.utils import FrappeTestCase


class TestFC_BTW_Extracted_Emails(FrappeTestCase):
	pass
 # 6️⃣ FIRST AI CALL: Check if this is a cab booking email
    #     validation_prompt = f"""
    # You are an expert email classifier for identifying CAB / TAXI / VEHICLE BOOKING related emails.

    # Your job: Analyze the following email and decide if it is related to any CAB BOOKING, TAXI BOOKING, VEHICLE BOOKING, or TRAVEL REQUEST.

    # Email:
    # {email_content}

    # IMPORTANT RULES:
    # - Return ONLY a raw JSON object. No markdown, no text, no code blocks.
    # - Format:
    # {{"is_cab_booking": true or false, "reason": "short explanation"}}

    # CLASSIFY AS TRUE (cab booking) IF email contains **any** of the following:
    # - Mentions of cab, taxi, vehicle, car, trip, chauffeur, airport pickup/drop, etc.
    # - Passenger names, pickup/drop locations, travel date or time.
    # - Booking confirmation, request for cab, or trip details.
    # - Vendor or company sending cab booking confirmations.
    # - Attachments or booking details even if short.

    # CLASSIFY AS FALSE (not cab booking) IF:
    # - It's OTP, marketing, newsletter, or unrelated service mail.
    # - It's about invoices, password resets, or welcome messages.

    # Even if the email looks partially like a booking (e.g., “Request for vehicle” or “trip details”), still mark TRUE.
    # Be lenient — better to classify possibly true than to miss one.

    # Return result strictly as JSON:
    # {{"is_cab_booking": true, "reason": "mentions pickup and drop details"}}
    # """
    #     try:
    #             validation_response = client.messages.create(
    #                 model="claude-4-sonnet-20250514",
    #                 max_tokens=1024,
    #                 messages=[{"role": "user", "content": validation_prompt}]
    #             )
    #             validation_output = validation_response.content[0].text.strip()
    #             print(validation_output)
    #             validation_data = json.loads(validation_output)
    #             if not validation_data.get("is_cab_booking", False):
    #                 continue
        # except Exception as e:
        #         frappe.log_error(f"AI Validation Error for {comm['name']}: {str(e)}", "Cab Booking - Validation Error")
        #         continue



   # try:
        #     response = client.messages.create(
        #         model="claude-4-sonnet-20250514",
        #         max_tokens=4096,
        #         messages=[{"role": "user", "content": prompt}]
        #     )

        #     ai_output = response.content[0].text.strip()
        #     prompt_tokens = response.usage.input_tokens
        #     completion_tokens = response.usage.output_tokens
        #     total_tokens = prompt_tokens + completion_tokens

        #     # ✅ Step 1: Defensive check before parsing
        #     if not ai_output or not ai_output.startswith("{"):
        #         frappe.log_error(
        #             f"⚠️ Non-JSON output for {comm['name']}: {ai_output[:500]}",
        #             "Cab Booking - JSON Warning"
        #         )
        #         continue

        #     # ✅ Step 2: Safe JSON parse
        #     try:
        #         data = json.loads(ai_output)
        #     except Exception as e:
        #         frappe.log_error(
        #             f"JSON Parse Error for {comm['name']}: {str(e)} | Raw output: {ai_output[:500]}",
        #             "Cab Booking - JSON Error"
        #         )
        #         continue

        # except Exception as e:
        #     frappe.log_error(f"API Error for {comm['name']}: {str(e)}", "Cab Booking - API Error")
        #     continue


# STEP 1️⃣ - Email bhejne se PEHLE Communication record banao
# ==========================================
# comm = frappe.new_doc("Communication")
# comm.communication_type = "Communication"  # "Email" nahi, "Communication" use karo
# comm.communication_medium = "Email"
# comm.sent_or_received = "Sent"
# comm.recipients = "sarimk360@gmail.com"
# comm.subject = "Test Email"
# comm.content = "Hello, this is a test email from Frappe!"
# comm.status = "Sent"
# comm.insert(ignore_permissions=True)
# frappe.db.commit()

# # ==========================================
# # STEP 2️⃣ - Ab email bhejo aur Message-ID track karo
# # ==========================================
# frappe.sendmail(
#     recipients=["sarimk360@gmail.com"],
#     subject=comm.subject,
#     message=comm.content,
#     delayed=False,
#     reference_doctype="Communication",
#     reference_name=comm.name,
#     now=True  # 👈 ensures email bhejte hi record update ho
# )

# frappe.db.commit()

# # Communication record reload karo taaki updated message_id mil sake
# comm.reload()
# print(f"✅ Sent mail saved as: {comm.name}")
# print(f"📬 Message ID captured: {comm.message_id if comm.message_id else '❌ None (SMTP didn’t return Message-ID)'}")

# # ==========================================
# # STEP 3️⃣ - Recent outgoing mails dekh lo (confirmation)
# # ==========================================
# outgoing = frappe.get_all(
#     "Communication",
#     filters={"sent_or_received": "Sent"},
#     fields=["name", "subject", "message_id", "creation"],
#     order_by="creation desc",
#     limit=3
# )

# print("\n📤 Outgoing Emails:")
# for o in outgoing:
#     print(f" - {o.name} | Subject: {o.subject} | Message ID: {o.message_id}")

# # ==========================================
# # STEP 4️⃣ - Recent incoming mails check karo (reply aaye kya)
# # ==========================================
# incoming = frappe.get_all(
#     "Communication",
#     filters={"sent_or_received": "Received"},
#     fields=["name", "subject", "in_reply_to", "message_id", "creation"],
#     order_by="creation desc",
#     limit=5
# )

# print("\n📥 Incoming Emails:")
# for c in incoming:
#     print(f" - {c.name} | Subject: {c.subject}")
#     print(f"   In-Reply-To: {c.in_reply_to}")
#     print(f"   Message ID: {c.message_id}\n")

# # ==========================================
# # STEP 5️⃣ - Final summary
# # ==========================================
# sent_comm = frappe.get_all(
#     "Communication",
#     filters={"sent_or_received": "Sent"},
#     fields=["name", "message_id", "subject"],
#     order_by="creation desc",
#     limit=1
# )[0]

# print(f"📦 Latest Sent Message-ID: {sent_comm.message_id}")

# replies = frappe.get_all(
#     "Communication",
#     filters={
#         "reference_doctype": "Communication",
#         "reference_name": comm.name,
#         "sent_or_received": "Received"
#     },
#     fields=["name", "sender", "subject", "creation", "content"]
# )
# comm = frappe.get_all(
#     "Communication",
#     filters={
#         "sent_or_received": "Sent",
#         "subject": "Test Email"
#     },
#     fields=["name", "reference_doctype", "reference_name"],
#     order_by="creation desc",
#     limit=1
# )[0]
# parent_trip = frappe.db.get_value(
#     "Communication",
#     comm["name"],
#     ["reference_doctype", "reference_name"],
#     as_dict=True
# )

# if parent_trip and parent_trip.reference_doctype == "Trip Request":
#     trip_request_name = parent_trip.reference_name
#     print(f"📎 Linking reply to Trip Request {trip_request_name}")
# else:
#     print("❌ No Trip Request linked to this outgoing mail.")

import re
from bs4 import BeautifulSoup

# Build an HTML + plain text body listing the booking row and missing fields
def build_missing_info_email_body(trip, row):
    # row is a child row doc (table_lftf)
    missing_list = row.missing_fields_list or ""
    html = f"""
    <p>Hello,</p>
    <p>We are missing details for booking <b>{row.booking_number}</b> in Trip <b>{trip.name}</b>.</p>
    <p><b>Passenger:</b> {row.passenger_name or ''} <br>
       <b>Missing fields:</b> {missing_list or 'None'}</p>
    <p>Please reply to this same email (do NOT create a new email) with the missing details for booking <b>{row.booking_number}</b>.
       Your reply will be auto-applied to the booking row.</p>
    <hr>
    <small>Reference: TR-{trip.name} | Booking: {row.booking_number}</small>
    """
    # plain text fallback
    text = f"""Hello,

We are missing details for booking {row.booking_number} in Trip {trip.name}.

Passenger: {row.passenger_name or ''}
Missing fields: {missing_list or 'None'}

Please reply to this same email (do NOT create a new email) with the missing details for booking {row.booking_number}.
Your reply will be auto-applied to the booking row.

Reference: TR-{trip.name} | Booking: {row.booking_number}
"""
    return html, text

# Send single mail per booking row, linked to Trip Request
def send_missing_info_mail_for_row(trip, row):
    html_body, text_body = build_missing_info_email_body(trip, row)
    subject = f"Trip Request Update - {trip.name} | Booking: {row.booking_number}"
    # Use reference_doctype pointing to Trip Request so replies get linked
    try:
        frappe.sendmail(
            recipients=[trip.poc_email or trip.booked_by_email or row.passenger_number or "support@example.com"],
            subject=subject,
            message=html_body,
            delayed=False,
            reference_doctype="FC_BTW_Trip_Requests",
            reference_name=trip.name,
            now=True
        )
        frappe.db.commit()
        frappe.msgprint(f"Sent missing-info mail for {row.booking_number} -> {trip.name}")
        frappe.logger().info(f"Sent missing-info mail: {subject} -> {trip.name}")
        return True
    except Exception as e:
        frappe.log_error(f"Failed to send missing mail for {trip.name} {row.booking_number}: {str(e)}", "Missing Mail Send Error")
        return False

# Helper to extract booking_number from subject - robust for common patterns
def extract_booking_from_subject(subject):
    if not subject:
        return None
    # look for "Booking: <value>" or "#123R1" like patterns
    m = re.search(r"Booking[:\s]*([#\w\-R]+)", subject, flags=re.IGNORECASE)
    if m:
        return m.group(1).strip()
    # fallback: look for pattern like #12R1 or something with R#
    m2 = re.search(r"(#?\w+R\d+)", subject)
    if m2:
        return m2.group(1)
    return None
# print("✅ Final missing fields updated per booking_number:", 
                #     [f"{r.booking_number}: {r.missing_fields_list}" for r in trip.table_lftf])

                #                 # 📨 Send individual missing fields emails per booking
                # try:
                #     if updated_missing:
                #         for missing in updated_missing:
                #             booking_num = missing.get("booking_number")
                #             fields_list = ", ".join(missing.get("missing_fields_list", [])) if isinstance(missing.get("missing_fields_list"), list) else missing.get("missing_fields_list")

                #             html_body = f"""
                #             <p>Dear {trip.booked_by_name or 'Customer'},</p>
                #             <p>We’ve created your trip request <b>{trip.trip_name}</b>.</p>
                #             <p>For booking <b>{booking_num}</b>, the following details are missing:</p>
                #             <ul>
                #                 {''.join([f"<li>{field}</li>" for field in fields_list.split(', ')])}
                #             </ul>
                #             <p>Please reply to this email with the missing details. Our system will automatically update your booking.</p>
                #             <br>
                #             <p>Thank you,<br>Cab Booking Team</p>
                #             """

                #             recipient_email = (
                #                 trip.booked_by_email
                #                 or trip.poc_email
                #                 or trip.billed_to_email
                #                 or "support@example.com"
                #             )

                #             frappe.sendmail(
                #                 recipients=[recipient_email],
                #                 subject=f"Missing Details for Booking {booking_num}",
                #                 message=html_body
                #             )

                #             print(f"📧 Sent missing fields email for {booking_num} → {recipient_email}")

                # except Exception as mail_err:
                #     frappe.log_error(f"Missing Fields Email Error: {str(mail_err)}", "Cab Booking - Missing Fields Mail")
                #     print(f"❌ Failed to send missing field emails: {str(mail_err)}")
 # # 🧩 Step 9: Auto-update missing Trip Request fields from replies
        # try:
        #     replies = frappe.get_all(
        #         "Communication",
        #         filters={
        #             "reference_doctype": "Communication",
        #             "reference_name": comm["name"],
        #             "sent_or_received": "Received"
        #         },
        #         fields=["name", "subject", "content", "creation"]
        #     )

        #     if replies:
        #         print(f"📨 Found {len(replies)} reply(s) for {comm['name']}")

        #     for reply in replies:
        #         reply_text = BeautifulSoup(reply["content"], "html.parser").get_text(separator="\n").strip()

        #         prefilter_reply = prefilter_booking_email(reply["subject"], reply_text)
        #         if not prefilter_reply["is_likely_booking"]:
        #             print(f"↪️ Skipping irrelevant reply: {reply['subject']}")
        #             continue

        #         reply_context = f"""
        #         Sender: {reply['sender']}
        #         Subject: {reply['subject']}

        #         Body:
        #         {reply_text}
        #         """
        #         reply_prompt = template_prompt.replace("{email_text}", reply_context)

        #         response = client.messages.create(
        #             model="claude-haiku-4-5-20251001",
        #             max_tokens=2048,
        #             messages=[{"role": "user", "content": reply_prompt}]
        #         )
        #         reply_output = response.content[0].text.strip()
        #         reply_output = re.sub(r"^```(json)?", "", reply_output)
        #         reply_output = re.sub(r"```$", "", reply_output).strip()

        #         try:
        #             reply_data = json.loads(reply_output)
        #         except Exception as e:
        #             frappe.log_error(f"Reply JSON parse failed for {reply['name']}: {str(e)}", "Cab Booking Reply Error")
        #             continue

        #         updated = False
        #         for idx, row in enumerate(trip.table_lftf):
        #             booking = None
        #             for b in reply_data.get("bookings", []):
        #                 if (
        #                     b.get("passenger_name") == row.passenger_name
        #                     or b.get("booking_number") == row.booking_number
        #                 ):
        #                     booking = b
        #                     break

        #             if not booking:
        #                 continue

        #             fields_to_update = [
        #                 "pickup_location", "drop_location", "pickup_date", "pickup_time",
        #                 "drop_time", "reporting_time", "passenger_number"
        #             ]
        #             for f in fields_to_update:
        #                 val = booking.get(f)
        #                 if val and not row.get(f):
        #                     row.set(f, val)
        #                     updated = True

        #         if updated:
        #             trip.save(ignore_permissions=True)
        #             frappe.db.commit()
        #             print(f"✅ Trip {trip.name} updated with details from reply {reply['name']}")

        # except Exception as e:
        #     frappe.log_error(f"Reply update failed for {comm['name']}: {str(e)}", "Cab Booking - Reply Update")
        #     print(f"❌ Reply update failed: {str(e)}")  