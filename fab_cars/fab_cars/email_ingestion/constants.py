# Copyright (c) 2026, fab_cars and contributors
# For license information, please see license.txt

import re

# Sender strings: `user@x`, `Name <user@x>`, etc.
EMAIL_RE = re.compile(
	r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}",
	re.IGNORECASE,
)

MESSAGE_ID_RE = re.compile(r"^\s*<[^>]+@[^>]+>\s*$")
# Some upstreams provide Message-ID without angle brackets.
_UNBRACKETED_MESSAGE_ID_RE = re.compile(r"^\s*[^<>\s]+@[^<>\s]+\s*$")

# Hidden in follow-up HTML so replies merge into the same `FC Raw Email Log`.
FC_THREAD_ROOT_RE = re.compile(
	r"FC-THREAD-ROOT:\s*(FCR_[A-Za-z0-9_]+)",
	re.IGNORECASE,
)

# Separator between inbound messages stored in a single `plain_text` (merged thread).
THREAD_MERGE_SEPARATOR = "\n\n---\n\n"

_SUBJECT_THREAD_RE = re.compile(r"(?i)^\s*(re|fw|fwd)\s*:\s*")


def normalize_subject_for_threading(subject: str) -> str:
	s = (subject or "").strip()
	s = _SUBJECT_THREAD_RE.sub("", s)
	return s.strip()
