# Copyright (c) 2025, sarim and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document
from bs4 import BeautifulSoup
from anthropic import Anthropic
import frappe
import json

class ExtractedEmailNew(Document):
	pass
# def extract_emails_scheduler():

	
 
# 1️⃣ Initialize Claude client
api_key = frappe.local.conf.get("anthropic_api_key")
client = Anthropic(api_key=api_key)

def extract_emails_scheduler():

    emails = frappe.get_all(
        "Communication",
        filters={
            "communication_type": "Communication",
            "sent_or_received": "Received"
        },
        fields=["sender", "subject", "content", "creation", "name"]
    )

    for e in emails:
        # 3️⃣ Convert HTML to plain text
        plain_text = BeautifulSoup(e['content'], "html.parser").get_text(separator="\n")

        # 4️⃣ Skip if already extracted
        if frappe.db.exists("Extracted Email New", {"source_email_id": e['name']}):
            print(f"Already processed: {e['subject']}")
            continue

        # 5️⃣ Insert into Extracted Email New
        extracted_email = frappe.get_doc({
            "doctype": "Extracted Email New",
            "sender": e['sender'],
            "subject": e['subject'],
            "message_body": plain_text,
            "received_date": e['creation'],
            "source_email_id": e['name']
        })
        extracted_email.insert(ignore_permissions=True)

        # 6️⃣ Prepare Claude prompt
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

        # 7️⃣ Call Claude
        try:
            response = client.messages.create(
                model="claude-3-5-sonnet-20240620",
                max_tokens=200,
                messages=[{"role": "user", "content": prompt}]
            )

            ai_output = response.content[0].text.strip()

            try:
                extracted_data = json.loads(ai_output)
            except json.JSONDecodeError:
                frappe.log_error(f"Invalid Claude output:\n{ai_output}", "AI Extraction Error")
                extracted_data = {}

            # 8️⃣ Create Trip Request if data exists
            if extracted_data:
                # avoid duplicates by subject or source_email_id
                if not frappe.db.exists("Trip Request", {"email_reference": e["name"]}):
                    trip_doc = frappe.get_doc({
                        "doctype": "Trip Request",
                        # "name": e["subject"],  # subject as docname
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
                    print(f"Trip Request already exists: {e['subject']}")
            else:
                print(f"No structured data found in: {e['subject']}")

        except Exception as err:
            frappe.log_error(f"Claude extraction failed: {str(err)}", "Extract Email Scheduler")

    frappe.db.commit()
    print("All emails processed.")


    ## single mail id extraction 

    # from frappe.model.document import Document
# import frappe
# from anthropic import Anthropic
# import json
# 
# 1️⃣ Claude client
# api_key = frappe.local.conf.get("anthropic_api_key")
# client = Anthropic(api_key=api_key)
# 
# 2️⃣ Specific email id
# source_email_id = "b0p5lrnh1t"
# 
# 3️⃣ Fetch the email from Extracted Email New
# try:
    # email_doc = frappe.get_doc("Extracted Email New", source_email_id)
# except frappe.DoesNotExistError:
    # print(f"No email found with source_email_id: {source_email_id}")
    # email_doc = None
# 
# if email_doc:
    # plain_text = email_doc.message_body
# 
    # 4️⃣ Prepare prompt
    # prompt = f"""
    # You are an assistant that extracts trip booking information from emails.
    # Extract JSON with these keys: pickup_location, drop_location, pickup_date,
    # pickup_time, passenger_name, contact_number. Text:
    # ---
    # {plain_text}
    # ---
    # Return valid JSON only, no explanations.
    # """
# 
    # 5️⃣ Call Claude
    # try:
        # response = client.messages.create(
            # model="claude-3-5-sonnet-20240620",
            # max_tokens=200,
            # messages=[{"role": "user", "content": prompt}]
        # )
# 
        # ai_output = response.content[0].text.strip()
        # print("AI Extraction Output:", ai_output)
# 
        # 6️⃣ Optional: parse JSON to validate
        # try:
            # extracted_data = json.loads(ai_output)
            # print("Parsed Data:", extracted_data)
        # except json.JSONDecodeError:
            # print("Invalid JSON returned by Claude.")
# 
    # except Exception as e:
        # print("Claude API call failed:", e)
# 


	
