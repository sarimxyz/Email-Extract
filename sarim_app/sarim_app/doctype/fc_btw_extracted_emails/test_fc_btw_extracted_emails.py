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
