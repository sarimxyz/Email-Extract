import frappe
from frappe.model.document import Document

class FC_BTW_Trip_Requests(Document):
    def autoname(self):
        # Use the base name field, not self.name
        base_name = getattr(self, "trip_name", None)
        if not base_name:
            base_name = "unknown"

        # Append _TR
        base_name = f"{base_name}_TR"

        # Count existing trips with same base
        existing_count = frappe.db.count(
            "FC_BTW_Trip_Requests",
            {"name": ["like", f"{base_name}%"]}
        )

        # Final name: add number if duplicates exist
        self.name = base_name if existing_count == 0 else f"{base_name}_{existing_count + 1}"


# class FC_BTW_Trip_Requests(Document):
# 	def autoname(self):
# 		sender = self.passenger_name or "unknown"
# 		date_obj = frappe.utils.get_datetime(self.pickup_date) if self.pickup_date else frappe.utils.now_datetime()
# 		timestamp = date_obj.strftime("%d-%m-%Y_%I-%M %p")

# 		base_name = f"{sender}_{timestamp}"
# 		existing_count = frappe.db.count(
# 			"FC_BTW_Trip_Requests",
# 			{"name": ["like", f"{base_name}%"]}
# 		)

# 		self.name = base_name if existing_count == 0 else f"{base_name}_{existing_count + 1}"

# class FC_BTW_Trip_Requests(Document):
#     def autoname(self):
#         # Use the extracted email name as base
#         base_name = getattr(self, "name", "unknown") + "_TR"

#         # Count existing trips with same base
#         existing_count = frappe.db.count(
#             "FC_BTW_Trip_Requests",
#             {"name": ["like", f"{base_name}%"]}
#         )

#         # Final name: add number if duplicates exist
#         self.name = base_name if existing_count == 0 else f"{base_name}_{existing_count + 1}"

# import frappe
# from frappe.model.document import Document

# class FC_BTW_Trip_Requests(Document):
#     def autoname(self):
#         """
#         Naming Convention:
#         Use same as Extracted Email base name (sender_dd-mm-yyyy_HH-MM AM/PM)
#         + suffix if multiple bookings exist.
#         """

#         # use the mail_link or ai_json_response to fetch the Extracted Email name
#         base_name = None

#         # If mail_link is set, fetch the linked extracted email
#         if self.mail_link:
#             extracted_email = frappe.db.get_value("FC_BTW_Extracted_Emails", self.mail_link, "name")
#             if extracted_email:
#                 base_name = extracted_email

#         # fallback if no mail_link or email found
#         if not base_name:
#             base_name = "unknown_" + frappe.utils.now_datetime().strftime("%d-%m-%Y_%I-%M %p")

#         # check if any trips exist with same base
#         existing_count = frappe.db.count(
#             "FC_BTW_Trip_Requests",
#             {"name": ["like", f"{base_name}%"]}
#         )

#         if existing_count == 0:
#             self.name = base_name
#         else:
#             self.name = f"{base_name}_{existing_count + 1}"
