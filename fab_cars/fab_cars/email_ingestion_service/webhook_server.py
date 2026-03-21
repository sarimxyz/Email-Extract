# Copyright (c) 2026, fab_cars and contributors
# For license information, please see license.txt

import base64
import datetime as dt
import email
import email.header
import email.utils
import html
import json
import os
import re
import time
import traceback
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer


def _env(name: str, default=None):
	return os.environ.get(name, default)


def _strip_html_to_text(html_text: str) -> str:
	html_text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html_text, flags=re.IGNORECASE | re.DOTALL)
	html_text = re.sub(r"<[^>]+>", " ", html_text)
	html_text = html.unescape(html_text)
	html_text = re.sub(r"[\r\n\t]+", " ", html_text)
	html_text = re.sub(r"\s{2,}", " ", html_text)
	return html_text.strip()


def _decode_mime_header(value: str) -> str:
	try:
		decoded = email.header.decode_header(value)
		parts = []
		for part, enc in decoded:
			if isinstance(part, bytes):
				parts.append(part.decode(enc or "utf-8", errors="replace"))
			else:
				parts.append(str(part))
		return "".join(parts).strip()
	except Exception:
		return value.strip()


def _strip_angle_brackets(value: str | None) -> str:
	if value is None:
		return ""
	v = str(value).strip()
	if v.startswith("<") and v.endswith(">") and len(v) >= 3:
		return v[1:-1].strip()
	return v


