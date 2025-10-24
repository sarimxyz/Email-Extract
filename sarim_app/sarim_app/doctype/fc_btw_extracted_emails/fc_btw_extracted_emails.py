# # Copyright (c) 2025, sarim and contributors
# # For license information, please see license.txt

# # import frappe
# from frappe.model.document import Document


# class FC_BTW_Extracted_Emails(Document):
# 	pass
# import frappe
# from bs4 import BeautifulSoup
# from anthropic import Anthropic
# import json

# def process_received_emails_to_trip_requests():
#     """
#     1. Fetch all received emails from Communication with subject 'cab booking'
#     2. Add them to Extracted Email New
#     3. Extract trip data using Claude
#     4. Create Trip Request docs automatically
#     5. Update Extracted Email New with status and error
#     """
# def autoname(self):
#         """
#         Naming convention: sender-email_YYYYMMDD_HHMMSS
#         """
#         sender = self.sender or "unknown"
#         # replace characters not allowed in names
#         sender_clean = sender.replace("@", "_at_").replace(".", "_dot_")
#         timestamp = self.received_date.strftime("%Y%m%d_%H%M%S")
#         self.name = f"{sender_clean}_{timestamp}"
#     # 1️⃣ Initialize Claude client
#     api_key = frappe.local.conf.get("anthropic_api_key")
#     client = Anthropic(api_key=api_key)

#     # 2️⃣ Fetch all received emails with subject containing 'cab booking'
#     communications = frappe.get_all(
#         "Communication",
#         filters={
#             "communication_type": "Communication",
#             "sent_or_received": "Received",
#             "subject": ["like", "%cab booking%"]
#         },
#         fields=["sender", "subject", "content", "creation", "name"]
#     )

#     for comm in communications:
#         # 3️⃣ Clean email HTML
#         plain_text = BeautifulSoup(comm["content"], "html.parser").get_text(separator="\n").strip()

#         exists = frappe.db.exists("FC_BTW_Extracted_Emails", {"source_email_id": comm["name"]})
#         if exists:
#             print(f"Email {comm['name']} already exists in Extracted Email New, skipping.")
#             continue

#         # 4️⃣ Add to FC_BTW_Extracted_Emails
#         try:
#             email_doc = frappe.get_doc({
#                 "doctype": "FC_BTW_Extracted_Emails",
#                 "source_email_id": comm["name"],
#                 "sender": comm["sender"],
#                 "subject": comm["subject"],
#                 "message_body": plain_text,
#                 "received_date": comm["creation"],
#                 "communication_link": comm["name"]
#             })
#             email_doc.insert()
#             frappe.db.commit()
#             print(f"Added email {comm['name']} to Extracted Email New")
#         except Exception as ex:
#             print(f"Failed to add email {comm['name']}: {ex}")
#             continue

#         # Fetch prompt from Cab Settings
#         cab_settings = frappe.get_single("FC_BTW_Cab_Settings")
#         template_prompt = cab_settings.prompt

#         # Replace placeholder {email_text} with actual email content
#         prompt = template_prompt.replace("{email_text}", plain_text)


#         # 6️⃣ Call Claude
#         try:
#             response = client.messages.create(
#                 model="claude-3-5-sonnet-20240620",
#                 max_tokens=200,
#                 messages=[{"role": "user", "content": prompt}]
#             )
#             ai_output = response.content[0].text.strip()
#             print(f"Email: {comm['name']} -> AI Output: {ai_output}")

#             # 7️⃣ Parse JSON
#             try:
#                 data = json.loads(ai_output)
#             except json.JSONDecodeError:
#                 print(f"Invalid JSON from Claude for email {comm['name']}")
#                 email_doc.trip_request_status = "Failed"
#                 email_doc.trip_request_error = "Invalid JSON from Claude"
#                 email_doc.save()
#                 frappe.db.commit()
#                 continue

#             # 8️⃣ Insert into Trip Request with proper error handling
#             try:
#                 trip = frappe.get_doc({
#                     "doctype": "FC_BTW_Trip_Requests",
#                     "pickup_location": data.get("pickup_location") or "",
#                     "drop_location": data.get("drop_location") or "",
#                     "pickup_date": data.get("pickup_date") or "",
#                     "pickup_time": data.get("pickup_time") or "",
#                     "passenger_number": data.get("contact_number") or "",
#                     "passenger_name": data.get("passenger_name") or "",
#                     "mail_link": comm["name"],
#                     "email_message_body": plain_text,
#     				"ai_json_response": ai_output
#                 })
#                 trip.insert()
#                 frappe.db.commit()

