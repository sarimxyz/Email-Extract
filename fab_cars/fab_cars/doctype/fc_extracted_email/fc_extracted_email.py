# Copyright (c) 2025, sarim and contributors
# For license information, please see license.txt

import json
import re
from typing import Any

import frappe
from frappe.model.document import Document

from fab_cars.fab_cars.llm.llm_client import get_default_llm_models, llm_invoke_text


class FCExtractedEmail(Document):
	def autoname(self):
		sender = (self.sender or "unknown").strip()
		# Frappe does not allow special characters '<' and '>' in document names.
		# Sender strings often come in the RFC-5322 style: `Name <email@example.com>`.
		sender = re.sub(r"[<>]", "", sender).strip()
		if not sender:
			sender = "unknown"
		received = getattr(self, "received_date", None)
		if received:
			if hasattr(received, "strftime"):
				timestamp = received.strftime("%d-%m-%Y_%I-%M %p")
			else:
				try:
					received_dt = frappe.utils.get_datetime(received)
					timestamp = received_dt.strftime("%d-%m-%Y_%I-%M %p")
				except Exception:
					timestamp = frappe.utils.now_datetime().strftime("%d-%m-%Y_%I-%M %p")
		else:
			timestamp = frappe.utils.now_datetime().strftime("%d-%m-%Y_%I-%M %p")

		base_name = f"{sender}_{timestamp}"

		existing_count = frappe.db.count("FC Extracted Email", {"name": ["like", f"{base_name}%"]})

		self.name = base_name if existing_count == 0 else f"{base_name}_{existing_count + 1}"


def _build_email_content(email_subject: str, plain_text: str) -> str:
	return f"Subject: {email_subject}\n\n{plain_text}"


def _parse_llm_json_object(text: str) -> dict:
	candidate = (text or "").strip()

	candidate = re.sub(r"```[a-zA-Z]*", "", candidate)
	candidate = candidate.replace("```", "").strip()

	start = candidate.find("{")
	end = candidate.rfind("}")
	if start != -1 and end != -1 and end > start:
		candidate = candidate[start : end + 1]

	try:
		return json.loads(candidate)
	except json.JSONDecodeError:
		m = re.search(r"\{.*\}", candidate, flags=re.DOTALL)
		if not m:
			raise
		return json.loads(m.group(0))


def _call_llm_classifier(*, email_subject: str, plain_text: str) -> bool:
	"""Return True if email is (likely) a cab/taxi/vehicle booking request."""
	email_content = _build_email_content(email_subject, plain_text)

	validation_prompt = f"""
You are an expert email classifier for identifying CAB / TAXI / VEHICLE BOOKING related emails.

Your job: Analyze the following email and decide if it is related to any CAB BOOKING, TAXI BOOKING, VEHICLE BOOKING, or TRAVEL REQUEST.

Email:
{email_content}

IMPORTANT RULES:
- Return ONLY a raw JSON object. No markdown, no text, no code blocks.
- Format:
{{"is_cab_booking": true or false, "reason": "short explanation"}}

CLASSIFY AS TRUE (cab booking) IF email contains **any** of the following:
- Mentions of cab, taxi, vehicle, car, trip, chauffeur, airport pickup/drop, etc.
- Passenger names, pickup/drop locations, travel date or time.
- Booking confirmation, request for cab, or trip details.
- Vendor or company sending cab booking confirmations.
- Attachments or booking details even if short.

CLASSIFY AS FALSE (not cab booking) IF:
- It's OTP, marketing, newsletter, or unrelated service mail.
- It's about invoices, password resets, or welcome messages.

⚠️ Even if the email looks partially like a booking (e.g., “Request for vehicle” or “trip details”), still mark TRUE.
Be lenient — better to classify possibly true than to miss one.

Return result strictly as JSON:
{{"is_cab_booking": true, "reason": "mentions pickup and drop details"}}
"""

	models = get_default_llm_models()
	result = llm_invoke_text(
		prompt=validation_prompt,
		model=models["classifier"],
		max_tokens=1024,
	)

	validation_data = _parse_llm_json_object(result.text)
	return bool(validation_data.get("is_cab_booking", False))


def _entity_field(data: dict, key: str) -> dict:
	val = data.get(key)
	return val if isinstance(val, dict) else {}


def _truthy_value(v: Any) -> bool:
	# Treat empty strings / None as missing; accept numbers too.
	if v is None:
		return False
	s = str(v).strip()
	return bool(s)


