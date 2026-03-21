# Copyright (c) 2026, fab_cars and contributors
# For license information, please see license.txt

from __future__ import annotations

import re
from typing import Optional

import frappe
from frappe.core.utils import html2text
from frappe.model.document import Document
from frappe.utils.user import get_system_managers


def _get_system_user() -> str:
	"""Pick a user with permissions to write internal ingestion doctypes."""
	users = get_system_managers(only_name=True) or []
	return users[0] if users else "Administrator"


def _normalize_plain_text(text: str) -> str:
	text = (text or "").strip()
	# Collapse horizontal whitespace, but keep newlines structure mostly intact.
	text = re.sub(r"[ \t]+", " ", text)
	text = re.sub(r"\n{3,}", "\n\n", text)
	return text.strip()


def _strip_angle_brackets(value: str | None) -> str | None:
	if not value:
		return None
	v = str(value).strip()
	if v.startswith("<") and v.endswith(">") and len(v) >= 3:
		return v[1:-1].strip()
	return v


def _message_id_variants(message_id: str | None) -> list[str]:
	"""
	Message-ids may be stored with or without angle brackets depending on source.
	We try both to make parent lookup resilient.
	"""
	if not message_id:
		return []
	v = str(message_id).strip()
	if not v:
		return []
	variants = {v}
	stripped = _strip_angle_brackets(v)
	if stripped and stripped != v:
		variants.add(stripped)
		variants.add(f"<{stripped}>")
	return list(variants)


def _strip_quoted_reply_plaintext(text: str) -> str:
	"""
	Remove common quoted-reply separators to keep extraction focused on what
	the user actually wrote in each email.
	"""
	if not text:
		return text
	separator_patterns = [
		r"(?im)^\s*On .+ wrote:\s*$",
		r"(?im)^\s*-----Original Message-----\s*$",
		r"(?im)^\s*From:\s*.+$",
	]
	min_idx = None
	for pat in separator_patterns:
		m = re.search(pat, text)
		if not m:
			continue
		idx = m.start()
		min_idx = idx if min_idx is None else min(min_idx, idx)
	if min_idx is None:
		return text.strip()
	return text[:min_idx].strip()


def _communication_to_plain_text(communication: Document) -> str:
	plain = html2text(communication.get("content") or "")
	plain = _normalize_plain_text(plain)
	if plain:
		return plain
	return _normalize_plain_text(communication.get("text_content") or "")


def _build_thread_plain_text_from_communication(
	current_communication: Document,
	current_plain_text: str,
	*,
	max_hops: int = 5,
) -> str:
	"""
	Build extraction context by prepending parent `Communication` records
	(using `in_reply_to`).

	In Frappe inbound-email receiving, `Communication.in_reply_to` is typically
	set to the parent Communication's `name` (not the parent email's `message_id`).
	This function supports both cases:
	- if `in_reply_to` matches an existing Communication name -> fetch by name
	- otherwise -> treat it as a message-id and fetch by `Communication.message_id`
	"""
	parent_ref = current_communication.get("in_reply_to")
	if not parent_ref:
		return current_plain_text

	parts: list[str] = []
	visited: set[str] = set()
	hops = 0

	while parent_ref and hops < max_hops:
		# Resolve parent by Communication.name first (most common in Frappe).
		rows = frappe.get_all(
			"Communication",
			filters={"name": parent_ref},
			fields=["name", "sent_or_received", "in_reply_to", "message_id", "content", "text_content"],
			limit_page_length=1,
		)
		if not rows:
			# Fallback: treat in_reply_to as a message-id.
			parent_variants = _message_id_variants(parent_ref)
			if not parent_variants:
				break

			rows = frappe.get_all(
				"Communication",
				filters={
					"communication_medium": "Email",
					"message_id": ["in", parent_variants],
				},
				fields=[
					"name",
					"sent_or_received",
					"in_reply_to",
					"message_id",
					"content",
					"text_content",
				],
				order_by="creation DESC",
				limit_page_length=1,
			)
		if not rows:
			break

		parent = rows[0]
		parent_name = parent.get("name") or ""
		if not parent_name or parent_name in visited:
			break
		visited.add(parent_name)

		# Only append bodies from user-sent emails (Received).
		# We still follow Sent messages via `in_reply_to` so we can reach the
		# original booking, but we don't add our own follow-up template text.
		if (parent.get("sent_or_received") or "") == "Received":
			parent_text = _communication_to_plain_text(parent)  # type: ignore[arg-type]
			if parent_text:
				parts.append(parent_text)

		parent_ref = parent.get("in_reply_to")
		hops += 1

	if not parts:
		return current_plain_text

	# parts is built from nearest parent -> farthest. Reverse to get root -> current.
	parts.reverse()
	# Strip quoted separators only from the *current* reply so we focus on what
	# the user newly provided, while still keeping parent context unmodified.
	current_txt = _strip_quoted_reply_plaintext(current_plain_text or "")
	if current_txt:
		parts.append(current_txt)
	return "\n\n---\n\n".join(parts)


def _heuristic_is_cab_booking(*, subject: str, plain_text: str) -> bool | None:
	"""
	Quick keyword gate to reduce expensive LLM calls.

	Returns:
	- True: strongly looks like cab/taxi/vehicle booking
	- False: clearly not a cab booking (we should skip classifier)
	- None: ambiguous -> fall back to LLM classifier
	"""
	blob = f"{subject or ''}\n{plain_text or ''}".lower()

	positive_keywords = [
		"cab",
		"taxi",
		"vehicle",
		"car",
		"chauffeur",
		"pickup",
		"pick-up",
		"drop",
		"dropoff",
		"airport",
		"trip",
		"booking",
		"travel",
	]
	negative_keywords = [
		"otp",
		"one-time password",
		"password",
		"reset",
		"verification code",
		"newsletter",
		"marketing",
		"promotion",
		"invoice",
		"payment",
		"receipt",
		"unsubscribe",
		"welcome",
	]

	looks_positive = any(k in blob for k in positive_keywords)
	looks_negative = any(k in blob for k in negative_keywords)

	# If there's strong evidence it's not a booking, skip.
	if looks_negative and not looks_positive:
		return False

	# If we find any booking intent keywords, we can avoid the classifier.
	if looks_positive:
		return True

	return None


