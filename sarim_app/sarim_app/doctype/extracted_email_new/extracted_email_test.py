import frappe
from bs4 import BeautifulSoup
from anthropic import Anthropic
import json

def process_received_emails_to_trip_requests():
    """
    1. Fetch all received emails from Communication
    2. Add them to Extracted Email New
    3. Extract trip data using Claude
    4. Create Trip Request docs automatically
    """
    # 1️⃣ Initialize Claude client
    api_key = frappe.local.conf.get("anthropic_api_key")
    client = Anthropic(api_key=api_key)

    # 2️⃣ Fetch all received emails
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
        # 3️⃣ Skip if already added
        existing = frappe.get_all(
            "Extracted Email New",
            filters={"source_email_id": comm["name"]},
            fields=["name"]
        )
        if existing:
            continue

        # 4️⃣ Clean email HTML
        plain_text = BeautifulSoup(comm["content"], "html.parser").get_text(separator="\n").strip()

        # 5️⃣ Add to Extracted Email New
        try:
            email_doc = frappe.get_doc({
                "doctype": "Extracted Email New",
                "source_email_id": comm["name"],
                "sender": comm["sender"],
                "subject": comm["subject"],
                "message_body": plain_text,
                "received_date": comm["creation"]
            })
            email_doc.insert()
            frappe.db.commit()
            print(f"Added email {comm['name']} to Extracted Email New")
        except Exception as ex:
            print(f"Failed to add email {comm['name']}: {ex}")
            continue

        # 6️⃣ Prepare Claude prompt
        prompt = f"""
Human:
You are an assistant that extracts trip booking information from emails.
Extract JSON with these keys: pickup_location, drop_location, pickup_date,
pickup_time, passenger_name, contact_number. Text:
---
{plain_text}
---
Return valid JSON only, no explanations.

Assistant:
"""

        # 7️⃣ Call Claude
        try:
            response = client.messages.create(
                model="claude-3-5-sonnet-20240620",
                max_tokens=200,
                messages=[{"role": "user", "content": prompt}]
            )
            ai_output = response.content[0].text.strip()
            print(f"Email: {comm['name']} -> AI Output: {ai_output}")

            # 8️⃣ Parse JSON
            try:
                data = json.loads(ai_output)
            except json.JSONDecodeError:
                print(f"Invalid JSON from Claude for email {comm['name']}")
                continue

            # 9️⃣ Insert into Trip Request
            try:
                trip = frappe.get_doc({
                    "doctype": "Trip Request",
                    "pickup_location": data.get("pickup_location") or "",
                    "drop_location": data.get("drop_location") or "",
                    "pickup_date": data.get("pickup_date") or "",
                    "pickup_time": data.get("pickup_time") or "",
                    "passenger_number": data.get("contact_number") or ""
                })
                trip.insert()
                frappe.db.commit()
                print(f"Trip Request created for email {comm['name']}")
            except Exception as ex:
                print(f"Failed to create Trip Request for email {comm['name']}: {ex}")

        except Exception as e:
            print(f"Claude API call failed for email {comm['name']}: {e}")