def _missing_required_booking_fields(*, bookings: list[dict], booked_by: dict) -> list[str]:
	"""
	Return missing required fields as user-friendly labels.

	Required (per your intake requirements):
	- Pickup location
	- Drop location
	- Pickup date + time
	- User name + phone
	- Notes are optional
	- For multiple bookings: required fields must be present for *all* bookings
	"""

	# Stable order of labels for the follow-up email.
	label_order = [
		"Name",
		"Phone number",
		"Pickup location",
		"Drop location",
		"Pickup date",
		"Pickup time",
	]

	missing = set()

	if not _truthy_value(booked_by.get("name")):
		missing.add("Name")
	if not _truthy_value(booked_by.get("number")):
		missing.add("Phone number")

	for b in bookings:
		if not _truthy_value(b.get("pickup_location")):
			missing.add("Pickup location")
		if not _truthy_value(b.get("drop_location")):
			missing.add("Drop location")
		if not _truthy_value(b.get("pickup_date")):
			missing.add("Pickup date")
		if not _truthy_value(b.get("pickup_time")):
			missing.add("Pickup time")

	return [l for l in label_order if l in missing]


def _extract_sender_email_and_name(sender: str) -> tuple[str | None, str | None]:
	"""
	Extract best-effort (email, display_name) from common formats:
	- `user@example.com`
	- `User Name <user@example.com>`
	"""
	if not sender:
		return None, None

	s = sender.strip()
	if not s:
		return None, None

	# Common pattern: "Name <email@example.com>"
	if "<" in s and ">" in s:
		email_part = s.split("<", 1)[1].split(">", 1)[0].strip()
		name_part = s.split("<", 1)[0].strip().strip('"').strip("'")
		if email_part and "@" in email_part:
			return email_part, name_part or None

	# Fallback: if it's directly an email address.
	if "@" in s and " " not in s:
		return s, None

	# Best-effort name from the local-part.
	if "@" in s:
		email_like = s if "@" in s else None
		if email_like and email_like.count("@") == 1 and email_like.split("@", 1)[1]:
			name_guess = email_like.split("@", 1)[0]
			name_guess = name_guess.replace(".", " ").replace("_", " ").strip() or None
			return email_like, name_guess

	return None, None


def _derive_drop_fields_from_pickup(bookings: list[dict]) -> None:
	"""
	Fill missing drop date/time using pickup datetime.

	Rules:
	- If drop date is missing -> default to pickup date.
	- If drop time is missing -> default to pickup time.
	- If both are missing -> assume same as pickup.

	Note: There is no duration estimation logic in the current codebase,
	so drop time falls back to pickup time when not explicitly provided.
	"""

	for b in bookings:
		# If the LLM omitted drop date/time, infer them from pickup.
		if not _truthy_value(b.get("drop_date")) and _truthy_value(b.get("pickup_date")):
			b["drop_date"] = b.get("pickup_date")

		if not _truthy_value(b.get("drop_time")) and _truthy_value(b.get("pickup_time")):
			b["drop_time"] = b.get("pickup_time")


# Must match `fab_cars.fab_cars.api.email_ingestion_api` thread merge separator (avoid import cycles).
_THREAD_PLAIN_TEXT_SEP = "\n\n---\n\n"


def _merge_entity_dicts_latest_wins(*entities: dict) -> dict:
	"""Later dicts override earlier ones for the same key when the new value is non-empty."""
	out: dict = {}
	for e in entities:
		if not isinstance(e, dict):
			continue
		for k, v in e.items():
			if _truthy_value(v):
				out[k] = v
	return out


def _merge_booking_lists_by_index(*booking_lists: list) -> list[dict]:
	normalized: list[list[dict]] = []
	for bl in booking_lists:
		if isinstance(bl, dict):
			bl = [bl]
		if not isinstance(bl, list):
			bl = []
		normalized.append(bl)
	max_n = max((len(b) for b in normalized), default=0)
	merged: list[dict] = []
	for i in range(max_n):
		chain = []
		for bl in normalized:
			if i < len(bl) and isinstance(bl[i], dict):
				chain.append(bl[i])
		merged.append(_merge_entity_dicts_latest_wins(*chain))
	return merged


