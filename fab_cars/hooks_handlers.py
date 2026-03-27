import frappe


def ensure_references_header_for_threading(email_body):
	"""
	Threading for outbound mail:

	1. **Fab Cars fallback**: `EmailQueue.prepare_email_content` only sets `In-Reply-To`
	   when `in_reply_to` is a `Communication.name` with a stored `message_id`. Inbound
	   mail that never matched a Communication (webhook-only, timing) would otherwise
	   send with no threading headers. `fab_cars.fab_cars.email_ingestion.followup`
	   stashes the customer's RFC Message-ID in `frappe.flags.fab_cars_thread_parent_message_id`
	   for the duration of `frappe.sendmail`; we inject it here if Frappe left
	   `In-Reply-To` empty.

	2. **References**: Some clients weigh `References` heavily; mirror `In-Reply-To`
	   when `References` is missing.
	"""
	try:
		# Do not use `or {}`: an empty dict is a valid `msg_root` in tests; `or {}`
		# would replace it with a detached dict and break header reads.
		msg_root = getattr(email_body, "msg_root", None)
		if msg_root is None:
			msg_root = {}

		parent_mid = frappe.flags.pop("fab_cars_thread_parent_message_id", None)
		if parent_mid and not msg_root.get("In-Reply-To"):
			pid = str(parent_mid).strip()
			if pid:
				if not (pid.startswith("<") and pid.endswith(">")):
					pid = pid.strip("<>")
					pid = f"<{pid}>" if pid else ""
				if pid:
					email_body.set_header("In-Reply-To", pid)
					msg_root = getattr(email_body, "msg_root", None)
					if msg_root is None:
						msg_root = {}

		in_reply_to = msg_root.get("In-Reply-To")
		if in_reply_to and not msg_root.get("References"):
			email_body.set_header("References", str(in_reply_to))
	except Exception:
		# Non-fatal; sending should continue even if header injection fails.
		pass
