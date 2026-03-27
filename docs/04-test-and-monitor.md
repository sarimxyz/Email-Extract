# Test and Monitor

## 1) Send a test webhook

Choose one option:

### Production (recommended)
Send a POST request to the Frappe endpoints in `03-setup-webhook-ingestion.md`:
- SendGrid: `https://YOUR-SITE/api/method/fab_cars.fab_cars.api.email_provider_webhook_api.sendgrid_webhook`
- Gmail: `https://YOUR-SITE/api/method/fab_cars.fab_cars.api.email_provider_webhook_api.gmail_webhook`

If the request is valid, the endpoint responds with:
- `{"ok": true, ...}` on success
- `{"ok": false, "error": "..."}` on failure

### Local/dev (optional standalone server)
1. Start the ingestion service (webhook server).
2. Send a single test POST request to:
   - SendGrid: `http://<host>:<port>/webhook/sendgrid`
   - Gmail: `http://<host>:<port>/webhook/gmail`

If the request is valid, the standalone server responds with JSON:
- `{ "ok": true, "result": ... }`
- or `{ "ok": false, "result": ... }`

HTTP `500` means the standalone server failed to process the webhook itself (invalid JSON, missing payload fields, etc.).

## 2) Check `FC Raw Email Log`

Open **`FC Raw Email Log`** and locate the newly created record.

Status meanings:

- `Pending`: ingestion is being attempted (including retries)
- `Needs Info`: the app is missing key booking details (check `last_error`)
- `Successful`: extraction produced an `FC Trip Request`
- `Failed`: extraction/LLM/JSON parsing failed and `max_attempts` was exceeded
- `Skipped`: the classifier decided it is not a cab/taxi/vehicle booking

The `last_error` field contains the most useful failure detail.

## 3) Check `FC Trip Request`

Open **`FC Trip Request`** for the linked record.

You should see fields populated from the extracted JSON, including:

- city, required vehicle type, request type
- booked-by details and passenger + pickup/drop/time fields

## 4) Use the `email-extraction` page (monitoring)

Go to the Desk Page **`email-extraction`** to view:

- a table of recent emails and their extraction/trip status
- number cards for totals in a date range

If the data table shows “No data found”, verify:
- the webhook is reaching the ingestion service
- the ingestion service can reach Frappe
- your LLM and prompt settings are configured

