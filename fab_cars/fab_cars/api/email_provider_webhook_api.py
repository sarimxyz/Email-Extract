# Copyright (c) 2026, fab_cars and contributors
# For license information, please see license.txt

import os
from typing import Any

import frappe

from fab_cars.fab_cars.api.email_ingestion_api import ingest_email
from fab_cars.fab_cars.email_ingestion_service import webhook_server as webhook_adapter


def _maybe_verify_webhook() -> None:
	"""
	Optional shared-secret verification for public webhook endpoints.

	This mirrors `WEBHOOK_SHARED_SECRET` behavior in `webhook_server.py`,
	but runs inside Frappe (no separate process needed in production).
	"""

	shared_secret = os.environ.get("WEBHOOK_SHARED_SECRET")
	if not shared_secret:
		return

	# Header lookup is case-insensitive in most WSGI stacks, but we try common variants.
	incoming = (frappe.request.headers or {}).get("X-FC-Webhook-Token") or (frappe.request.headers or {}).get(
		"x-fc-webhook-token"
	)
	if not incoming or incoming != shared_secret:
		raise PermissionError("Invalid webhook token")


def _to_frappe_ingest_payload(*, ingest_payload: dict[str, Any]) -> dict[str, Any]:
	plain_text = ingest_payload.get("plain_text") or ""
	if not isinstance(plain_text, str) or not plain_text.strip():
		raise ValueError("No plain text extracted from incoming email")

	# Keep this shape aligned with `webhook_server.py`.
	return {
		"message_id": ingest_payload.get("message_id"),
		"sender": ingest_payload.get("sender") or "",
		"subject": ingest_payload.get("subject") or "",
		"received_at": ingest_payload.get("received_at"),
		"plain_text": plain_text,
		# Optional correlation hint for idempotency/debugging.
		"correlation_id": ingest_payload.get("correlation_id") or ingest_payload.get("message_id") or None,
		"in_reply_to": ingest_payload.get("in_reply_to") or None,
		"references": ingest_payload.get("references") or None,
	}


def _run_provider_webhook(
	extract_payload: Any,
	payload: dict[str, Any],
	*,
	log_title: str,
) -> dict[str, Any]:
	try:
		_maybe_verify_webhook()
		ingest_payload = extract_payload(payload or {})
		req_payload = _to_frappe_ingest_payload(ingest_payload=ingest_payload)
		result = ingest_email(req_payload)
		return {"ok": True, "result": result}
	except Exception as e:
		frappe.log_error(str(e), log_title)
		return {"ok": False, "error": str(e)}


@frappe.whitelist(allow_guest=True)
def healthz() -> dict[str, Any]:
	return {"ok": True}


@frappe.whitelist(allow_guest=True)
def sendgrid_webhook(payload: dict[str, Any]) -> dict[str, Any]:
	"""
	SendGrid webhook adapter.

	Production behavior: this runs inside your existing Frappe web workers,
	so you do NOT need to keep `webhook_server.py` running as a separate daemon.
	"""

	return _run_provider_webhook(
		webhook_adapter._extract_sendgrid_payload,
		payload,
		log_title="fab_cars sendgrid webhook",
	)


@frappe.whitelist(allow_guest=True)
def gmail_webhook(payload: dict[str, Any]) -> dict[str, Any]:
	"""
	Gmail Pub/Sub push webhook adapter.

	Notes:
	- If your provider only sends headers/metadata, you must enable upstream raw MIME passthrough
	  (or provide `plain_text`) so extraction can proceed.
	"""

	return _run_provider_webhook(
		webhook_adapter._extract_gmail_payload,
		payload,
		log_title="fab_cars gmail webhook",
	)
