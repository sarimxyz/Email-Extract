# Copyright (c) 2026, fab_cars and contributors
# For license information, please see license.txt

import hashlib
import re
from datetime import timezone
from typing import Any

import frappe


def sha256_text(text: str) -> str:
	return hashlib.sha256(text.encode("utf-8")).hexdigest()


def normalize_ws(text: str) -> str:
	return re.sub(r"\s+", " ", (text or "")).strip().lower()


def _optional_str_field(payload: dict[str, Any], key: str) -> str | None:
	v = payload.get(key)
	if v is None:
		return None
	if not isinstance(v, str):
		raise ValueError(f"`{key}` must be a string when provided")
	return v


def compute_email_hash(
	*,
	message_id: str | None,
	sender: str,
	subject: str,
	received_at_dt,
	plain_text: str,
) -> str:
	if message_id:
		return sha256_text(str(message_id))

	canonical_plain = normalize_ws(plain_text)[:2000]
	canonical = (
		f"{normalize_ws(sender)}|{normalize_ws(subject)}|{received_at_dt.isoformat()}|{canonical_plain}"
	)
	return sha256_text(canonical)


def validate_webhook_payload(payload: dict[str, Any]) -> dict[str, Any]:
	"""Validate webhook payload shape strictly enough for safe persistence/extraction."""
	if not isinstance(payload, dict):
		raise ValueError("Payload must be a JSON object")

	plain_text = payload.get("plain_text")
	sender = payload.get("sender")
	subject = payload.get("subject")
	received_at = payload.get("received_at")

	if not isinstance(plain_text, str) or not plain_text.strip():
		raise ValueError("`plain_text` is required and must be a non-empty string")
	if sender is None or not isinstance(sender, str):
		raise ValueError("`sender` is required and must be a string")
	if subject is None or not isinstance(subject, str):
		raise ValueError("`subject` is required and must be a string")
	if received_at is None:
		raise ValueError("`received_at` is required")

	try:
		received_at_dt = frappe.utils.get_datetime(received_at)
	except Exception as e:
		raise ValueError("`received_at` must be a datetime/ISO string") from e

	if getattr(received_at_dt, "tzinfo", None) is not None:
		received_at_dt = received_at_dt.astimezone(timezone.utc).replace(tzinfo=None)

	message_id = _optional_str_field(payload, "message_id")
	email_hash = _optional_str_field(payload, "email_hash")
	correlation_id = _optional_str_field(payload, "correlation_id")
	in_reply_to = _optional_str_field(payload, "in_reply_to")
	references = _optional_str_field(payload, "references")

	is_cab_booking = payload.get("is_cab_booking")
	if is_cab_booking is not None and not isinstance(is_cab_booking, bool):
		raise ValueError("`is_cab_booking` must be a boolean when provided")

	return {
		"plain_text": plain_text,
		"sender": sender.strip(),
		"subject": subject.strip(),
		"received_at_dt": received_at_dt,
		"message_id": message_id,
		"email_hash": email_hash,
		"correlation_id": correlation_id,
		"in_reply_to": in_reply_to,
		"references": references,
		"is_cab_booking": is_cab_booking,
	}


def get_ingestion_max_attempts() -> int:
	if not frappe.db.exists("DocType", "FC Ingestion Settings"):
		raise ValueError("Missing DocType `FC Ingestion Settings`. Create it to configure ingestion retries.")

	settings = frappe.get_single("FC Ingestion Settings")
	amt = int(getattr(settings, "max_attempts", None) or 0)
	if amt < 1:
		raise ValueError("`FC Ingestion Settings.max_attempts` must be >= 1")
	return amt


def get_ingestion_settings():
	if not frappe.db.exists("DocType", "FC Ingestion Settings"):
		raise ValueError("Missing DocType `FC Ingestion Settings`. Create it to configure ingestion retries.")
	return frappe.get_single("FC Ingestion Settings")
