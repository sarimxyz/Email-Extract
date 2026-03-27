# Copyright (c) 2026, fab_cars and contributors
# For license information, please see license.txt

import html as html_lib

import frappe

from fab_cars.fab_cars.email_ingestion.addresses import extract_sender_email
from fab_cars.fab_cars.email_ingestion.message_ids import coerce_message_id_for_reply, strip_angle_brackets


def communication_name_for_sendmail_in_reply_to(message_id_or_comm_name: str | None) -> str | None:
	"""
	Resolve the value for `frappe.sendmail(..., in_reply_to=...)`: a `Communication.name`.

	See Frappe `EmailQueue.prepare_email_content`: `in_reply_to` must be a Communication row name.
	"""
	if not message_id_or_comm_name:
		return None

	raw = str(message_id_or_comm_name).strip()
	if not raw:
		return None

	if frappe.db.exists("Communication", raw):
		return raw

	variants: list[str] = [raw]
	stripped = strip_angle_brackets(raw)
	if stripped and stripped not in variants:
		variants.append(stripped)
	if stripped:
		bracketed = f"<{stripped}>"
		if bracketed not in variants:
			variants.append(bracketed)

	names = frappe.get_all(
		"Communication",
		filters={"communication_medium": "Email", "message_id": ["in", variants]},
		pluck="name",
		order_by="creation desc",
		limit_page_length=1,
	)
	return names[0] if names else None


def message_id_stripped_for_communication_db(parent_message_id: str | None) -> str | None:
	"""Frappe stores `Communication.message_id` without angle brackets (see `receive.py`)."""
	if not parent_message_id:
		return None
	coerced = coerce_message_id_for_reply(str(parent_message_id).strip())
	if not coerced:
		return None
	stripped = strip_angle_brackets(coerced)
	return stripped.strip() if stripped else None


def ensure_stub_communication_for_parent_message(
	*,
	parent_message_id: str | None,
	subject: str,
	sender: str,
	plain_text_snippet: str,
) -> str | None:
	"""
	Create a minimal Received Communication for the customer's Message-ID when missing,
	so Frappe can set outbound In-Reply-To from `Communication.message_id`.
	"""
	stripped = message_id_stripped_for_communication_db(parent_message_id)
	if not stripped:
		return None

	coerced = coerce_message_id_for_reply(stripped) or f"<{stripped}>"
	existing = communication_name_for_sendmail_in_reply_to(coerced)
	if existing:
		return existing

	found = frappe.db.get_value(
		"Communication",
		{"communication_medium": "Email", "message_id": stripped},
		"name",
	)
	if found:
		return found

	sender_email = extract_sender_email(sender or "") or (sender or "").strip()[:255]
	subj = (subject or "Inbound email")[:900]
	snippet = (plain_text_snippet or "")[:8000]

	try:
		comm = frappe.get_doc(
			{
				"doctype": "Communication",
				"subject": subj,
				"communication_medium": "Email",
				"communication_type": "Communication",
				"sent_or_received": "Received",
				"status": "Open",
				"sender": sender_email,
				"content": f"<pre>{html_lib.escape(snippet)}</pre>",
				"message_id": stripped,
			}
		)
		comm.insert(ignore_permissions=True)
		return comm.name
	except Exception:
		frappe.log_error(frappe.get_traceback(), "fab_cars stub Communication for threading")
		return frappe.db.get_value(
			"Communication",
			{"communication_medium": "Email", "message_id": stripped},
			"name",
		)