#                 # ✅ Update Extracted Email New
#                 email_doc.trip_request_status = "Success"
#                 email_doc.trip_request_error = ""
#                 email_doc.save()
#                 frappe.db.commit()

#                 print(f"Trip Request created for email {comm['name']}")

#             except Exception as ex:
#                 # ❌ Update Extracted Email New with failure
#                 email_doc.trip_request_status = "Failed"
#                 email_doc.trip_request_error = str(ex)
#                 email_doc.save()
#                 frappe.db.commit()

#                 print(f"Failed to create Trip Request for email {comm['name']}: {ex}")

#         except Exception as e:
#             print(f"Claude API call failed for email {comm['name']}: {e}")
#             email_doc.trip_request_status = "Failed"
#             email_doc.trip_request_error = f"Claude API call failed: {e}"
#             email_doc.save()
#             frappe.db.commit()

# Copyright (c) 2025, sarim and contributors
# For license information, please see license.txt

from frappe.model.document import Document
import frappe
from bs4 import BeautifulSoup
from anthropic import Anthropic
import json

class FC_BTW_Extracted_Emails(Document):
    def autoname(self):
        """
        Naming: sender_dd-mm-yyyy_HH-MM-SS
        """
        
        sender = self.sender or "unknown"
        # keep sender as-is
        timestamp = self.received_date.strftime("%d-%m-%Y_%I-%M %p")  # 12-hour format with AM/PM
        self.name = f"{sender}_{timestamp}"


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

    # 2️⃣ Fetch all received emails with subject containing 'cab booking'
    communications = frappe.get_all(
        "Communication",
        filters={
            "communication_type": "Communication",
            "sent_or_received": "Received",
            "subject": ["like", "%cab booking%"]
        },
        fields=["sender", "subject", "content", "creation", "name"]
    )

    for comm in communications:
        # 3️⃣ Clean email HTML
        plain_text = BeautifulSoup(comm["content"], "html.parser").get_text(separator="\n").strip()

        exists = frappe.db.exists("FC_BTW_Extracted_Emails", {"source_email_id": comm["name"]})
        if exists:
            print(f"Email {comm['name']} already exists, skipping.")
            continue

        # 4️⃣ Add to FC_BTW_Extracted_Emails
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
            # print(f"Added email {comm['name']} to Extracted Emails")
        except Exception as ex:
            # print(f"Failed to add email {comm['name']}: {ex}")
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
        base_name = email_doc.name  # sender_dd-mm-yyyy_HH-MM-SS

 
        # 8️⃣ Insert into Trip Request
        try:  
                trip = frappe.get_doc({
                    "doctype": "FC_BTW_Trip_Requests",
                    "trip_name":base_name,
                    # "pickup_location": data.get("pickup_location") or "",
                    # "drop_location": data.get("drop_location") or "",
                    # "pickup_date": data.get("pickup_date") or "",
                    # "pickup_time": data.get("pickup_time") or "",
                    # "reporting_time": data.get("reporting_time") or "",
                    "vehicle_type": data.get("vehicle_type") or "",
                    "city": data.get("city") or "",
                    "miscellaneous_requirements": data.get("miscellaneous_requirements") or "",
                    # "passenger_number": data.get("contact_number") or "",
                    # "passenger_name": data.get("passenger_name") or "",
                    "duty_type":data.get("duty_type") or "",
                    "request_type":data.get("request_type") or "",
                    "special_request":data.get("special_request") or "",
                    "remarks":data.get("remarks") or "",
                    "notes":data.get("notes") or "",
                    "mail_link": comm["name"],
                    "email_message_body": plain_text,
                    "ai_json_response": ai_output,
                    "ai_token_usage": total_tokens
                })

                bookings = data.get("bookings", [])
                if isinstance(bookings, dict):  # safety for single object
                    bookings = [bookings]

                for b in bookings:
                    trip.append("table_rtlw", {
                        "passenger_name": b.get("passenger_name") or "",
                        "passenger_number": b.get("passenger_number") or "",
                        "pickup_location": b.get("pickup_location") or "",
                        "drop_location": b.get("drop_location") or "",
                        "pickup_date": b.get("pickup_date") or "",
                        "pickup_time": b.get("pickup_time") or "",
                        "drop_time": b.get("drop_time") or ""
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
                print(f"Failed to create Trip Request for email {comm['name']}: {ex}")
