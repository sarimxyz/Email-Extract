# Copyright (c) 2026, fab_cars and contributors
# For license information, please see license.txt

from fab_cars.fab_cars.email_ingestion.constants import EMAIL_RE


def extract_sender_email(sender: str) -> str | None:
	"""
	Extract a raw email address from common formats:
	`user@example.com`, `User Name <user@example.com>`, etc.
	"""
	if not sender:
		return None
	s = sender.strip()
	m = EMAIL_RE.search(s)
	return m.group(0) if m else None
