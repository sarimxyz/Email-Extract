# Copyright (c) 2026, fab_cars and contributors
# For license information, please see license.txt

from fab_cars.fab_cars.email_ingestion.message_ids import (
	coerce_message_id_for_reply,
	is_fab_cars_raw_log_name,
)


def ingested_message_id_lines(raw_log) -> list[str]:
	raw = (raw_log.get("ingested_message_ids") or "").strip()
	if not raw:
		return []
	return [ln.strip() for ln in raw.splitlines() if ln.strip()]


def incoming_message_already_recorded(raw_log, message_id: str | None) -> bool:
	if not message_id:
		return False
	mid = str(message_id).strip()
	if not mid:
		return False
	if (raw_log.get("message_id") or "").strip() == mid:
		return True
	return mid in ingested_message_id_lines(raw_log)


def record_ingested_message_id(raw_log, message_id: str | None) -> None:
	if not message_id:
		return
	mid = str(message_id).strip()
	if not mid:
		return
	lines = ingested_message_id_lines(raw_log)
	if mid not in lines:
		lines.append(mid)
	raw_log.ingested_message_ids = "\n".join(lines)


def parent_inbound_message_id_for_followup_reply(
	*,
	raw_log,
	payload_message_id: str | None,
	payload_correlation_id: str | None,
) -> str | None:
	"""
	RFC Message-ID of the customer's inbound booking email the follow-up must reply to.

	Preference: `thread_root_message_id`, then `message_id`, then webhook `message_id`,
	then `correlation_id` when it is not `FCR_*` and coerces to a Message-ID.
	"""
	candidates: list[str | None] = [
		raw_log.get("thread_root_message_id") if raw_log else None,
		raw_log.get("message_id") if raw_log else None,
		payload_message_id,
	]
	if payload_correlation_id and not is_fab_cars_raw_log_name(payload_correlation_id):
		candidates.append(payload_correlation_id)

	for c in candidates:
		mid = coerce_message_id_for_reply(c)
		if mid:
			return mid
	return None
