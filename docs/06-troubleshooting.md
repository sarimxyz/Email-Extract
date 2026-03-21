# Troubleshooting

Use this when emails show up as `Failed` or trips are not created.

## 1) Nothing appears in `FC Raw Email Log`

Check:

- Pick your setup mode and confirm the provider is calling the right URL:
  - Production (recommended): POST to the Frappe endpoints in `03-setup-webhook-ingestion.md`
  - Local/dev (optional): start the standalone webhook server, then POST to:
    - `/webhook/sendgrid` or `/webhook/gmail`
- The webhook payload is valid JSON and includes usable email text:
  - `text` / `html` (SendGrid) or `plain_text` / `raw_mime` (Gmail)

Then verify ingestion can reach Frappe (standalone server mode only):
- It calls the whitelisted method `ingest_email` using `FRAPPE_API_KEY`.

## 2) `FC Raw Email Log` shows `Failed` with LLM/config errors

Most common causes:

- Missing `FC LLM Settings` singleton values (provider, model IDs, API key)
- `FC Cab Settings.prompt` does not include `{email_text}`

Fix the Doctypes in Desk, then resend the same webhook event.

## 3) Status is `Pending` for a while

The ingestion service retries calls to Frappe for temporary failures.

Eventually:

- It becomes `Successful`, `Needs Info`, `Failed`, or `Skipped`
- `last_error` becomes the primary source of truth

## 4) Status is `Needs Info`

The app recognized a booking request, but it is missing one or more required details (for example pickup/drop location, date/time, or your contact phone).

Open `FC Raw Email Log` and read `last_error` to see exactly what is missing. If `send_followup_email` is enabled, the app may have already emailed the sender—reply with the missing details (ideally in the same email thread).

## 5) JSON parsing errors from the LLM

The extractor expects the LLM to return strict JSON.

Fix by:

1. Editing `FC Cab Settings.prompt` to ensure it clearly instructs strict JSON output.
2. Ensuring the returned keys and types match what the app maps into `FC Trip Request`.

After fixing, resend the email webhook again.

## 6) “Max attempts exceeded”

That means extraction failed repeatedly up to:

- `FC Ingestion Settings.max_attempts`

Set `max_attempts` higher only if you expect transient issues. Otherwise, fix the prompt/models.

