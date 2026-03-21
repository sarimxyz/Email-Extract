# Copyright (c) 2026, fab_cars and contributors
# For license information, please see license.txt

"""Gate ingestion for Communication-driven sync: historical mail vs new mail + idempotency."""

from datetime import datetime, timezone

import frappe
from frappe.model.document import Document

from fab_cars.fab_cars.email_ingestion.message_ids import find_raw_log_name_for_message_id


def _to_utc_naive(dt: datetime | None) -> datetime | None:
	if dt is None:
		return None
	if getattr(dt, "tzinfo", None) is not None:
		return dt.astimezone(timezone.utc).replace(tzinfo=None)
	return dt


def communication_received_at_utc(doc: Document) -> datetime | None:
	"""Prefer `communication_date` (email Date / Frappe), then `creation` as fallback."""
	raw = doc.get("communication_date") or doc.get("creation")
	if not raw:
		return None
	try:
		dt = frappe.utils.get_datetime(raw)
	except Exception:
		return None
	return _to_utc_naive(dt)


def should_enqueue_ingestion_for_communication(doc: Document) -> bool:
	"""
	Return False when this inbound Communication must not trigger `ingest_email`.

	- No cutoff on Email Account (legacy): allow.
	- Email received time <= cutoff: skip (historical / initial sync batch).
	- Message-ID already present on an FC Raw Email Log: skip (idempotency).
	"""
	email_account = (doc.get("email_account") or "").strip()
	if not email_account:
		return True

	if not frappe.db.has_column("Email Account", "initial_sync_completed_at"):
		return True

	cutoff_raw = frappe.db.get_value("Email Account", email_account, "initial_sync_completed_at")
	if not cutoff_raw:
		return True

	cutoff_dt = _to_utc_naive(frappe.utils.get_datetime(cutoff_raw))
	if not cutoff_dt:
		return True

	received_dt = communication_received_at_utc(doc)
	if received_dt is None:
		return False

	if received_dt <= cutoff_dt:
		return False

	mid = (doc.get("message_id") or "").strip()
	if mid and find_raw_log_name_for_message_id(mid):
		return False

	return True