def _communication_to_payload(
	*,
	communication: Document,
	is_cab_booking: bool | None,
	plain_text_override: str | None = None,
) -> dict:
	"""
	Build a payload compatible with `fab_cars.fab_cars.api.email_ingestion_api.ingest_email`.
	"""
	plain_text = plain_text_override
	if plain_text is None:
		plain_text = html2text(communication.get("content") or "")
		plain_text = _normalize_plain_text(plain_text)

	# Fallback: Frappe already parsed a plain text version during receiving.
	if not plain_text:
		plain_text = _normalize_plain_text(communication.get("text_content") or "")

	subject = (communication.get("subject") or "").strip()
	sender = (communication.get("sender") or communication.get("sender_full_name") or "").strip()

	received_at = (
		communication.get("communication_date") or communication.get("creation") or frappe.utils.now()
	)

	message_id = communication.get("message_id") or None
	token_match = re.search(r"FC-THREAD-ROOT\s*[:=]\s*([^\s<>,;]+)", plain_text or "", flags=re.IGNORECASE)
	correlation_id = (
		(token_match.group(1).strip() if token_match else None)
		or communication.get("in_reply_to")
		or message_id
	)

	return {
		"plain_text": plain_text,
		"sender": sender,
		"subject": subject,
		"received_at": received_at,
		"message_id": message_id,
		"correlation_id": correlation_id,
		"is_cab_booking": is_cab_booking,
	}


def enqueue_ingestion_from_communication(doc: Document, method: str | None = None) -> None:
	"""
	Frappe hook: when a new inbound email is stored as `Communication`, enqueue extraction.
	"""
	try:
		if (doc.get("communication_medium") or "") != "Email":
			return
		if (doc.get("sent_or_received") or "") != "Received":
			return

		# Convert to plain text early, so heuristic can avoid unnecessary LLM calls.
		plain_text = html2text(doc.get("content") or "")
		plain_text = _normalize_plain_text(plain_text)
		if not plain_text:
			plain_text = _normalize_plain_text(doc.get("text_content") or "")

		# For replies, include parent email context so the user doesn't need to
		# resend details already provided in the earlier message.
		plain_text = _build_thread_plain_text_from_communication(
			current_communication=doc,
			current_plain_text=plain_text,
		)

		subject = (doc.get("subject") or "").strip()
		sender = (doc.get("sender") or doc.get("sender_full_name") or "").strip()
		if not sender or not subject or not plain_text:
			# Can't extract reliably; let the record be created later from proper webhook payloads.
			return

		is_cab_booking = _heuristic_is_cab_booking(subject=subject, plain_text=plain_text)

		payload = _communication_to_payload(
			communication=doc,
			is_cab_booking=is_cab_booking,
			plain_text_override=plain_text,
		)
		# Enqueue ingestion. The ingestion worker will set the correct user.
		frappe.enqueue(
			"fab_cars.fab_cars.api.email_ingestion_api.ingest_email",
			queue="short",
			enqueue_after_commit=True,
			payload=payload,
		)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "fab_cars - communication enqueue ingestion")


def fast_pull_emails() -> None:
	"""
	Faster email syncing than Frappe's default cadence.

	Runs within the scheduler; it will pull enabled Email Accounts.
	"""
	from frappe.email.doctype.email_account.email_account import pull

	# Match the plan requirement: pull immediately (now=True) for faster syncing.
	pull(now=True)


def retry_failed_ingestions(max_records: int = 25) -> None:
	"""
	Retries LLM/extraction failures stored in `FC Raw Email Log`.
	"""
	system_user = _get_system_user()
	frappe.set_user(system_user)

	settings = frappe.get_single("FC Ingestion Settings")
	max_attempts = int(getattr(settings, "max_attempts", None) or 0)
	if max_attempts < 1:
		return

	failed_logs = frappe.get_all(
		"FC Raw Email Log",
		filters={"status": "Failed"},
		fields=[
			"name",
			"attempt_count",
			"plain_text",
			"sender",
			"subject",
			"received_at",
			"message_id",
			"email_hash",
			"correlation_id",
		],
		order_by="received_at desc, name desc",
		limit_page_length=max_records,
	)

	for log in failed_logs:
		attempt_count = int(log.get("attempt_count") or 0)
		if attempt_count >= max_attempts:
			continue

		payload = {
			"plain_text": log.get("plain_text") or "",
			"sender": log.get("sender") or "",
			"subject": log.get("subject") or "",
			"received_at": log.get("received_at"),
			"message_id": log.get("message_id"),
			"email_hash": log.get("email_hash"),
			"correlation_id": log.get("correlation_id"),
			# Let the pipeline decide classification/extraction again.
			"is_cab_booking": None,
		}

		# Deduplicate enqueued retries to avoid overlapping scheduler runs.
		frappe.enqueue(
			"fab_cars.fab_cars.api.email_ingestion_api.ingest_email",
			queue="short",
			enqueue_after_commit=True,
			payload=payload,
			job_id=f"fab_cars_retry|{log.name}",
			deduplicate=True,
		)
