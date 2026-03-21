# Copyright (c) 2026, fab_cars and contributors
# For license information, please see license.txt

import hashlib
import html as html_lib
import re
from datetime import timezone
from typing import Any

import frappe
from frappe.utils.user import get_system_managers

from fab_cars.fab_cars.doctype.fc_extracted_email.fc_extracted_email import process_payload_to_trip_request

_EMAIL_RE = re.compile(
	r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}",
	re.IGNORECASE,
)

_MESSAGE_ID_RE = re.compile(r"^\s*<[^>]+@[^>]+>\s*$")
# Some upstreams provide Message-ID without angle brackets. For threading we still
# need the `In-Reply-To` format, so we accept that shape and wrap it with `< >`.
_UNBRACKETED_MESSAGE_ID_RE = re.compile(r"^\s*[^<>\s]+@[^<>\s]+\s*$")


def _coerce_message_id_for_reply(value: str | None) -> str | None:
	if not value:
		return None
	v = value.strip()
	if _MESSAGE_ID_RE.match(v):
		return v
	if _UNBRACKETED_MESSAGE_ID_RE.match(v):
		return f"<{v}>"
	return None


def _is_fab_cars_raw_log_name(value: str | None) -> bool:
	"""True if this looks like an `FC Raw Email Log` docname (`FCR_<hash>`), not an RFC Message-ID."""
	if not value:
		return False
	v = str(value).strip()
	return v.startswith("FCR_") and len(v) > 4


# Hidden in follow-up HTML so replies can be merged into the same `FC Raw Email Log`.
_FC_THREAD_ROOT_RE = re.compile(
	r"FC-THREAD-ROOT:\s*(FCR_[A-Za-z0-9_]+)",
	re.IGNORECASE,
)
# Separator between inbound messages stored in a single `plain_text` (merged thread).
_FC_THREAD_MERGE_SEP = "\n\n---\n\n"


def _extract_fc_thread_root_name_from_plain_text(plain_text: str | None) -> str | None:
	if not plain_text:
		return None
	m = _FC_THREAD_ROOT_RE.search(plain_text)
	return m.group(1) if m else None


def _message_id_variants(value: str | None) -> list[str]:
	"""Message-IDs may appear with or without angle brackets depending on source."""
	if not value:
		return []
	v = str(value).strip()
	if not v:
		return []
	out: set[str] = {v}
	st = _strip_angle_brackets(v)
	if st and st != v:
		out.add(st)
		out.add(f"<{st}>")
	return list(out)


def _reference_header_tokens(value: str | None) -> list[str]:
	if not value or not str(value).strip():
		return []
	tokens: list[str] = []
	for tok in re.split(r"\s+", str(value).strip()):
		t = tok.strip()
		if not t:
			continue
		st = _strip_angle_brackets(t)
		tokens.append(st or t)
	return tokens


def _find_raw_log_name_for_message_id(value: str | None) -> str | None:
	"""Return an `FC Raw Email Log` name whose thread includes this RFC Message-ID."""
	for mid in _message_id_variants(value):
		for field in ("message_id", "thread_root_message_id"):
			name = frappe.db.get_value("FC Raw Email Log", {field: mid}, "name")
			if name:
				return name

	st = _strip_angle_brackets(value or "") or (str(value).strip() if value else "")
	if not st:
		return None

	for candidate in (st, f"<{st}>"):
		row = frappe.db.sql(
			"""
			SELECT name FROM `tabFC Raw Email Log`
			WHERE ingested_message_ids IS NOT NULL AND ingested_message_ids != ''
			AND CONCAT('\n', ingested_message_ids, '\n') LIKE %(pat)s
			LIMIT 1
			""",
			{"pat": f"%\n{candidate}\n%"},
		)
		if row:
			return row[0][0]
	return None


_SUBJECT_THREAD_RE = re.compile(r"(?i)^\s*(re|fw|fwd)\s*:\s*")


def _normalize_subject_for_thread(subject: str) -> str:
	s = (subject or "").strip()
	s = _SUBJECT_THREAD_RE.sub("", s)
	return s.strip()


