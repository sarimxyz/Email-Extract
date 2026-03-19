import frappe
from frappe.model.document import Document


class FCTripRequest(Document):
	def autoname(self):
		# Use the base name field, not self.name
		base_name = getattr(self, "trip_name", None)
		if not base_name:
			base_name = "unknown"

		# Append _TR
		base_name = f"{base_name}_TR"

		# Count existing trips with same base
		existing_count = frappe.db.count("FC Trip Request", {"name": ["like", f"{base_name}%"]})

		# Final name: add number if duplicates exist
		self.name = base_name if existing_count == 0 else f"{base_name}_{existing_count + 1}"
