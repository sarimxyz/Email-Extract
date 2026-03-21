# Copyright (c) 2026, fab_cars and contributors
# For license information, please see license.txt

"""Orchestration helpers for `ingest_email` (raw log upsert + thread trip hints)."""

from typing import Any

import frappe

from fab_cars.fab_cars.email_ingestion.payload import compute_email_hash
from fab_cars.fab_cars.email_ingestion.raw_log_messages import (
	incoming_message_already_recorded,
	record_ingested_message_id,
)
from fab_cars.fab_cars.email_ingestion.thread_plain_text import merge_plain_text_segments


def _ok_trip_response(raw_log) -> dict:
	return {"status": "ok", "raw_log": raw_log.name, "trip_request": raw_log.get("trip_request")}


def retryable_ok_response(raw_log) -> dict:
	"""Standard webhook body when ingestion is deferred or still running."""
	return {
		"status": "ok",
		"raw_log": raw_log.name,
		"trip_request": raw_log.get("trip_request"),
		"retryable": True,
		"missing_fields": [],
	}


def _failed_max_attempts(raw_log, *, with_retryable_flag: bool) -> dict:
	out = {
		"status": "failed",
		"raw_log": raw_log.name,
		"trip_request": raw_log.get("trip_request"),
		"error": raw_log.last_error or "Max ingestion attempts exceeded",
	}
	if with_retryable_flag:
		out["retryable"] = False
	return out


def effective_correlation_id(validated: dict[str, Any]) -> str | None:
	return validated.get("correlation_id") or validated.get("email_hash") or validated.get("message_id")


def resolve_thread_success_trip(*, correlation_id: str | None, merge_root: str | None) -> str | None:
	"""If the thread already completed successfully elsewhere, return that `FC Trip Request` name."""
	thread_success_trip = None
	if correlation_id:
		thread_success_trip = frappe.db.get_value(
			"FC Raw Email Log",
			{"correlation_id": correlation_id, "status": "Successful"},
			"trip_request",
		)

	if merge_root:
		ts_merge = frappe.db.get_value(
			"FC Raw Email Log",
			merge_root,
			["status", "trip_request"],
			as_dict=True,
		)
		if ts_merge and ts_merge.get("status") == "Successful" and ts_merge.get("trip_request"):
			thread_success_trip = ts_merge.get("trip_request")

	return thread_success_trip


def ensure_email_hash(
	*,
	email_hash: str | None,
	message_id: str | None,
	sender: str,
	subject: str,
	received_at_dt,
	plain_text: str,
) -> str:
	if email_hash:
		return email_hash
	return compute_email_hash(
		message_id=message_id,
		sender=sender,
		subject=subject,
		received_at_dt=received_at_dt,
		plain_text=plain_text,
	)


def try_mark_trip_from_existing_link(raw_log) -> dict | None:
	"""If a trip already points at this raw log name, mark Successful and return response dict."""
	existing_trip = frappe.db.get_value("FC Trip Request", {"trip_name": raw_log.name}, "name")
	if not existing_trip:
		return None
	raw_log.status = "Successful"
	raw_log.trip_request = existing_trip
	raw_log.last_error = None
	raw_log.save()
	frappe.db.commit()
	return _ok_trip_response(raw_log)


def merge_reply_into_raw_log(
	raw_log,
	*,
	plain_text: str,
	sender: str,
	subject: str,
	received_at_dt,
	message_id: str | None,
	correlation_id: str | None,
	max_attempts: int,
) -> tuple[dict | None, bool]:
	"""
	Apply an inbound reply merged into `merge_root`. Returns (early_response_dict, merged_ok).

	When `early_response_dict` is not None, caller should return it immediately.
	"""
	if raw_log.status == "Successful" and raw_log.get("trip_request"):
		return _ok_trip_response(raw_log), False

	if incoming_message_already_recorded(raw_log, message_id):
		return retryable_ok_response(raw_log), False

	early = try_mark_trip_from_existing_link(raw_log)
	if early:
		return early, False

	if raw_log.status == "Failed" and (raw_log.attempt_count or 0) >= max_attempts:
		return _failed_max_attempts(raw_log, with_retryable_flag=True), False

	if raw_log.status == "Processing":
		raw_log.last_error = None
		raw_log.save()
		frappe.db.commit()
		return retryable_ok_response(raw_log), False

	prev_mid = (raw_log.get("message_id") or "").strip()
	raw_log.plain_text = merge_plain_text_segments(raw_log.plain_text, plain_text)
	record_ingested_message_id(raw_log, message_id)
	if message_id:
		raw_log.message_id = message_id
	if not raw_log.get("thread_root_message_id"):
		raw_log.thread_root_message_id = prev_mid or (message_id or None)
	raw_log.sender = sender
	raw_log.subject = subject
	raw_log.received_at = received_at_dt
	raw_log.attempt_count = (raw_log.attempt_count or 0) + 1
	raw_log.status = "Pending"
	raw_log.last_error = None
	if not raw_log.correlation_id:
		raw_log.correlation_id = correlation_id
	raw_log.save()
	frappe.db.commit()
	return None, True


