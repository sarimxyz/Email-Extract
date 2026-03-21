# Setup Webhook Email Ingestion

This app converts **cab/taxi/vehicle booking emails** into `FC Trip Request` records in Frappe.

It does that by:
1. Receiving webhook events from your email provider (Gmail or SendGrid).
2. Extracting/normalizing plain text.
3. Running the app’s classification + LLM extraction.
4. Writing `FC Raw Email Log` and then creating `FC Trip Request` (or `Failed` / `Needs Info`).

## No extra process in production (recommended)

For production, do **not** run `webhook_server.py` as a separate daemon.
Instead, configure your email provider to POST directly to the Frappe endpoints below.

This makes the ingestion logic run inside the normal `bench start` web workers, with no extra manual supervision.

## Prerequisites (do these once in Desk)

1. `FC LLM Settings` (singleton)
   - Set `llm_provider` (Anthropic or OpenAI)
   - Add the matching API key (encrypted Password field)
   - Ensure classifier + extractor model IDs are set (defaults exist, but keep them consistent)
2. `FC Cab Settings` (singleton)
   - Set `prompt`
   - **Critical:** the prompt must include the placeholder `{email_text}`
3. `FC Ingestion Settings` (singleton)
   - Set `max_attempts` (start with `3` to `5`)
   - (Optional) enable `send_followup_email` if you want the app to email the sender when it needs missing booking details

## Webhook endpoints (copy/paste)

Replace `https://YOUR-SITE` with your Frappe site base URL.

SendGrid:
`https://YOUR-SITE/api/method/fab_cars.fab_cars.api.email_provider_webhook_api.sendgrid_webhook`

Gmail (Pub/Sub push):
`https://YOUR-SITE/api/method/fab_cars.fab_cars.api.email_provider_webhook_api.gmail_webhook`

Both endpoints:
- expect `Content-Type: application/json`
- expect the POST body to be the **provider webhook JSON**
  - i.e., the same JSON you would have sent to the standalone `webhook_server.py`

### Optional security (recommended)

If you set `WEBHOOK_SHARED_SECRET` in your Frappe/bench environment, the endpoints will require:
- `X-FC-Webhook-Token: <same secret value>`

## Test the integration (fastest way to confirm)

### SendGrid test payload

SendGrid endpoint:
`https://YOUR-SITE/api/method/fab_cars.fab_cars.api.email_provider_webhook_api.sendgrid_webhook`

Run:
```bash
curl -sS -X POST "https://YOUR-SITE/api/method/fab_cars.fab_cars.api.email_provider_webhook_api.sendgrid_webhook" \
  -H "Content-Type: application/json" \
  -d '{
    "message_id":"<msg-1@example.com>",
    "sender":"somebody@example.com",
    "subject":"Cab booking",
    "received_at":"2026-03-19T10:00:00Z",
    "text":"plain text of the email"
  }'
```

Expected response:
- `{"ok": true, ...}` on success
- `{"ok": false, "error": "..."}` on failure

### Gmail test payload (plain_text mode)

Gmail endpoint:
`https://YOUR-SITE/api/method/fab_cars.fab_cars.api.email_provider_webhook_api.gmail_webhook`

Run:
```bash
curl -sS -X POST "https://YOUR-SITE/api/method/fab_cars.fab_cars.api.email_provider_webhook_api.gmail_webhook" \
  -H "Content-Type: application/json" \
  -d '{
    "messageId":"<msg-2@example.com>",
    "sender":"somebody@example.com",
    "subject":"Cab booking",
    "received_at":"2026-03-19T10:00:00Z",
    "plain_text":"plain text of the email"
  }'
```

For best accuracy with Gmail, enable upstream raw MIME passthrough and send `raw_mime` (or `rawMime`) instead of `plain_text`.

## Verify results in Frappe

1. Open `FC Raw Email Log`
   - A new record should appear quickly.
   - `status` will become one of: `Pending`, `Successful`, `Failed`, `Needs Info`, or `Skipped`.
2. If `Successful`, open the linked `FC Trip Request`.

## If something fails

- Check `FC Raw Email Log.last_error` for the exact error message.
- Re-check `FC Cab Settings.prompt` contains `{email_text}`.
- If the status is `Needs Info`: open `FC Raw Email Log` and read `last_error` (it lists the missing details). Reply with those details (or resend the webhook) so the app can create the trip.

## Optional: standalone ingestion server (local/dev only)

If you still want the old “separate HTTP process” model for testing, you can run:
```bash
python -m fab_cars.fab_cars.email_ingestion_service.webhook_server
```

But for production “no manual intervention”, use the Frappe endpoints above.

Note for local testing: the standalone server also needs `plain_text` or `raw_mime` for Gmail (it won’t magically extract the full email text from headers only).