def _resolve_merge_root_from_thread_headers(
	*,
	in_reply_to: str | None,
	references: str | None,
	message_id: str | None,
) -> str | None:
	"""
	Resolve an existing raw log using RFC threading headers (References / In-Reply-To).

	These may point at the customer's original inbound id, a prior merged id, or (via References)
	an earlier hop in the chain.
	"""
	incoming = set(_message_id_variants(message_id))

	candidates: list[str] = []
	for t in _reference_header_tokens(references):
		candidates.append(t)
	if in_reply_to and str(in_reply_to).strip():
		candidates.append(str(in_reply_to).strip())

	seen: set[str] = set()
	for c in candidates:
		if not c or c in seen:
			continue
		seen.add(c)
		if incoming & set(_message_id_variants(c)):
			continue
		name = _find_raw_log_name_for_message_id(c)
		if name:
			return name
	return None


def _resolve_merge_root_by_subject_sender(sender: str, subject: str) -> str | None:
	"""
	Last-resort thread match: same sender email + same normalized subject (Re:/Fwd: stripped).

	Only considers logs in `Needs Info` (awaiting a reply with missing details). This avoids
	merging unrelated new booking emails that share a common subject line with an open thread.

	Skipped for subjects that look like forwards (new thread unless headers linked).
	"""
	if not (subject or "").strip() or not (sender or "").strip():
		return None
	if re.match(r"(?i)^\s*fwd\s*:", subject.strip()):
		return None

	email = _extract_sender_email(sender)
	if not email:
		return None

	base_subj = _normalize_subject_for_thread(subject)
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
		if _normalize_subject_for_thread(row.get("subject") or "") == base_subj:
			return row.get("name")
	return None


