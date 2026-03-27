# Copyright (c) 2026, fab_cars and contributors
# For license information, please see license.txt

import re

import frappe

from fab_cars.fab_cars.email_ingestion.addresses import extract_sender_email
from fab_cars.fab_cars.email_ingestion.constants import FC_THREAD_ROOT_RE, normalize_subject_for_threading
from fab_cars.fab_cars.email_ingestion.message_ids import (
	find_raw_log_name_for_message_id,
	is_fab_cars_raw_log_name,
	message_id_variants,
	reference_header_tokens,
)


def extract_fc_thread_root_name_from_plain_text(plain_text: str | None) -> str | None:
	if not plain_text:
		return None
	m = FC_THREAD_ROOT_RE.search(plain_text)
	return m.group(1) if m else None


def resolve_merge_root_from_thread_headers(
	*,
	in_reply_to: str | None,
	references: str | None,
	message_id: str | None,
) -> str | None:
	"""Resolve an existing raw log using RFC threading headers (References / In-Reply-To)."""
	incoming = set(message_id_variants(message_id))

	candidates: list[str] = []
	for t in reference_header_tokens(references):
		candidates.append(t)
	if in_reply_to and str(in_reply_to).strip():
		candidates.append(str(in_reply_to).strip())

	seen: set[str] = set()
	for c in candidates:
		if not c or c in seen:
			continue
		seen.add(c)
		if incoming & set(message_id_variants(c)):
			continue
		name = find_raw_log_name_for_message_id(c)
		if name:
			return name
	return None


def resolve_merge_root_by_subject_sender(sender: str, subject: str) -> str | None:
	"""
	Last-resort thread match: same sender email + same normalized subject (Re:/Fwd: stripped).

	Only considers logs in `Needs Info`. Skips subjects that look like forwards.
	"""
	if not (subject or "").strip() or not (sender or "").strip():
		return None
	if re.match(r"(?i)^\s*fwd\s*:", subject.strip()):
		return None

	email = extract_sender_email(sender)
	if not email:
		return None

	base_subj = normalize_subject_for_threading(subject)
	if not base_subj:
		return None

	start = frappe.utils.add_days(frappe.utils.now_datetime(), -30)
	rows = frappe.get_all(
		"FC Raw Email Log",
		filters={
			"sender": ["like", f"%{email}%"],
			"status": "Needs Info",
			"received_at": [">=", start],
		},
		fields=["name", "subject"],
		order_by="received_at desc",
		limit_page_length=20,
	)
	for row in rows:
		if normalize_subject_for_threading(row.get("subject") or "") == base_subj:
			return row.get("name")
	return None


def resolve_thread_root_log_name(*, plain_text: str, correlation_id: str | None) -> str | None:
	"""
	Resolve an existing `FC Raw Email Log` name so inbound replies merge into the same doc.

	1. `correlation_id` when the webhook passes our thread token (`FCR_*`).
	2. `FC-THREAD-ROOT:FCR_*` token in the body (quoted follow-up template).
	3. Webhook `correlation_id` as RFC Message-ID of the initial inbound booking email.
	"""
	if correlation_id and is_fab_cars_raw_log_name(correlation_id):
		cid = str(correlation_id).strip()
		if frappe.db.exists("FC Raw Email Log", cid):
			return cid
	token = extract_fc_thread_root_name_from_plain_text(plain_text)
	if token and frappe.db.exists("FC Raw Email Log", token):
		return token

	if correlation_id and not is_fab_cars_raw_log_name(correlation_id):
		root = find_raw_log_name_for_message_id(str(correlation_id).strip())
		if root:
			return root

	return None


def resolve_merge_root(
	*,
	plain_text: str,
	correlation_id: str | None,
	message_id: str | None,
	in_reply_to: str | None,
	references: str | None,
	sender: str,
	subject: str,
) -> str | None:
	"""Best-effort: merge inbound replies into the same `FC Raw Email Log` as the booking thread."""
	r = resolve_thread_root_log_name(plain_text=plain_text, correlation_id=correlation_id)
	if r:
		return r
	r = resolve_merge_root_from_thread_headers(
		in_reply_to=in_reply_to,
		references=references,
		message_id=message_id,
	)
	if r:
		return r
	return resolve_merge_root_by_subject_sender(sender=sender, subject=subject)