def update_existing_raw_log_by_name(
	raw_log,
	*,
	plain_text: str,
	sender: str,
	subject: str,
	received_at_dt,
	message_id: str | None,
	correlation_id: str | None,
	max_attempts: int,
) -> dict | None:
	"""In-place update for an existing `FCR_*` doc (non-merge path). Returns early response or None."""
	if message_id:
		raw_log.message_id = message_id
	raw_log.sender = sender
	raw_log.subject = subject
	raw_log.received_at = received_at_dt
	raw_log.plain_text = plain_text
	if message_id and not raw_log.get("thread_root_message_id"):
		raw_log.thread_root_message_id = message_id
	if message_id:
		record_ingested_message_id(raw_log, message_id)

	if raw_log.status == "Successful" and raw_log.get("trip_request"):
		return _ok_trip_response(raw_log)

	early = try_mark_trip_from_existing_link(raw_log)
	if early:
		return early

	if raw_log.status == "Failed" and (raw_log.attempt_count or 0) >= max_attempts:
		return _failed_max_attempts(raw_log, with_retryable_flag=False)

	if raw_log.status == "Processing":
		raw_log.correlation_id = correlation_id
		raw_log.last_error = None
		raw_log.save()
		frappe.db.commit()
		return retryable_ok_response(raw_log)

	raw_log.attempt_count = (raw_log.attempt_count or 0) + 1
	raw_log.status = "Pending"
	raw_log.last_error = None
	raw_log.correlation_id = correlation_id
	raw_log.save()
	frappe.db.commit()
	return None


def load_or_create_raw_log_for_ingestion(
	*,
	merge_root: str | None,
	raw_log_name: str,
	email_hash: str,
	plain_text: str,
	sender: str,
	subject: str,
	received_at_dt,
	message_id: str | None,
	correlation_id: str | None,
	max_attempts: int,
) -> tuple[Any, dict | None, bool]:
	"""
	Load or create `FC Raw Email Log` for this webhook.

	Returns ``(raw_log, early_response, merged_into_thread)``. When ``early_response`` is set,
	the caller must return it immediately (duplicate / success shortcut / max attempts / processing).
	``merged_into_thread`` is True when this message was merged into an existing thread doc.
	"""
	if merge_root:
		raw_log = frappe.get_doc("FC Raw Email Log", merge_root)
		early, merged_into_thread = merge_reply_into_raw_log(
			raw_log,
			plain_text=plain_text,
			sender=sender,
			subject=subject,
			received_at_dt=received_at_dt,
			message_id=message_id,
			correlation_id=correlation_id,
			max_attempts=max_attempts,
		)
		if early:
			return None, early, False
		return raw_log, None, merged_into_thread

	if frappe.db.exists("FC Raw Email Log", raw_log_name):
		raw_log = frappe.get_doc("FC Raw Email Log", raw_log_name)
		early = update_existing_raw_log_by_name(
			raw_log,
			plain_text=plain_text,
			sender=sender,
			subject=subject,
			received_at_dt=received_at_dt,
			message_id=message_id,
			correlation_id=correlation_id,
			max_attempts=max_attempts,
		)
		if early:
			return None, early, False
		return raw_log, None, False

	raw_log = insert_new_raw_log(
		raw_log_name=raw_log_name,
		email_hash=email_hash,
		message_id=message_id,
		sender=sender,
		subject=subject,
		received_at_dt=received_at_dt,
		plain_text=plain_text,
		correlation_id=correlation_id,
	)
	return raw_log, None, False


def insert_new_raw_log(
	*,
	raw_log_name: str,
	email_hash: str,
	message_id: str | None,
	sender: str,
	subject: str,
	received_at_dt,
	plain_text: str,
	correlation_id: str | None,
) -> Any:
	raw_log = frappe.get_doc(
		{
			"doctype": "FC Raw Email Log",
			"name": raw_log_name,
			"message_id": message_id,
			"email_hash": email_hash,
			"sender": sender,
			"subject": subject,
			"received_at": received_at_dt,
			"plain_text": plain_text,
			"status": "Pending",
			"attempt_count": 1,
			"last_error": None,
			"correlation_id": correlation_id,
			"thread_root_message_id": message_id or None,
			"ingested_message_ids": f"{message_id}\n" if message_id else None,
		}
	)
	raw_log.insert()
	frappe.db.commit()
	return raw_log