def _resolve_merge_root(
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
	r = _resolve_thread_root_log_name(plain_text=plain_text, correlation_id=correlation_id)
	if r:
		return r
	r = _resolve_merge_root_from_thread_headers(
		in_reply_to=in_reply_to,
		references=references,
		message_id=message_id,
	)
	if r:
		return r
	return _resolve_merge_root_by_subject_sender(sender=sender, subject=subject)


def _resolve_thread_root_log_name(*, plain_text: str, correlation_id: str | None) -> str | None:
	"""
	Resolve an existing `FC Raw Email Log` name so inbound **replies** merge into the same doc.

	1. `correlation_id` when the webhook passes our thread token (`FCR_*`).
	2. `FC-THREAD-ROOT:FCR_*` token in the body (quoted follow-up template).
	"""
	if correlation_id and _is_fab_cars_raw_log_name(correlation_id):
		cid = str(correlation_id).strip()
		if frappe.db.exists("FC Raw Email Log", cid):
			return cid
	token = _extract_fc_thread_root_name_from_plain_text(plain_text)
	if token and frappe.db.exists("FC Raw Email Log", token):
		return token

	# Fallback: webhook correlation_id can be an RFC Message-ID of the
	# *initial inbound booking email* (not our FC Raw Email Log token).
	# Map it back to the existing FC Raw Email Log so replies merge even
	# when the hidden thread token isn't preserved by the client.
	if correlation_id and not _is_fab_cars_raw_log_name(correlation_id):
		root = _find_raw_log_name_for_message_id(str(correlation_id).strip())
		if root:
			return root

	return None


def _split_thread_plain_text_segments(plain_text: str) -> list[str]:
	"""Split merged `plain_text` on the same separator used when appending inbound replies."""
	if not (plain_text or "").strip():
		return []
	parts = re.split(r"\n{2,}---\n{2,}", plain_text.strip())
	return [p.strip() for p in parts if p.strip()]


def _merge_plain_text_segments(existing: str | None, new_inbound: str) -> str:
	e = (existing or "").strip()
	n = (new_inbound or "").strip()
	if not e:
		return n
	if not n:
		return e
	return e + _FC_THREAD_MERGE_SEP + n


def _ingested_message_id_lines(raw_log) -> list[str]:
	raw = (raw_log.get("ingested_message_ids") or "").strip()
	if not raw:
		return []
	return [ln.strip() for ln in raw.splitlines() if ln.strip()]


def _incoming_message_already_recorded(raw_log, message_id: str | None) -> bool:
	"""True if this inbound `message_id` was already merged / stored on this log."""
	if not message_id:
		return False
	mid = str(message_id).strip()
	if not mid:
		return False
	if (raw_log.get("message_id") or "").strip() == mid:
		return True
	return mid in _ingested_message_id_lines(raw_log)


def _record_ingested_message_id(raw_log, message_id: str | None) -> None:
	if not message_id:
		return
	mid = str(message_id).strip()
	if not mid:
		return
	lines = _ingested_message_id_lines(raw_log)
	if mid not in lines:
		lines.append(mid)
	raw_log.ingested_message_ids = "\n".join(lines)


def _parent_inbound_message_id_for_followup_reply(
	*,
	raw_log,
	payload_message_id: str | None,
	payload_correlation_id: str | None,
) -> str | None:
	"""
	Resolve the RFC Message-ID of the **customer's inbound booking email** the follow-up must reply to.

	Preference order:
	1. `FC Raw Email Log.message_id` (persisted inbound id for this event)
	2. Validated webhook `message_id`
	3. `correlation_id` only when it is not our own Fab Cars thread token (`FCR_*`) and
	   coerces to a valid Message-ID (e.g. provider thread id in `<...@...>` form)
	"""
	candidates: list[str | None] = [
		raw_log.get("thread_root_message_id") if raw_log else None,
		raw_log.get("message_id") if raw_log else None,
		payload_message_id,
	]
	if payload_correlation_id and not _is_fab_cars_raw_log_name(payload_correlation_id):
		candidates.append(payload_correlation_id)

	for c in candidates:
		mid = _coerce_message_id_for_reply(c)
		if mid:
			return mid
	return None


def _strip_angle_brackets(value: str | None) -> str | None:
	if not value:
		return None
	v = value.strip()
	if v.startswith("<") and v.endswith(">") and len(v) >= 3:
		return v[1:-1].strip()
	return v


def _communication_name_for_sendmail_in_reply_to(message_id_or_comm_name: str | None) -> str | None:
	"""
	Resolve the value to pass as `frappe.sendmail(..., in_reply_to=...)`.

	Frappe standard (see `EmailQueue.prepare_email_content`): `in_reply_to` must be
	the **name** of a `Communication` document. Frappe then loads that row's
	`message_id` and sets the outbound `In-Reply-To` header to that id.

	Passing a raw RFC Message-ID string (e.g. `<abc@mail.gmail.com>`) does **not**
	work: `get_value("Communication", "<...>", "message_id")` is not a valid lookup.

	We resolve by:
	1. If `message_id_or_comm_name` is already an existing `Communication.name`, use it.
	2. Else find the latest Email `Communication` whose `message_id` matches (with/without `<>`).
	"""
	if not message_id_or_comm_name:
		return None

	raw = str(message_id_or_comm_name).strip()
	if not raw:
		return None

	if frappe.db.exists("Communication", raw):
		return raw

	variants: list[str] = [raw]
	stripped = _strip_angle_brackets(raw)
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


def _message_id_stripped_for_communication_db(parent_message_id: str | None) -> str | None:
	"""Frappe stores `Communication.message_id` without angle brackets (see `receive.py`)."""
	if not parent_message_id:
		return None
	coerced = _coerce_message_id_for_reply(str(parent_message_id).strip())
	if not coerced:
		return None
	stripped = _strip_angle_brackets(coerced)
	return stripped.strip() if stripped else None


def _ensure_stub_communication_for_parent_message(
	*,
	parent_message_id: str | None,
	subject: str,
	sender: str,
	plain_text_snippet: str,
) -> str | None:
	"""
	Frappe's `EmailQueue.prepare_email_content` only sets outbound `In-Reply-To` when
	`frappe.sendmail(..., in_reply_to=...)` is a **Communication.name** that has `message_id`
	set. Webhook-only booking mail often never created a `Communication`, so replies looked
	like new threads despite a `Re:` subject.

	Create a minimal **Received** Communication for the customer's Message-ID when missing,
	so native Frappe threading headers apply (most reliable for Gmail/Outlook).
	"""
	stripped = _message_id_stripped_for_communication_db(parent_message_id)
	if not stripped:
		return None

	coerced = _coerce_message_id_for_reply(stripped) or f"<{stripped}>"
	existing = _communication_name_for_sendmail_in_reply_to(coerced)
	if existing:
		return existing

	found = frappe.db.get_value(
		"Communication",
		{"communication_medium": "Email", "message_id": stripped},
		"name",
	)
	if found:
		return found

	sender_email = _extract_sender_email(sender or "") or (sender or "").strip()[:255]
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


def _build_thread_plain_text(*, correlation_id: str | None, current_plain_text: str | None) -> str:
	"""
	Build a thread-level body for extraction by concatenating all known inbound
	`FC Raw Email Log` messages belonging to the same `correlation_id`.

	When replies are merged into **one** log, `plain_text` contains multiple
	segments separated by `_FC_THREAD_MERGE_SEP`; each segment is stripped
	separately (same behaviour as one DB row per inbound message).

	Pass `current_plain_text=None` when the latest inbound body is already merged
	into `plain_text` (thread reply) or when reprocessing a single stored doc.
	"""
	if not correlation_id:
		return (current_plain_text or "") if current_plain_text is not None else ""

	# Keep it bounded: reduce token usage and avoid huge quoted threads.
	# (Most real threads are short.)
	max_msgs = 10
	max_chars = 20000

	thread_logs = frappe.get_all(
		"FC Raw Email Log",
		filters={"correlation_id": correlation_id},
		fields=["plain_text"],
		order_by="received_at asc",
		limit=max_msgs,
	)

	parts: list[str] = []
	for l in thread_logs:
		txt = (l.get("plain_text") or "").strip()
		if not txt:
			continue
		segs = _split_thread_plain_text_segments(txt)
		if len(segs) > 1:
			for s in segs:
				st = _strip_quoted_reply_plaintext(s)
				if st:
					parts.append(st)
		else:
			# Strip quoted previous message content so extraction focuses on what
			# the user wrote in each reply.
			parts.append(_strip_quoted_reply_plaintext(txt))

	# Ensure current content is always included when not already merged into the log.
	if current_plain_text is not None:
		current_txt = (current_plain_text or "").strip()
		if current_txt:
			current_txt = _strip_quoted_reply_plaintext(current_txt)
			if not parts or parts[-1] != current_txt:
				parts.append(current_txt)

	if not parts:
		return (current_plain_text or "") if current_plain_text is not None else ""

	joined = "\n\n---\n\n".join(parts)
	if len(joined) > max_chars:
		joined = joined[:max_chars]
	return joined


def _strip_quoted_reply_plaintext(text: str) -> str:
	"""
	Remove quoted reply separators (e.g. "On ... wrote:" / "-----Original Message-----").

	We do this both to reduce noise for LLM extraction and to avoid repeatedly
	"seeing" our own follow-up template instead of the user's actual reply.
	"""
	if not text:
		return text

	separator_patterns = [
		# Gmail / Outlook style.
		r"(?im)^\s*On .+ wrote:\s*$",
		# Outlook sometimes uses this separator.
		r"(?im)^\s*-----Original Message-----\s*$",
		# Fallback for blockquoted From lines.
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


def _sha256_text(text: str) -> str:
	return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _normalize_ws(text: str) -> str:
	return re.sub(r"\s+", " ", (text or "")).strip().lower()


def _compute_email_hash(
	*,
	message_id: str | None,
	sender: str,
	subject: str,
	received_at_dt,
	plain_text: str,
) -> str:
	if message_id:
		return _sha256_text(str(message_id))

	canonical_plain = _normalize_ws(plain_text)[:2000]
	canonical = (
		f"{_normalize_ws(sender)}|{_normalize_ws(subject)}|{received_at_dt.isoformat()}|{canonical_plain}"
	)
	return _sha256_text(canonical)


def _validate_payload(payload: dict[str, Any]) -> dict[str, Any]:
	"""
	Validate webhook payload shape strictly enough for safe persistence/extraction.
	"""

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

	# MariaDB `Datetime` columns generally expect naive datetimes; strip tzinfo
	# after converting to UTC for stable comparisons + indexing.
	if getattr(received_at_dt, "tzinfo", None) is not None:
		received_at_dt = received_at_dt.astimezone(timezone.utc).replace(tzinfo=None)

	message_id = payload.get("message_id")
	if message_id is not None and not isinstance(message_id, str):
		raise ValueError("`message_id` must be a string when provided")

	email_hash = payload.get("email_hash")
	if email_hash is not None and not isinstance(email_hash, str):
		raise ValueError("`email_hash` must be a string when provided")

	correlation_id = payload.get("correlation_id")
	if correlation_id is not None and not isinstance(correlation_id, str):
		raise ValueError("`correlation_id` must be a string when provided")

	in_reply_to = payload.get("in_reply_to")
	if in_reply_to is not None and not isinstance(in_reply_to, str):
		raise ValueError("`in_reply_to` must be a string when provided")

	references = payload.get("references")
	if references is not None and not isinstance(references, str):
		raise ValueError("`references` must be a string when provided")

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


def _get_ingestion_max_attempts() -> int:
	"""
	Single source of truth for retry limits (doctype-only; no site_config/env).
	"""
	if not frappe.db.exists("DocType", "FC Ingestion Settings"):
		raise ValueError("Missing DocType `FC Ingestion Settings`. Create it to configure ingestion retries.")

	settings = frappe.get_single("FC Ingestion Settings")
	amt = int(getattr(settings, "max_attempts", None) or 0)
	if amt < 1:
		raise ValueError("`FC Ingestion Settings.max_attempts` must be >= 1")
	return amt


def _get_ingestion_settings():
	if not frappe.db.exists("DocType", "FC Ingestion Settings"):
		raise ValueError("Missing DocType `FC Ingestion Settings`. Create it to configure ingestion retries.")
	return frappe.get_single("FC Ingestion Settings")


def _extract_sender_email(sender: str) -> str | None:
	"""
	Attempt to extract a raw email address from common formats like:
	- `user@example.com`
	- `User Name <user@example.com>`
	"""
	if not sender:
		return None
	s = sender.strip()
	# Be tolerant of real-world `From:` strings, like:
	# - `Name <email@example.com>`
	# - `email@example.com (via something)`
	# - `Name <email@example.com>, Company List ...`
	m = _EMAIL_RE.search(s)
	return m.group(0) if m else None


def _send_missing_info_followup(
	*,
	to_sender: str,
	missing_fields: list[str],
	# RFC Message-ID of the customer's **inbound** booking mail (coerced to `<...@...>`).
	# Used to thread the follow-up as a reply via Communication lookup + `ensure_references_header_for_threading`.
	in_reply_to: str | None,
	original_subject: str | None,
	thread_root_token: str | None,
	plain_text_snippet: str | None = None,
) -> bool:
	settings = _get_ingestion_settings()
	if not getattr(settings, "send_followup_email", 1):
		return False

	to_email = _extract_sender_email(to_sender)
	if not to_email:
		return False

	custom_subject = getattr(settings, "followup_email_subject", None)
	base_subject = custom_subject or "Action needed: a few details for your Fab Cars booking"

	# Threading: Gmail/Outlook use RFC `In-Reply-To`/`References` first, but matching
	# `Re: <original thread subject>` avoids a "new conversation" when headers are weak.
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
		# Hidden token so the user's reply (when quoted) can be linked back to
		# the original raw email log entry.
		thread_root_html = (
			f"<!-- FC-THREAD-ROOT:{thread_root_token} -->"
			f'<div style="display:none">FC-THREAD-ROOT:{thread_root_token}</div>'
		)

	# Professional, concise HTML: works in Gmail/Outlook; token must stay in body for threading fallbacks.
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

	# Frappe: `in_reply_to` must be a `Communication.name` (not a raw Message-ID).
	# See `QueueBuilder.prepare_email_content` in frappe/email/doctype/email_queue/email_queue.py
	if in_reply_to:
		_ensure_stub_communication_for_parent_message(
			parent_message_id=in_reply_to,
			subject=original_subject or base_subject,
			sender=to_sender,
			plain_text_snippet=plain_text_snippet or "",
		)
	communication_name = _communication_name_for_sendmail_in_reply_to(in_reply_to)
	if in_reply_to and not communication_name:
		frappe.logger("fab_cars.email").info(
			"Missing-info follow-up: no Communication row for inbound Message-Id; "
			"outbound In-Reply-To cannot be set by Frappe. id=%s",
			in_reply_to,
		)

	# When Frappe cannot resolve a Communication, `prepare_email_content` skips
	# `In-Reply-To`. Stash the customer's Message-ID for `make_email_body_message`
	# (see `fab_cars.hooks_handlers.ensure_references_header_for_threading`). Email Queue
	# builds MIME synchronously when the row is created, so this runs in-process.
	parent_mid_for_hook = _coerce_message_id_for_reply(in_reply_to)
	try:
		if parent_mid_for_hook:
			frappe.flags.fab_cars_thread_parent_message_id = parent_mid_for_hook
		frappe.sendmail(
			recipients=[to_email],
			subject=subject,
			message=message,
			in_reply_to=communication_name,
			email_headers={"X-FC-Thread-Root": thread_root_token} if thread_root_token else None,
			# Omit `message_id`: Frappe must generate a **new** unique Message-Id for this
			# outbound mail. Reusing the parent's id breaks RFC 5322 and client threading.
		)
	finally:
		frappe.flags.pop("fab_cars_thread_parent_message_id", None)
	return True


@frappe.whitelist(allow_guest=False)
def ingest_email(payload: dict) -> dict:
	"""Validate payload, upsert `FC Raw Email Log`, run extraction, create `FC Trip Request` when applicable."""
	# IMPORTANT: This can be called from background workers or from ingestion
	# webhooks. Use a privileged user so inserts/updates don't depend on the
	# caller's session (and so "Pull emails" doesn't break the current browser session).
	system_user = get_system_managers(only_name=True) or []
	frappe.set_user(system_user[0] if system_user else "Administrator")

	try:
		validated = _validate_payload(payload)
	except Exception as e:
		frappe.throw(str(e))

	plain_text = validated["plain_text"]
	sender = validated["sender"]
	subject = validated["subject"]
	received_at_dt = validated["received_at_dt"]
	message_id = validated["message_id"]
	email_hash = validated["email_hash"]
	correlation_id = validated["correlation_id"] or email_hash or message_id
	in_reply_to = validated.get("in_reply_to")
	references = validated.get("references")
	is_cab_booking = validated.get("is_cab_booking")
	max_attempts = _get_ingestion_max_attempts()

	thread_success_trip = None
	if correlation_id:
		thread_success_trip = frappe.db.get_value(
			"FC Raw Email Log",
			{"correlation_id": correlation_id, "status": "Successful"},
			"trip_request",
		)

	merge_root = _resolve_merge_root(
		plain_text=plain_text,
		correlation_id=correlation_id,
		message_id=message_id,
		in_reply_to=in_reply_to,
		references=references,
		sender=sender,
		subject=subject,
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

	if not email_hash:
		email_hash = _compute_email_hash(
			message_id=message_id,
			sender=sender,
			subject=subject,
			received_at_dt=received_at_dt,
			plain_text=plain_text,
		)

	raw_log_name = f"FCR_{email_hash}"
	merged_into_thread = False

	if merge_root:
		# Thread reply: merge into the same `FC Raw Email Log` (do not create `FCR_{hash(new_msg)}`).
		raw_log = frappe.get_doc("FC Raw Email Log", merge_root)

		if raw_log.status == "Successful" and raw_log.get("trip_request"):
			return {"status": "ok", "raw_log": raw_log.name, "trip_request": raw_log.trip_request}

		if _incoming_message_already_recorded(raw_log, message_id):
			return {
				"status": "ok",
				"raw_log": raw_log.name,
				"trip_request": raw_log.get("trip_request"),
				"retryable": True,
				"missing_fields": [],
			}

		existing_trip = frappe.db.get_value("FC Trip Request", {"trip_name": raw_log.name}, "name")
		if existing_trip:
			raw_log.status = "Successful"
			raw_log.trip_request = existing_trip
			raw_log.last_error = None
			raw_log.save()
			frappe.db.commit()
			return {"status": "ok", "raw_log": raw_log.name, "trip_request": existing_trip}

		if raw_log.status == "Failed" and (raw_log.attempt_count or 0) >= max_attempts:
			return {
				"status": "failed",
				"raw_log": raw_log.name,
				"trip_request": raw_log.get("trip_request"),
				"error": raw_log.last_error or "Max ingestion attempts exceeded",
				"retryable": False,
			}

		if raw_log.status == "Processing":
			raw_log.last_error = None
			raw_log.save()
			frappe.db.commit()
			return {
				"status": "ok",
				"raw_log": raw_log.name,
				"trip_request": raw_log.get("trip_request"),
				"retryable": True,
				"missing_fields": [],
			}

		prev_mid = (raw_log.get("message_id") or "").strip()
		raw_log.plain_text = _merge_plain_text_segments(raw_log.plain_text, plain_text)
		_record_ingested_message_id(raw_log, message_id)
		# Only overwrite when provider sent an id; avoid clearing the column on None.
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
		merged_into_thread = True

	elif frappe.db.exists("FC Raw Email Log", raw_log_name):
		raw_log = frappe.get_doc("FC Raw Email Log", raw_log_name)

		if message_id:
			raw_log.message_id = message_id
		raw_log.sender = sender
		raw_log.subject = subject
		raw_log.received_at = received_at_dt
		raw_log.plain_text = plain_text
		if message_id and not raw_log.get("thread_root_message_id"):
			raw_log.thread_root_message_id = message_id
		if message_id:
			_record_ingested_message_id(raw_log, message_id)

		if raw_log.status == "Successful" and raw_log.get("trip_request"):
			return {"status": "ok", "raw_log": raw_log.name, "trip_request": raw_log.trip_request}

		existing_trip = frappe.db.get_value("FC Trip Request", {"trip_name": raw_log.name}, "name")
		if existing_trip:
			raw_log.status = "Successful"
			raw_log.trip_request = existing_trip
			raw_log.last_error = None
			raw_log.save()
			frappe.db.commit()
			return {"status": "ok", "raw_log": raw_log.name, "trip_request": existing_trip}

		if raw_log.status == "Failed" and (raw_log.attempt_count or 0) >= max_attempts:
			return {
				"status": "failed",
				"raw_log": raw_log.name,
				"trip_request": raw_log.get("trip_request"),
				"error": raw_log.last_error or "Max ingestion attempts exceeded",
				"retryable": False,
			}

		# Concurrent ingestion: another worker holds this log in `Processing`.
		# Persist inbound metadata but do not re-run extraction or bump attempts.
		if raw_log.status == "Processing":
			raw_log.correlation_id = correlation_id
			raw_log.last_error = None
			raw_log.save()
			frappe.db.commit()
			return {
				"status": "ok",
				"raw_log": raw_log.name,
				"trip_request": raw_log.get("trip_request"),
				"retryable": True,
				"missing_fields": [],
			}

		raw_log.attempt_count = (raw_log.attempt_count or 0) + 1
		raw_log.status = "Pending"
		raw_log.last_error = None
		raw_log.correlation_id = correlation_id
		raw_log.save()
		frappe.db.commit()
	else:
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

	# New row created as `Processing` (e.g. lock row): skip extraction.
	if raw_log.status == "Processing":
		return {
			"status": "ok",
			"raw_log": raw_log.name,
			"trip_request": raw_log.get("trip_request"),
			"retryable": True,
			"missing_fields": [],
		}

	# If the thread already has a successful booking, do not re-run extraction.
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

	thread_plain_text = _build_thread_plain_text(
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
		# New source of truth for dashboard joining is `FC Raw Email Log`.
		mail_link_value=raw_log.name,
		is_cab_booking=is_cab_booking,
	)

	if result.get("status") == "needs_info":
		missing_fields = result.get("missing_fields") or []
		try:
			# Reply in the same thread as the user's **initial booking email**: parent = inbound Message-ID.
			# Compute before we overwrite `correlation_id` with our Fab Cars thread token (`FCR_*`).
			parent_message_id = _parent_inbound_message_id_for_followup_reply(
				raw_log=raw_log,
				payload_message_id=message_id,
				payload_correlation_id=correlation_id,
			)

			# Stable booking context id: correlates the user follow-up reply for extraction.
			thread_root_token = raw_log.name
			raw_log.correlation_id = thread_root_token
			raw_log.save()
			frappe.db.commit()

			_send_missing_info_followup(
				to_sender=sender,
				missing_fields=missing_fields,
				in_reply_to=parent_message_id,
				original_subject=subject,
				thread_root_token=thread_root_token,
				plain_text_snippet=plain_text,
			)
		except Exception as e:
			# If email sending fails, keep ingestion state; missing info is still tracked.
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
	"""
	Re-run extraction for an existing `FC Raw Email Log`.

	This is primarily intended for debugging and for reprocessing older
	records after improving thread-aware parsing.
	"""
	raw_log = frappe.get_doc("FC Raw Email Log", raw_log_name)

	thread_plain_text = _build_thread_plain_text(
		correlation_id=raw_log.correlation_id,
		current_plain_text=None,
	)

	result = process_payload_to_trip_request(
		plain_text=thread_plain_text,
		email_subject=raw_log.subject,
		email_sender=raw_log.sender,
		received_date=raw_log.received_at,
		source_message_id=raw_log.message_id or raw_log.email_hash,
		base_name=raw_log.name,
		extracted_email_doc=None,
		raw_email_log_doc=raw_log,
		mail_link_value=raw_log.name,
		is_cab_booking=True,  # already classified as a cab booking in the original pipeline
	)

	return result
