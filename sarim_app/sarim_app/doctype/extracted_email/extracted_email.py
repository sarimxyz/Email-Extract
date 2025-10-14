# 1

# # Copyright (c) 2025, sarim and contributors
# # For license information, please see license.txt

# # import frappe
# from frappe.model.document import Document

# from bs4 import BeautifulSoup
# import frappe
# class ExtractedEmail(Document):

# 	def extract_emails_scheduler():
# 		"""
# 		Scheduler function to extract emails from Communication
# 		and insert into Extracted Email doctype
# 		"""
# 		emails = frappe.get_all(
# 			"Communication",
# 			filters={
# 				"communication_type": "Communication",
# 				"sent_or_received": "Received"
# 			},
# 			fields=["sender", "subject", "content", "creation", "name"]
# 		)

# 		for e in emails:
# 			exists = frappe.db.exists("Extracted Email", {"source_email_id": e.name})
# 			if not exists:
# 				# Clean HTML to plain text
# 				plain_text = BeautifulSoup(e.content, "html.parser").get_text(separator="\n")
				
# 				doc = frappe.get_doc({
# 					"doctype": "Extracted Email",
# 					"sender": e.sender,
# 					"subject": e.subject,
# 					"message_body": plain_text,
# 					"received_date": e.creation,
# 					"source_email_id": e.name
# 				})
# 				doc.insert(ignore_permissions=True)
# 				frappe.logger().info(f"Extracted Email: {e.subject}")
# 			else:
# 				frappe.logger().info(f"Already exists: {e.subject}")

# 		frappe.db.commit()
# 2nd working immediate last
# from frappe.model.document import Document
# from bs4 import BeautifulSoup
# import frappe

# class ExtractedEmail(Document):
#     pass  # Controller for Doctype

# def extract_emails_scheduler():
#     """
#     Scheduler function to extract emails from Communication
#     and insert into Extracted Email doctype
#     """
#     emails = frappe.get_all(
#         "Communication",
#         filters={
#             "communication_type": "Communication",
#             "sent_or_received": "Received"
#         },
#         fields=["sender", "subject", "content", "creation", "name"]
#     )

#     for e in emails:
#         exists = frappe.db.exists("Extracted Email", {"source_email_id": e['name']})
#         if not exists:
#             plain_text = BeautifulSoup(e['content'], "html.parser").get_text(separator="\n")
            
#             doc = frappe.get_doc({
#                 "doctype": "Extracted Email",
#                 "sender": e['sender'],
#                 "subject": e['subject'],
#                 "message_body": plain_text,
#                 "received_date": e['creation'],
#                 "source_email_id": e['name']
#             })
#             doc.insert(ignore_permissions=True)
#             print(f"Extracted Email: {e['subject']}")
#         else:
#             print(f"Already exists: {e['subject']}")

#     frappe.db.commit()

# 2

#     from frappe.model.document import Document
# from bs4 import BeautifulSoup
# import frappe
# import json
# import openai  # install via pip install openai

# class ExtractedEmail(Document):
#     pass  # Controller for Doctype


# def extract_emails_scheduler():
#     """
#     Scheduler function to extract emails from Communication
#     and insert into Extracted Email + AI-parsed Doctype
#     """
#     emails = frappe.get_all(
#         "Communication",
#         filters={
#             "communication_type": "Communication",
#             "sent_or_received": "Received"
#         },
#         fields=["sender", "subject", "content", "creation", "name"]
#     )

#     for e in emails:
#         exists = frappe.db.exists("Extracted Email", {"source_email_id": e['name']})
#         if exists:
#             print(f"Already exists: {e['subject']}")
#             continue

#         # Extract plain text from HTML
#         plain_text = BeautifulSoup(e['content'], "html.parser").get_text(separator="\n")

#         # Step 1: Create Extracted Email record
#         extracted_email = frappe.get_doc({
#             "doctype": "Extracted Email",
#             "sender": e['sender'],
#             "subject": e['subject'],
#             "message_body": plain_text,
#             "received_date": e['creation'],
#             "source_email_id": e['name']
#         })
#         extracted_email.insert(ignore_permissions=True)
#         print(f"Extracted Email: {e['subject']}")

#         # Step 2: AI Extraction (You can skip if not needed)
#         try:
#             prompt = f"""
#             Extract the following structured details from this email text:
#             ---
#             {plain_text}
#             ---
#             Required fields (return as JSON only):
#             - pickup_location
#             - drop_location
#             - pickup_date
#             - pickup_time
#             - passenger_name
#             - contact_number
#             """

#             # Call OpenAI or any other model
#             response = openai.ChatCompletion.create(
#                 model="gpt-4o-mini",  # can use gpt-4-turbo or gpt-3.5-turbo
#                 messages=[{"role": "user", "content": prompt}],
#             )