def _merge_extraction_payloads(*payloads: dict) -> dict:
	"""
	Merge multiple extractor JSON payloads (oldest → newest). Later non-empty values win.
	"""
	if not payloads:
		return {}
	if len(payloads) == 1:
		return payloads[0]

	merged_top: dict = {}
	for p in payloads:
		if not isinstance(p, dict):
			continue
		for k, v in p.items():
			if k in ("bookings", "booked_by", "billed_to", "point_of_contact"):
				continue
			if _truthy_value(v):
				merged_top[k] = v

	booked_by = _merge_entity_dicts_latest_wins(
		*[_entity_field(p, "booked_by") for p in payloads if isinstance(p, dict)]
	)
	billed_to = _merge_entity_dicts_latest_wins(
		*[_entity_field(p, "billed_to") for p in payloads if isinstance(p, dict)]
	)
	poc = _merge_entity_dicts_latest_wins(
		*[_entity_field(p, "point_of_contact") for p in payloads if isinstance(p, dict)]
	)

	booking_lists = []
	for p in payloads:
		if not isinstance(p, dict):
			continue
		b = p.get("bookings")
		if isinstance(b, dict):
			b = [b]
		if isinstance(b, list):
			booking_lists.append(b)

	merged_bookings = _merge_booking_lists_by_index(*booking_lists) if booking_lists else []

	return {
		**merged_top,
		"booked_by": booked_by,
		"billed_to": billed_to,
		"point_of_contact": poc,
		"bookings": merged_bookings,
	}


def _split_thread_plain_text_segments(plain_text: str) -> list[str]:
	if not (plain_text or "").strip():
		return []
	if _THREAD_PLAIN_TEXT_SEP not in plain_text:
		return [plain_text.strip()]
	parts = plain_text.split(_THREAD_PLAIN_TEXT_SEP)
	return [p.strip() for p in parts if p.strip()]


def _normalize_seat_count(value: Any) -> str:
	"""
	Seats are represented by `passenger_number` in the extracted booking JSON.

	Rule:
	- If the user did not mention seat count/passengers, default to 1.
	- If a value is present, extract the first integer (e.g. "2 seats" -> "2").
	"""
	if value is None:
		return "1"
	if isinstance(value, int):
		return str(value)
	s = str(value).strip()
	if not s:
		return "1"
	m = re.search(r"\d+", s)
	return m.group(0) if m else "1"


def _build_extractor_prompt(*, plain_text: str, cab_settings) -> str:
	template_prompt = cab_settings.prompt or ""
	if "{email_text}" not in template_prompt:
		raise ValueError(
			"FC Cab Settings.prompt must include the placeholder `{email_text}` for the message body"
		)
	thread_hint = ""
	if _THREAD_PLAIN_TEXT_SEP in (plain_text or ""):
		thread_hint = (
			"The input may contain MULTIPLE messages separated by blank lines and '---'. "
			"Treat them as ONE email thread in chronological order (oldest first). "
			"Merge information across all parts; when the same field appears more than once, "
			"prefer the MOST RECENT (latest) non-empty value.\n\n"
		)
	prompt = template_prompt.replace("{email_text}", thread_hint + plain_text)
	drop_optional_instruction = (
		"Drop date and time are optional. If not explicitly mentioned, infer them from pickup datetime "
		"or leave them equal to pickup."
	)
	one_datetime_as_pickup_instruction = (
		"If the user mentions only one datetime, treat it as the pickup date/time and infer the drop "
		"date/time from the pickup date/time."
	)
	if drop_optional_instruction not in prompt:
		prompt = f"{prompt}\n\n{drop_optional_instruction}\n{one_datetime_as_pickup_instruction}"
	return prompt


def _invoke_extractor_llm(*, prompt: str) -> tuple[dict, str, int]:
	models = get_default_llm_models()
	llm_result = llm_invoke_text(
		prompt=prompt,
		model=models["extractor"],
		max_tokens=4096,
	)
	ai_output = llm_result.text
	total_tokens = llm_result.total_tokens or 0

	try:
		data = _parse_llm_json_object(ai_output)
	except json.JSONDecodeError:
		strict_retry_prompt = (
			f"{prompt}\n\n"
			"STRICT OUTPUT REQUIREMENTS:\n"
			"- Output ONLY a single valid JSON object.\n"
			"- Do NOT include any preface, commentary, markdown, or code fences.\n"
			"- Use double quotes for all keys/strings.\n"
			"- Ensure the JSON is parseable by standard JSON parsers.\n"
		)
		retry_result = llm_invoke_text(
			prompt=strict_retry_prompt,
			model=models["extractor"],
			max_tokens=4096,
		)
		ai_output = retry_result.text
		total_tokens += retry_result.total_tokens or 0
		data = _parse_llm_json_object(ai_output)

	if not isinstance(data, dict):
		raise ValueError("LLM extraction must return a JSON object")
	return data, ai_output, total_tokens


