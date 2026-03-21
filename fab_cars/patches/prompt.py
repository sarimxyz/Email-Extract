import frappe


def set_default_fc_cab_settings_prompt():
	"""
	Ensure the singleton `FC Cab Settings` has the intended LLM extraction prompt.

	This runs as part of Frappe app patching (see `patches.txt`).
	"""

	cab_settings = frappe.get_single("FC Cab Settings")

	desired_prompt = '''You are a data extraction assistant. Given the plain text of an email, output ONLY a single valid JSON object (no preface, no comments, no markdown, no code fences).

You MUST return ALL required top-level keys exactly as listed below.

Required top-level JSON keys:
- summary (string or null)
- vehicle_type (string or null)
- city (string or null)
- miscellaneous_requirements (string or null)
- duty_type (string or null)
- request_type (string or null)
- special_request (string or null)
- remarks (string or null)
- notes (string or null)

- booked_by (object with keys: name, email, number)
- billed_to (object with keys: name, email, number)
- point_of_contact (object with keys: name, email, number)

- has_multiple_bookings (boolean)
- number_of_bookings (integer)
- bookings (array of booking objects)

CRITICAL rules:
1) `bookings` MUST be present and MUST contain at least ONE booking object, even if some fields are missing.
2) For any field you cannot determine, use null (not an empty string).
3) If seat count / passenger number is not mentioned, you may return passenger_number as null (the system will default it).
4) `booked_by` MUST be an object. If you can't find the user name or phone in the email, set those fields to null (so the system can ask for missing details).

Booking object schema (each element inside `bookings[]`):
- passenger_name (string or null)
- passenger_number (string or null)
- pickup_location (string or null)
- drop_location (string or null)
- pickup_date (string or null)
- pickup_time (string or null)
- drop_date (string or null)        // OPTIONAL: if not present, you can return null
- drop_time (string or null)        // OPTIONAL: if not present, you can return null
- reporting_time (string or null)
- passenger_specific_request (string or null)

Datetime rule:
- If the email mentions only ONE datetime (date+time or date-only), treat it as the pickup datetime and set drop_date/drop_time to null (the system will infer).

Phone rule:
- booked_by.number must be the phone number of the requester/passerby (string), or null if missing.

Output format:
Return a single JSON object that matches exactly the schema above.

Email text:
"""
{email_text}
"""

Return the JSON now.
'''

	current_prompt = cab_settings.prompt or ""
	# Only set when the stored prompt doesn't exactly match the intended template.
	# This keeps the extractor behavior stable across installs/upgrades.
	should_set = current_prompt.strip() != desired_prompt.strip()

	if should_set:
		cab_settings.prompt = desired_prompt
		cab_settings.save(ignore_permissions=True)
		frappe.db.commit()


def execute():
	set_default_fc_cab_settings_prompt()
