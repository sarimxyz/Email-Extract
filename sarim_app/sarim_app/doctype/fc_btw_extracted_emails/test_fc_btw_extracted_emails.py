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
