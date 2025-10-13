# Copyright (c) 2025, sarim and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document

from bs4 import BeautifulSoup
import frappe
class ExtractedEmail(Document):

	def extract_emails_scheduler():
		"""
		Scheduler function to extract emails from Communication
		and insert into Extracted Email doctype
		"""
		emails = frappe.get_all(
			"Communication",
			filters={
				"communication_type": "Communication",
				"sent_or_received": "Received"
			},
			fields=["sender", "subject", "content", "creation", "name"]
		)

		for e in emails:
			exists = frappe.db.exists("Extracted Email", {"source_email_id": e.name})
			if not exists:
				# Clean HTML to plain text
				plain_text = BeautifulSoup(e.content, "html.parser").get_text(separator="\n")
				
				doc = frappe.get_doc({
					"doctype": "Extracted Email",
					"sender": e.sender,
					"subject": e.subject,
					"message_body": plain_text,
					"received_date": e.creation,
					"source_email_id": e.name
				})
				doc.insert(ignore_permissions=True)
				frappe.logger().info(f"Extracted Email: {e.subject}")
			else:
				frappe.logger().info(f"Already exists: {e.subject}")

		frappe.db.commit()