def _normalize_and_validate_booking_payload(data: dict) -> tuple[list[dict], dict, dict, dict]:
	bookings = data.get("bookings")
	if bookings is None:
		raise ValueError("LLM extraction missing required field `bookings`")
	if isinstance(bookings, dict):
		bookings = [bookings]
	if not isinstance(bookings, list):
		raise ValueError("`bookings` must be a list of booking objects")
	if len(bookings) == 0:
		raise ValueError("`bookings` must contain at least one booking")
	for idx, b in enumerate(bookings):
		if not isinstance(b, dict):
			raise ValueError(f"Booking at index {idx} must be an object")

	for b in bookings:
		b["passenger_number"] = _normalize_seat_count(b.get("passenger_number"))

	_derive_drop_fields_from_pickup(bookings)

	booked_by = _entity_field(data, "booked_by")
	billed_to = _entity_field(data, "billed_to")
	poc = _entity_field(data, "point_of_contact")
	return bookings, booked_by, billed_to, poc


def process_payload_to_trip_request(
	*,
	plain_text: str,
	email_subject: str,
	email_sender: str,
	received_date,
	source_message_id: str,
	base_name: str,
	extracted_email_doc: Document | None = None,
	raw_email_log_doc: Document | None = None,
	mail_link_value: str | None = None,
	is_cab_booking: bool | None = None,
) -> dict:
	try:
		if is_cab_booking is None:
			is_cab_booking = _call_llm_classifier(
				email_subject=email_subject,
				plain_text=plain_text,
			)

		if not is_cab_booking:
			if raw_email_log_doc is not None:
				raw_email_log_doc.status = "Skipped"
				raw_email_log_doc.save()
				frappe.db.commit()
			if extracted_email_doc is not None:
				extracted_email_doc.trip_request_status = "Failed"
				extracted_email_doc.trip_request_error = "Not a cab/taxi/vehicle booking email"
				extracted_email_doc.save()
				frappe.db.commit()
			return {"status": "skipped"}

		cab_settings = frappe.get_single("FC Cab Settings")
		prompt = _build_extractor_prompt(plain_text=plain_text, cab_settings=cab_settings)
		data, ai_output, total_tokens = _invoke_extractor_llm(prompt=prompt)

		bookings, booked_by, billed_to, poc = _normalize_and_validate_booking_payload(data)

		# Sender fallback: used when LLM doesn't provide POC/booker email/name.
		sender_email, sender_name = _extract_sender_email_and_name(email_sender)

		missing_required = _missing_required_booking_fields(bookings=bookings, booked_by=booked_by)
		segments = _split_thread_plain_text_segments(plain_text)
		if missing_required and len(segments) > 1:
			segment_payloads: list[dict] = []
			segment_outputs: list[str] = []
			for seg in segments:
				seg_prompt = _build_extractor_prompt(plain_text=seg, cab_settings=cab_settings)
				seg_data, seg_ai, seg_tok = _invoke_extractor_llm(prompt=seg_prompt)
				total_tokens += seg_tok
				segment_payloads.append(seg_data)
				segment_outputs.append(seg_ai or "")
			merged = _merge_extraction_payloads(data, *segment_payloads)
			data = merged
			ai_output = "\n\n--- segment merge ---\n\n".join(
				[ai_output, *segment_outputs],
			)
			bookings, booked_by, billed_to, poc = _normalize_and_validate_booking_payload(data)
			missing_required = _missing_required_booking_fields(bookings=bookings, booked_by=booked_by)

		if missing_required:
			reason = "Missing required booking details: " + ", ".join(missing_required)
			if extracted_email_doc is not None:
				extracted_email_doc.trip_request_status = "Needs Info"
				extracted_email_doc.trip_request_error = reason
				extracted_email_doc.save()
				frappe.db.commit()
			if raw_email_log_doc is not None:
				raw_email_log_doc.status = "Needs Info"
				raw_email_log_doc.last_error = reason
				raw_email_log_doc.save()
				frappe.db.commit()
			return {
				"status": "needs_info",
				"missing_fields": missing_required,
				"retryable": False,
			}

		if extracted_email_doc is not None:
			extracted_email_doc.has_multiple_bookings = data.get("has_multiple_bookings", False)
			extracted_email_doc.number_of_bookings = data.get("number_of_bookings", 0)
			extracted_email_doc.save()
			frappe.db.commit()

		# Fill missing contact fields from the sender (email + best-effort name).
		booked_by_email = booked_by.get("email") or sender_email or ""
		booked_by_name = booked_by.get("name") or sender_name or ""
		booked_by_number = booked_by.get("number") or ""

		poc_name = poc.get("name") or sender_name or booked_by_name or ""
		poc_number = poc.get("number") or booked_by_number or ""
		poc_email = poc.get("email") or sender_email or booked_by_email or ""

		trip_summary = data.get("trip_summary") or data.get("summary") or ""

		trip_payload = {
			"doctype": "FC Trip Request",
			"trip_name": base_name,
			"summary": trip_summary,
			"required_vehicle_type": data.get("vehicle_type") or "",
			"city": data.get("city") or "",
			"miscellaneous_requirements": data.get("miscellaneous_requirements") or "",
			"duty_type": data.get("duty_type") or "",
			"request_type": data.get("request_type") or "",
			"special_request": data.get("special_request") or "",
			"remarks": data.get("remarks") or "",
			"notes": data.get("notes") or "",
			"booked_by_name": booked_by_name,
			"booked_by_email": booked_by_email,
			"booked_by_number": booked_by_number,
			"billed_to_name": billed_to.get("name") or "",
			"billed_to_email": billed_to.get("email") or "",
			"billed_to_number": billed_to.get("number") or "",
			"poc_name": poc_name,
			"poc_email": poc_email,
			"poc_number": poc_number,
			"email_message_body": plain_text,
			"ai_json_response": ai_output,
			"ai_token_usage": total_tokens,
		}
		if mail_link_value:
			trip_payload["mail_link"] = mail_link_value

		trip = frappe.get_doc(trip_payload)
		for b in bookings:
			trip.append(
				"table_lftf",
				{
					"passenger_name": b.get("passenger_name") or "",
					"passenger_number": b.get("passenger_number") or "",
					"pickup_location": b.get("pickup_location") or "",
					"drop_location": b.get("drop_location") or "",
					"pickup_date": b.get("pickup_date") or "",
					"pickup_time": b.get("pickup_time") or "",
					"drop_date": b.get("drop_date") or "",
					"drop_time": b.get("drop_time") or "",
					"reporting_time": b.get("reporting_time") or "",
					# Child doctype field is `passenger_special_request`.
					"passenger_special_request": b.get("passenger_special_request")
					or b.get("passenger_specific_request")
					or "",
				},
			)

		trip.insert()
		frappe.db.commit()

		if extracted_email_doc is not None:
			extracted_email_doc.trip_request_status = "Successful"
			extracted_email_doc.trip_request_error = ""
			extracted_email_doc.save()
			frappe.db.commit()

		if raw_email_log_doc is not None:
			raw_email_log_doc.status = "Successful"
			raw_email_log_doc.trip_request = trip.name
			raw_email_log_doc.save()
			frappe.db.commit()

		return {"status": "ok", "trip_request": trip.name}

	except json.JSONDecodeError as e:
		return _payload_failure(
			e,
			extracted_email_doc=extracted_email_doc,
			raw_email_log_doc=raw_email_log_doc,
			retryable=True,
		)
	except ValueError as e:
		return _payload_failure(
			e,
			extracted_email_doc=extracted_email_doc,
			raw_email_log_doc=raw_email_log_doc,
			retryable=False,
		)
	except Exception as e:
		return _payload_failure(
			e,
			extracted_email_doc=extracted_email_doc,
			raw_email_log_doc=raw_email_log_doc,
			retryable=True,
		)


def _payload_failure(
	e: Exception,
	*,
	extracted_email_doc: Document | None,
	raw_email_log_doc: Document | None,
	retryable: bool,
) -> dict:
	err = str(e)
	if extracted_email_doc is not None:
		extracted_email_doc.trip_request_status = "Failed"
		extracted_email_doc.trip_request_error = err
		extracted_email_doc.save()
		frappe.db.commit()
	if raw_email_log_doc is not None:
		raw_email_log_doc.status = "Failed"
		raw_email_log_doc.last_error = err
		raw_email_log_doc.save()
		frappe.db.commit()
	return {"status": "failed", "error": err, "retryable": retryable}