#             ai_output = response["choices"][0]["message"]["content"]

#             # Try parsing JSON response
#             try:
#                 extracted_data = json.loads(ai_output)
#             except json.JSONDecodeError:
#                 frappe.log_error(f"AI output not valid JSON: {ai_output}", "AI Extraction Error")
#                 extracted_data = {}

#             # Step 3: Insert into Trip Request / Booking Request Doctype
#             if extracted_data:
#                 trip_doc = frappe.get_doc({
#                     "doctype": "Trip Request",  # change to your Doctype name
#                     "pickup_location": extracted_data.get("pickup_location"),
#                     "drop_location": extracted_data.get("drop_location"),
#                     "pickup_date": extracted_data.get("pickup_date"),
#                     "pickup_time": extracted_data.get("pickup_time"),
#                     "passenger_name": extracted_data.get("passenger_name"),
#                     "contact_number": extracted_data.get("contact_number"),
#                     "email_reference": e['name'],
#                 })
#                 trip_doc.insert(ignore_permissions=True)
#                 print(f"Trip Request created for email: {e['subject']}")
#             else:
#                 print(f"No data extracted from: {e['subject']}")

#         except Exception as err:
#             frappe.log_error(f"AI extraction failed: {str(err)}", "Extract Email Scheduler")

#     frappe.db.commit()

# 3 Trip request AI

from frappe.model.document import Document
from bs4 import BeautifulSoup
import frappe
import json
import openai

class ExtractedEmail(Document):
    pass


def extract_emails_scheduler():
    """
    Scheduler function to extract emails from Communication
    and insert into Extracted Email + Trip Request (AI extracted)
    """
    # get your API key from site_config.json
    openai.api_key = frappe.local.conf.get("openai_api_key")

    emails = frappe.get_all(
        "Communication",
        filters={
            "communication_type": "Communication",
            "sent_or_received": "Received"
        },
        fields=["sender", "subject", "content", "creation", "name"]
    )

    for e in emails:
        # exists = frappe.db.exists("Extracted Email", {"source_email_id": e['name']})
        # if exists:
        #     print(f"Already exists: {e['subject']}")
        #     continue

        plain_text = BeautifulSoup(e['content'], "html.parser").get_text(separator="\n")

        # 1️⃣ Insert into Extracted Email
        extracted_email = frappe.get_doc({
            "doctype": "Extracted Email New",
            "sender": e['sender'],
            "subject": e['subject'],
            "message_body": plain_text,
            "received_date": e['creation'],
            "source_email_id": e['name']
        })
        extracted_email.insert(ignore_permissions=True)
        # print(f"Extracted Email saved: {e['subject']}")

        # 2️⃣ Call AI for structured extraction
        try:
            prompt = f"""
            You are an assistant that extracts trip booking information from emails.
            From the text below, extract JSON with these keys:
            pickup_location, drop_location, pickup_date, pickup_time, passenger_name, contact_number.
            Text:
            ---
            {plain_text}
            ---
            Return valid JSON only, no explanations.
            """

            # response = openai.ChatCompletion.create(
            #     model="gpt-4o-mini",
            #     messages=[{"role": "user", "content": prompt}],
            # )
            print("=== AI Prompt ===")
            print(prompt)
            response = openai.ChatCompletion.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
            )
            print("=== AI Response ===")
            print(response)

            ai_output = response["choices"][0]["message"]["content"].strip()
            print(ai_output)
            try:
                extracted_data = json.loads(ai_output)
            except json.JSONDecodeError:
                frappe.log_error(f"Invalid AI output:\n{ai_output}", "AI Extraction Error")
                extracted_data = {}

            if extracted_data:
                # 3️⃣ Create Trip Request (subject as name)
                trip_doc = frappe.get_doc({
                    "doctype": "Trip Request",
                    "name": e["subject"],  # 👈 set subject as the name/id
                    "pickup_location": extracted_data.get("pickup_location"),
                    "drop_location": extracted_data.get("drop_location"),
                    "pickup_date": extracted_data.get("pickup_date"),
                    "pickup_time": extracted_data.get("pickup_time"),
                    "passenger_name": extracted_data.get("passenger_name"),
                    "contact_number": extracted_data.get("contact_number"),
                    "email_reference": e["name"],
                })
                trip_doc.insert(ignore_permissions=True)
                print(f"Trip Request created: {e['subject']}")
            else:
                print(f"No structured data found in: {e['subject']}")

        except Exception as err:
            frappe.log_error(f"AI extraction failed: {str(err)}", "Extract Email Scheduler")

    frappe.db.commit()

