# Copyright (c) 2026, fab_cars and contributors
# For license information, please see license.txt

import html as html_lib

import frappe

from fab_cars.fab_cars.email_ingestion.addresses import extract_sender_email
from fab_cars.fab_cars.email_ingestion.communication import (
	communication_name_for_sendmail_in_reply_to,
	ensure_stub_communication_for_parent_message,
)
from fab_cars.fab_cars.email_ingestion.message_ids import coerce_message_id_for_reply
from fab_cars.fab_cars.email_ingestion.payload import get_ingestion_settings


def send_missing_info_followup(
	*,
	to_sender: str,
	missing_fields: list[str],
	in_reply_to: str | None,
	original_subject: str | None,
	thread_root_token: str | None,
	plain_text_snippet: str | None = None,
) -> bool:
	settings = get_ingestion_settings()
	if not getattr(settings, "send_followup_email", 1):
		return False

	to_email = extract_sender_email(to_sender)
	if not to_email:
		return False

	custom_subject = getattr(settings, "followup_email_subject", None)
	base_subject = custom_subject or "Action needed: a few details for your Fab Cars booking"

	if in_reply_to and (original_subject or "").strip():
		subject = f"Re: {original_subject.strip()}"
	elif custom_subject:
		subject = custom_subject
	elif in_reply_to and base_subject and not str(base_subject).lower().startswith("re:"):
		subject = f"Re: {base_subject}"
	else:
		subject = base_subject

	missing_list = [f for f in (missing_fields or []) if f]
	missing_items_html = "".join(f"<li>{html_lib.escape(f)}</li>" for f in missing_list)
	detail_label = "detail" if len(missing_list) == 1 else "details"

	thread_root_html = ""
	if thread_root_token:
		thread_root_html = (
			f"<!-- FC-THREAD-ROOT:{thread_root_token} -->"
			f'<div style="display:none">FC-THREAD-ROOT:{thread_root_token}</div>'
		)

	message = (
		f"{thread_root_html}"
		'<div style="font-family:system-ui,-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;'
		'font-size:15px;line-height:1.5;color:#1f2937;max-width:560px;">'
		"<p>Hello,</p>"
		"<p>Thank you for contacting Fab Cars. To confirm your cab booking, we still need the following "
		f"{detail_label}:</p>"
		f'<ul style="margin:12px 0;padding-left:20px;">{missing_items_html}</ul>'
		"<p>Please <strong>reply to this email</strong> with the information above. "
		"Staying in the same thread helps us match your message to your request quickly.</p>"
		"<p>We will confirm your booking as soon as we have these details.</p>"
		"<p>Best regards,<br/>Fab Cars</p>"
		"</div>"
	)

	if in_reply_to:
		ensure_stub_communication_for_parent_message(
			parent_message_id=in_reply_to,
			subject=original_subject or base_subject,
			sender=to_sender,
			plain_text_snippet=plain_text_snippet or "",
		)
	communication_name = communication_name_for_sendmail_in_reply_to(in_reply_to)
	if in_reply_to and not communication_name:
		frappe.logger("fab_cars.email").info(
			"Missing-info follow-up: no Communication row for inbound Message-Id; "
			"outbound In-Reply-To cannot be set by Frappe. id=%s",
			in_reply_to,
		)

	parent_mid_for_hook = coerce_message_id_for_reply(in_reply_to)
	try:
		if parent_mid_for_hook:
			frappe.flags.fab_cars_thread_parent_message_id = parent_mid_for_hook
		frappe.sendmail(
			recipients=[to_email],
			subject=subject,
			message=message,
			in_reply_to=communication_name,
			email_headers={"X-FC-Thread-Root": thread_root_token} if thread_root_token else None,
		)
	finally:
		frappe.flags.pop("fab_cars_thread_parent_message_id", None)
	return True


def send_booking_confirmation(
	*,
	to_sender: str,
	trip_request_name: str,
	in_reply_to: str | None,
	original_subject: str | None,
	thread_root_token: str | None,
	plain_text_snippet: str | None = None,
) -> bool:
	"""Notify the customer in the same thread that their trip request was created successfully."""
	settings = get_ingestion_settings()
	if not getattr(settings, "send_booking_confirmation_email", 1):
		return False

	to_email = extract_sender_email(to_sender)
	if not to_email:
		return False

	trip_ref = (trip_request_name or "").strip()
	if not trip_ref:
		return False

	custom_subject = getattr(settings, "booking_confirmation_email_subject", None)
	base_subject = custom_subject or "Your Fab Cars booking is confirmed"

	if in_reply_to and (original_subject or "").strip():
		subject = f"Re: {original_subject.strip()}"
	elif custom_subject:
		subject = custom_subject
	elif in_reply_to and base_subject and not str(base_subject).lower().startswith("re:"):
		subject = f"Re: {base_subject}"
	else:
		subject = base_subject

	ref_html = html_lib.escape(trip_ref)
	thread_root_html = ""
	if thread_root_token:
		thread_root_html = (
			f"<!-- FC-THREAD-ROOT:{thread_root_token} -->"
			f'<div style="display:none">FC-THREAD-ROOT:{thread_root_token}</div>'
		)

	message = (
		f"{thread_root_html}"
		'<div style="font-family:system-ui,-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;'
		'font-size:15px;line-height:1.5;color:#1f2937;max-width:560px;">'
		"<p>Hello,</p>"
		"<p>Thank you for choosing Fab Cars. We have received your booking request and "
		"<strong>recorded it successfully</strong> in our system.</p>"
		f"<p>Your booking reference: <strong>{ref_html}</strong></p>"
		"<p>We will follow up with you if any additional details are needed.</p>"
		"<p>Best regards,<br/>Fab Cars</p>"
		"</div>"
	)

	if in_reply_to:
		ensure_stub_communication_for_parent_message(
			parent_message_id=in_reply_to,
			subject=original_subject or base_subject,
			sender=to_sender,
			plain_text_snippet=plain_text_snippet or "",
		)
	communication_name = communication_name_for_sendmail_in_reply_to(in_reply_to)
	if in_reply_to and not communication_name:
		frappe.logger("fab_cars.email").info(
			"Booking confirmation: no Communication row for inbound Message-Id; "
			"outbound In-Reply-To cannot be set by Frappe. id=%s",
			in_reply_to,
		)

	parent_mid_for_hook = coerce_message_id_for_reply(in_reply_to)
	try:
		if parent_mid_for_hook:
			frappe.flags.fab_cars_thread_parent_message_id = parent_mid_for_hook
		frappe.sendmail(
			recipients=[to_email],
			subject=subject,
			message=message,
			in_reply_to=communication_name,
			email_headers={"X-FC-Thread-Root": thread_root_token} if thread_root_token else None,
		)
	finally:
		frappe.flags.pop("fab_cars_thread_parent_message_id", None)
	return True
