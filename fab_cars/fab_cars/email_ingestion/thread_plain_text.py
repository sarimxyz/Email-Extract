# Copyright (c) 2026, fab_cars and contributors
# For license information, please see license.txt

import re

import frappe

from fab_cars.fab_cars.email_ingestion.constants import THREAD_MERGE_SEPARATOR

# Split merged `plain_text` on the same separator used when appending inbound replies.
_THREAD_SEGMENT_SPLIT_RE = re.compile(r"\n{2,}---\n{2,}")


def split_thread_plain_text_segments(plain_text: str) -> list[str]:
	if not (plain_text or "").strip():
		return []
	parts = _THREAD_SEGMENT_SPLIT_RE.split(plain_text.strip())
	return [p.strip() for p in parts if p.strip()]


def _append_stripped_segments(parts: list[str], plain_text: str) -> None:
	"""Split stored `plain_text` on thread separators; strip quotes from each segment."""
	txt = (plain_text or "").strip()
	if not txt:
		return
	segs = split_thread_plain_text_segments(txt)
	if len(segs) > 1:
		for s in segs:
			st = strip_quoted_reply_plaintext(s)
			if st:
				parts.append(st)
	else:
		parts.append(strip_quoted_reply_plaintext(txt))


def merge_plain_text_segments(existing: str | None, new_inbound: str) -> str:
	e = (existing or "").strip()
	n = (new_inbound or "").strip()
	if not e:
		return n
	if not n:
		return e
	return e + THREAD_MERGE_SEPARATOR + n


def strip_quoted_reply_plaintext(text: str) -> str:
	"""
	Remove quoted reply separators (e.g. "On ... wrote:" / "-----Original Message-----").
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


def build_thread_plain_text_for_extraction(
	*, correlation_id: str | None, current_plain_text: str | None
) -> str:
	"""
	Concatenate all known inbound `FC Raw Email Log` bodies for the same `correlation_id`.

	When `current_plain_text` is not None, append it if not already the last segment
	(used when the latest body is not yet merged into the stored log row).
	"""
	if not correlation_id:
		return (current_plain_text or "") if current_plain_text is not None else ""

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
		_append_stripped_segments(parts, l.get("plain_text") or "")

	if current_plain_text is not None:
		current_txt = (current_plain_text or "").strip()
		if current_txt:
			current_txt = strip_quoted_reply_plaintext(current_txt)
			if not parts or parts[-1] != current_txt:
				parts.append(current_txt)

	if not parts:
		return (current_plain_text or "") if current_plain_text is not None else ""

	joined = THREAD_MERGE_SEPARATOR.join(parts)
	if len(joined) > max_chars:
		joined = joined[:max_chars]
	return joined
