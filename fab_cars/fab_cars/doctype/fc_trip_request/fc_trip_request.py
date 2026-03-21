import frappe
from frappe.model.document import Document


class FCTripRequest(Document):
	def autoname(self):
		"""
		Deterministic, collision-safe autonaming.

		`trip_name` is expected to already be a stable identifier coming from
		`FC Raw Email Log` (`FCR_<email_hash>`). We derive `FC Trip Request` name
		from it without any count-based logic (which is race-prone under concurrency).
		"""
		base_name = (getattr(self, "trip_name", None) or "").strip()
		if not base_name:
			base_name = "unknown"

		# Prefix/suffix are deterministic; ingestion idempotency should prevent collisions.
		self.name = f"{base_name}_TR"