def _strip_quoted_reply_plaintext(text: str) -> str:
	"""
	Best-effort cleanup to remove quoted reply content.

	Most email clients append the previous message after a separator like:
	- "On Fri, ... wrote:"
	- "-----Original Message-----"
	This prevents our extractor from repeatedly "seeing" the missing-items
	list from the follow-up instead of the user's actual reply values.
	"""
	if not text:
		return text

	separator_patterns = [
		# Gmail / Outlook style.
		r"(?im)^\s*On .+ wrote:\s*$",
		# Outlook sometimes.
		r"(?im)^\s*-----Original Message-----\s*$",
		# Simple fallback for blockquoted From lines.
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


def _extract_thread_root_token(msg: email.message.Message, plain_text: str) -> str | None:
	"""
	Extract the follow-up thread root token from either:
	- Custom header `X-FC-Thread-Root`
	- Embedded hidden token in the (quoted) HTML converted to plaintext
	"""
	try:
		token = msg.get("X-FC-Thread-Root") or msg.get("X-Fc-Thread-Root") or ""
		token = token.strip() if token else ""
	except Exception:
		token = ""

	if token:
		return token

	m = re.search(
		# Hidden token is typically `FC-THREAD-ROOT:{token}` inside an HTML comment/div.
		# Allow common token shapes (sha-like, message-id-like, etc.).
		r"FC-THREAD-ROOT\s*[:=]\s*([^\s<>,;]+)",
		plain_text or "",
		flags=re.IGNORECASE,
	)
	if m:
		return (m.group(1) or "").strip() or None

	return None


def _parse_raw_mime(raw_mime: str) -> dict:
	msg = email.message_from_string(raw_mime)

	message_id = _strip_angle_brackets(msg.get("Message-ID") or msg.get("Message-Id"))
	in_reply_to = _strip_angle_brackets(msg.get("In-Reply-To") or "")
	references = msg.get("References") or ""
	references_raw = references.strip() if references else ""
	from_header = msg.get("From") or ""
	subject_header = msg.get("Subject") or ""
	date_header = msg.get("Date") or ""

	sender = _decode_mime_header(from_header)
	subject = _decode_mime_header(subject_header)

	received_at = None
	if date_header:
		try:
			received_at = email.utils.parsedate_to_datetime(date_header)
			# Keep naive datetime in server timezone context (Frappe will parse safely).
			if received_at.tzinfo:
				received_at = received_at.astimezone(dt.timezone.utc).replace(tzinfo=None)
		except Exception:
			received_at = None

	plain_text_parts = []
	html_parts = []
	if msg.is_multipart():
		for part in msg.walk():
			if part.get_content_maintype() == "multipart":
				continue
			content_type = (part.get_content_type() or "").lower()
			payload = part.get_payload(decode=True) or b""
			charset = part.get_content_charset() or "utf-8"
			try:
				text = payload.decode(charset, errors="replace")
			except Exception:
				text = payload.decode("utf-8", errors="replace")

			if content_type == "text/plain":
				plain_text_parts.append(text)
			elif content_type == "text/html":
				html_parts.append(text)
	else:
		# Single part message
		content_type = (msg.get_content_type() or "").lower()
		payload = msg.get_payload(decode=True) or b""
		charset = msg.get_content_charset() or "utf-8"
		try:
			text = payload.decode(charset, errors="replace")
		except Exception:
			text = payload.decode("utf-8", errors="replace")
		if content_type == "text/plain":
			plain_text_parts.append(text)
		elif content_type == "text/html":
			html_parts.append(text)

	plain_text = "\n".join([p for p in plain_text_parts if p]).strip()
	if not plain_text and html_parts:
		plain_text = _strip_html_to_text("\n".join(html_parts))

	thread_root_token = _extract_thread_root_token(msg, plain_text)
	plain_text = _strip_quoted_reply_plaintext(plain_text)

	# Correlate replies within the same thread:
	# - `References` usually contains a chain of message-ids; we use the first token as the thread root.
	# - fall back to `In-Reply-To`, then finally to `Message-ID`.
	correlation_id = None
	# When ingesting replies, many clients set `In-Reply-To` to the *last* email
	# (e.g. our follow-up asking for missing fields) instead of the initial booking.
	# Using `References` first gives us the stable thread root.
	if thread_root_token:
		correlation_id = thread_root_token
	elif references.strip():
		first_token = references.split()[0].strip()
		correlation_id = _strip_angle_brackets(first_token)
	elif in_reply_to.strip():
		correlation_id = in_reply_to.strip()
	else:
		correlation_id = message_id

	return {
		"message_id": message_id,
		"correlation_id": correlation_id,
		"in_reply_to": in_reply_to.strip() if in_reply_to else "",
		"references": references_raw,
		"sender": sender,
		"subject": subject,
		"received_at": received_at.isoformat() if received_at else dt.datetime.utcnow().isoformat(),
		"plain_text": plain_text.strip(),
	}


def _extract_sendgrid_payload(payload: dict) -> dict:
	# Different SendGrid configs send different shapes; we try common ones.
	# Prefer explicit text/plain; fall back to HTML -> text.
	message_id = payload.get("message_id") or payload.get("messageId")
	sender = payload.get("sender") or payload.get("from") or payload.get("from_email") or ""
	subject = payload.get("subject") or ""
	received_at = (
		payload.get("received_at")
		or payload.get("timestamp")
		or payload.get("time")
		or dt.datetime.utcnow().isoformat()
	)

	plain_text = payload.get("text") or payload.get("plain_text") or ""
	html_text = payload.get("html") or ""
	raw_mime = payload.get("raw_mime") or payload.get("rawMime") or ""

	if raw_mime:
		return _parse_raw_mime(raw_mime)

	if not plain_text and html_text:
		plain_text = _strip_html_to_text(html_text)

	return {
		"message_id": message_id,
		"correlation_id": message_id,
		"sender": sender,
		"subject": subject,
		"received_at": received_at,
		"plain_text": plain_text.strip(),
	}


def _extract_gmail_payload(payload: dict) -> dict:
	# Gmail Pub/Sub push payload typically looks like:
	# { "message": { "data": "<base64>"} }
	# The decoded message contains emailAddress/historyId, and usually does NOT include raw content.
	# For this app, we support two modes:
	# 1) "raw_mime" or "plain_text" is already provided by an upstream step.
	# 2) Otherwise, we return a clear error so admins know they must enable raw MIME passthrough.
	raw_mime = payload.get("raw_mime") or payload.get("rawMime") or ""
	plain_text = payload.get("plain_text") or ""

	if raw_mime:
		return _parse_raw_mime(raw_mime)

	if plain_text.strip():
		thread_id = payload.get("thread_id") or payload.get("threadId")
		return {
			"message_id": payload.get("message_id") or payload.get("messageId"),
			"correlation_id": thread_id or payload.get("message_id") or payload.get("messageId"),
			"sender": payload.get("sender") or payload.get("from") or "",
			"subject": payload.get("subject") or "",
			"received_at": payload.get("received_at")
			or payload.get("timestamp")
			or dt.datetime.utcnow().isoformat(),
			"plain_text": plain_text.strip(),
		}

	# Decode for logging/diagnostics
	try:
		msg = payload.get("message") or {}
		data_b64 = msg.get("data")
		if data_b64:
			decoded = base64.b64decode(data_b64).decode("utf-8", errors="replace")
			# Not used for extraction unless raw MIME is present.
			_ = decoded
	except Exception:
		pass

	raise ValueError(
		"Gmail webhook received but no raw MIME/plain text was provided. "
		"To keep setup easy, configure your upstream to POST `raw_mime` or `plain_text` to this endpoint."
	)


def _post_to_frappe_ingest(payload: dict) -> dict:
	frappe_site_url = _env("FRAPPE_SITE_URL", "").rstrip("/")
	if not frappe_site_url:
		raise ValueError("Missing env var `FRAPPE_SITE_URL`")

	method_url = _env(
		"FRAPPE_INGEST_METHOD_URL",
		f"{frappe_site_url}/api/method/fab_cars.fab_cars.api.email_ingestion_api.ingest_email",
	)

	api_key = _env("FRAPPE_API_KEY")
	timeout_s = float(_env("FRAPPE_HTTP_TIMEOUT_SECONDS", "15"))
	retries = int(_env("INGESTION_RETRIES", "3"))

	headers = {"Content-Type": "application/json"}
	if api_key:
		# Frappe API keys are typically sent as: Authorization: token <key>
		headers["Authorization"] = f"token {api_key}"

	last_error = None
	for attempt in range(1, retries + 1):
		try:
			req = urllib.request.Request(
				method_url, data=json.dumps(payload).encode("utf-8"), headers=headers
			)
			with urllib.request.urlopen(req, timeout=timeout_s) as resp:
				body = resp.read().decode("utf-8", errors="replace")
				try:
					resp_json = json.loads(body)
				except json.JSONDecodeError:
					raise RuntimeError(f"Frappe returned non-JSON: {body[:500]}") from None
				if isinstance(resp_json, dict) and resp_json.get("status") == "failed":
					retryable = resp_json.get("retryable", True)
					if retryable:
						raise RuntimeError(resp_json.get("error") or "Email ingestion failed")
				return resp_json
		except urllib.error.HTTPError as e:
			status = getattr(e, "code", None)
			last_error = (
				f"HTTP {status}: {e.read().decode('utf-8', errors='replace') if hasattr(e, 'read') else e!s}"
			)
			if status not in (429, 500, 502, 503, 504) or attempt == retries:
				raise
			time.sleep(2**attempt)
		except Exception as e:
			last_error = str(e)
			if attempt == retries:
				raise
			time.sleep(2**attempt)

	return {"status": "error", "error": last_error}


def _maybe_verify_webhook(handler: BaseHTTPRequestHandler) -> None:
	shared_secret = _env("WEBHOOK_SHARED_SECRET")
	if not shared_secret:
		return
	incoming = handler.headers.get("X-FC-Webhook-Token")
	if not incoming or incoming != shared_secret:
		raise PermissionError("Invalid webhook token")


class WebhookHandler(BaseHTTPRequestHandler):
	server_version = "fab_cars-email-ingestion/0.1"

	def _send_json(self, code: int, payload: dict):
		self.send_response(code)
		self.send_header("Content-Type", "application/json")
		self.end_headers()
		self.wfile.write(json.dumps(payload).encode("utf-8"))

	def do_GET(self):
		if self.path == "/healthz":
			self._send_json(200, {"ok": True})
			return
		self._send_json(404, {"error": "not found"})

	def do_POST(self):
		try:
			_maybe_verify_webhook(self)

			length = int(self.headers.get("Content-Length", "0"))
			raw_body = self.rfile.read(length) if length > 0 else b""
			try:
				payload = json.loads(raw_body.decode("utf-8", errors="replace") or "{}")
			except json.JSONDecodeError:
				# Some providers send form-encoded or raw mime; for now require JSON.
				raise ValueError("Webhook body must be JSON")

			if self.path == "/webhook/sendgrid":
				ingest_payload = _extract_sendgrid_payload(payload)
			elif self.path == "/webhook/gmail":
				ingest_payload = _extract_gmail_payload(payload)
			else:
				self._send_json(404, {"error": "not found"})
				return

			# Minimal shape for Frappe ingestion API
			plain_text = ingest_payload.get("plain_text") or ""
			if not plain_text.strip():
				raise ValueError("No plain text extracted from incoming email")

			# If message_id isn't present, Frappe will compute a deterministic hash fallback.
			req_payload = {
				"message_id": ingest_payload.get("message_id"),
				"sender": ingest_payload.get("sender") or "",
				"subject": ingest_payload.get("subject") or "",
				"received_at": ingest_payload.get("received_at"),
				"plain_text": plain_text,
				# correlation_id is used to correlate replies in the same thread.
				"correlation_id": ingest_payload.get("correlation_id") or None,
				"in_reply_to": ingest_payload.get("in_reply_to") or None,
				"references": ingest_payload.get("references") or None,
			}

			result = _post_to_frappe_ingest(req_payload)

			# Permanent failures (max attempts exceeded) should not cause provider retries.
			if (
				isinstance(result, dict)
				and result.get("status") == "failed"
				and result.get("retryable") is False
			):
				self._send_json(200, {"ok": False, "result": result})
				return

			self._send_json(200, {"ok": True, "result": result})
		except Exception as e:
			self._send_json(
				500,
				{
					"ok": False,
					"error": str(e),
					"trace": traceback.format_exc(limit=5),
				},
			)


def run():
	port = int(_env("WEBHOOK_PORT", "8080"))
	host = _env("WEBHOOK_HOST", "0.0.0.0")
	httpd = HTTPServer((host, port), WebhookHandler)
	print(f"[fab_cars ingestion] listening on http://{host}:{port}")
	httpd.serve_forever()


if __name__ == "__main__":
	run()
