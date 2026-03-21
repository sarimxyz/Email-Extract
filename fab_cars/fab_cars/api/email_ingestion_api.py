# Copyright (c) 2026, fab_cars and contributors
# For license information, please see license.txt

import frappe
from frappe.utils.user import get_system_managers

from fab_cars.fab_cars.doctype.fc_extracted_email.fc_extracted_email import (
	process_payload_to_trip_request,
	resolve_is_cab_booking_for_ingestion,
)
from fab_cars.fab_cars.email_ingestion.followup import send_missing_info_followup
from fab_cars.fab_cars.email_ingestion.ingest_flow import (
	effective_correlation_id,
	ensure_email_hash,
	load_or_create_raw_log_for_ingestion,
	resolve_thread_success_trip,
	retryable_ok_response,
)
from fab_cars.fab_cars.email_ingestion.payload import get_ingestion_max_attempts, validate_webhook_payload
from fab_cars.fab_cars.email_ingestion.raw_log_messages import parent_inbound_message_id_for_followup_reply
from fab_cars.fab_cars.email_ingestion.thread_plain_text import build_thread_plain_text_for_extraction
from fab_cars.fab_cars.email_ingestion.thread_resolution import resolve_merge_root


@frappe.whitelist(allow_guest=False)
def ingest_email(payload: dict) -> dict:
	"""Validate payload; for cab/taxi bookings upsert `FC Raw Email Log` and run extraction.

	Non-booking mail returns ``status: skipped`` without creating `FC Raw Email Log`.
	"""
	system_user = get_system_managers(only_name=True) or []
	frappe.set_user(system_user[0] if system_user else "Administrator")

	try:
		validated = validate_webhook_payload(payload)
	except Exception as e:
		frappe.throw(str(e))

	plain_text = validated["plain_text"]
	sender = validated["sender"]
	subject = validated["subject"]
	received_at_dt = validated["received_at_dt"]
	message_id = validated["message_id"]
	email_hash = validated["email_hash"]
	correlation_id = effective_correlation_id(validated)
	in_reply_to = validated.get("in_reply_to")
	references = validated.get("references")
	is_cab_booking = validated.get("is_cab_booking")
	max_attempts = get_ingestion_max_attempts()

	merge_root = resolve_merge_root(
		plain_text=plain_text,
		correlation_id=correlation_id,
		message_id=message_id,
		in_reply_to=in_reply_to,
		references=references,
		sender=sender,
		subject=subject,
	)

	thread_success_trip = resolve_thread_success_trip(
		correlation_id=correlation_id,
		merge_root=merge_root,
	)

	email_hash = ensure_email_hash(
		email_hash=email_hash,
		message_id=message_id,
		sender=sender,
		subject=subject,
		received_at_dt=received_at_dt,
		plain_text=plain_text,
	)

	raw_log_name = f"FCR_{email_hash}"

	# Classify only for *new* inbound messages. Skip when merging threads, when the thread
	# already completed elsewhere, or when a raw log already exists (retry / idempotency).
	apply_cab_gate = not (
		merge_root or thread_success_trip or frappe.db.exists("FC Raw Email Log", raw_log_name)
	)
	if apply_cab_gate and not resolve_is_cab_booking_for_ingestion(
		is_cab_booking=is_cab_booking,
		email_subject=subject,
		plain_text=plain_text,
		force_allow_without_classifier=False,
	):
		return {
			"status": "skipped",
			"raw_log": None,
			"trip_request": None,
			"retryable": False,
			"missing_fields": [],
		}

	raw_log, early, merged_into_thread = load_or_create_raw_log_for_ingestion(
		merge_root=merge_root,
		raw_log_name=raw_log_name,
		email_hash=email_hash,
		plain_text=plain_text,
		sender=sender,
		subject=subject,
		received_at_dt=received_at_dt,
		message_id=message_id,
		correlation_id=correlation_id,
		max_attempts=max_attempts,
	)
	if early:
		return early

	if raw_log.status == "Processing":
		return retryable_ok_response(raw_log)

	if thread_success_trip:
		raw_log.status = "Successful"
		raw_log.trip_request = thread_success_trip
		raw_log.last_error = None
		raw_log.save()
		frappe.db.commit()
		return {
			"status": "ok",
			"raw_log": raw_log.name,
			"trip_request": thread_success_trip,
			"retryable": False,
			"missing_fields": [],
		}

	thread_plain_text = build_thread_plain_text_for_extraction(
		correlation_id=raw_log.correlation_id,
		current_plain_text=None if merged_into_thread else plain_text,
	)

	result = process_payload_to_trip_request(
		plain_text=thread_plain_text,
		email_subject=subject,
		email_sender=sender,
		received_date=received_at_dt,
		source_message_id=message_id or email_hash,
		base_name=raw_log.name,
		extracted_email_doc=None,
		raw_email_log_doc=raw_log,
		mail_link_value=raw_log.name,
		is_cab_booking=True,
	)

	if result.get("status") == "needs_info":
		missing_fields = result.get("missing_fields") or []
		try:
			parent_message_id = parent_inbound_message_id_for_followup_reply(
				raw_log=raw_log,
				payload_message_id=message_id,
				payload_correlation_id=correlation_id,
			)

			thread_root_token = raw_log.name
			raw_log.correlation_id = thread_root_token
			raw_log.save()
			frappe.db.commit()

			send_missing_info_followup(
				to_sender=sender,
				missing_fields=missing_fields,
				in_reply_to=parent_message_id,
				original_subject=subject,
				thread_root_token=thread_root_token,
				plain_text_snippet=plain_text,
			)
		except Exception as e:
			frappe.log_error(
				(
					"Failed to send missing-info follow-up email.\n"
					f"To sender raw: {sender}\n"
					f"Missing fields: {missing_fields}\n"
					f"Error: {e}\n\n"
					f"{frappe.get_traceback()}"
				),
				"fab_cars email follow-up",
			)

	return {
		"status": result.get("status"),
		"raw_log": raw_log.name,
		"trip_request": result.get("trip_request"),
		"error": result.get("error"),
		"retryable": result.get("retryable", True),
		"missing_fields": result.get("missing_fields") or [],
	}


def reprocess_fc_raw_email_log(raw_log_name: str) -> dict:
	"""Re-run extraction for an existing `FC Raw Email Log`."""
	raw_log = frappe.get_doc("FC Raw Email Log", raw_log_name)

	thread_plain_text = build_thread_plain_text_for_extraction(
		correlation_id=raw_log.correlation_id,
		current_plain_text=None,
	)

	return process_payload_to_trip_request(
		plain_text=thread_plain_text,
		email_subject=raw_log.subject,
		email_sender=raw_log.sender,
		received_date=raw_log.received_at,
		source_message_id=raw_log.message_id or raw_log.email_hash,
		base_name=raw_log.name,
		extracted_email_doc=None,
		raw_email_log_doc=raw_log,
		mail_link_value=raw_log.name,
		is_cab_booking=True,
	)
