# Copyright (c) 2026, fab_cars and contributors
# For license information, please see license.txt

import re

import frappe

from fab_cars.fab_cars.email_ingestion.constants import (
	_UNBRACKETED_MESSAGE_ID_RE,
	MESSAGE_ID_RE,
)


def strip_angle_brackets(value: str | None) -> str | None:
	if not value:
		return None
	v = value.strip()
	if v.startswith("<") and v.endswith(">") and len(v) >= 3:
		return v[1:-1].strip()
	return v


def coerce_message_id_for_reply(value: str | None) -> str | None:
	if not value:
		return None
	v = value.strip()
	if MESSAGE_ID_RE.match(v):
		return v
	if _UNBRACKETED_MESSAGE_ID_RE.match(v):
		return f"<{v}>"
	return None


def is_fab_cars_raw_log_name(value: str | None) -> bool:
	"""True if this looks like an `FC Raw Email Log` docname (`FCR_<hash>`), not an RFC Message-ID."""
	if not value:
		return False
	v = str(value).strip()
	return v.startswith("FCR_") and len(v) > 4


def message_id_variants(value: str | None) -> list[str]:
	"""Message-IDs may appear with or without angle brackets depending on source."""
	if not value:
		return []
	v = str(value).strip()
	if not v:
		return []
	out: set[str] = {v}
	st = strip_angle_brackets(v)
	if st and st != v:
		out.add(st)
		out.add(f"<{st}>")
	return list(out)


def reference_header_tokens(value: str | None) -> list[str]:
	if not value or not str(value).strip():
		return []
	tokens: list[str] = []
	for tok in re.split(r"\s+", str(value).strip()):
		t = tok.strip()
		if not t:
			continue
		st = strip_angle_brackets(t)
		tokens.append(st or t)
	return tokens


def find_raw_log_name_for_message_id(value: str | None) -> str | None:
	"""Return an `FC Raw Email Log` name whose thread includes this RFC Message-ID."""
	for mid in message_id_variants(value):
		for field in ("message_id", "thread_root_message_id"):
			name = frappe.db.get_value("FC Raw Email Log", {field: mid}, "name")
			if name:
				return name

	st = strip_angle_brackets(value or "") or (str(value).strip() if value else "")
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
