# Data Model & FAQ

This app creates and updates these main DocTypes.

## `FC Raw Email Log`

This is the audit/idempotency record for every inbound email event.

Important fields:

- `message_id` / `email_hash`: used to deduplicate events (each inbound mail normally maps to `FCR_{sha256(message_id)}`)
- `thread_root_message_id`: RFC Message-ID of the **first** inbound mail in the booking thread (used for follow-up email threading; `message_id` holds the **latest** inbound id)
- `ingested_message_ids`: newline-separated Message-IDs already merged into this log (idempotency for replies)
- `plain_text`: cleaned text sent to the LLM extractor; for thread replies this may contain multiple segments separated by `---` (merged into **one** log)
- `correlation_id`: groups emails that belong to the same conversation/thread. After a missing-details follow-up, it is set to the raw log name (`FCR_…`) so replies can be correlated.

**Thread replies (one log per booking):** A new inbound message usually creates a **new** `FC Raw Email Log` (`FCR_{hash(new message_id)}`). To continue the **same** booking instead of losing the first email’s context, the user’s reply must be matched to the existing log. The app does that when either:

1. The webhook passes `correlation_id` equal to the existing raw log name (`FCR_…`), or  
2. The email body still contains the hidden token from our follow-up: `FC-THREAD-ROOT:FCR_<same_log_name>` (quoted replies usually include this).

Then the new body is **appended** to the existing log’s `plain_text` and extraction sees the full thread.
- `status`:
  - `Pending`
  - `Needs Info`
  - `Successful`
  - `Failed`
  - `Skipped`
- `attempt_count`: how many extraction attempts were made
- `last_error`: the latest failure detail (use this first when debugging)
- `trip_request`: link to the created trip (when successful)

## `FC Trip Request`

Created when the classifier decides the email is cab/taxi/vehicle related.

It stores extracted booking information (city, pickup/drop, booked-by/poc details, and one or more booking rows).

## `FC Multiple Booking` (child table)

`FC Trip Request.table_lftf[]` is populated from the `bookings[]` array returned by the LLM extraction JSON.

## FAQ

### Will this create duplicate trips?

No. The app is idempotent:

- If the same `message_id` (or computed hash) is received again, the app will update the existing `FC Raw Email Log` and avoid creating a second trip.

### What happens for “non-cab” emails?

The classifier sets:

- `FC Raw Email Log.status = Skipped`
- no `FC Trip Request` is created

### What if the LLM returns invalid JSON?

The app marks:

- `FC Raw Email Log.status = Failed`
- `last_error` explains the parse/extraction failure

Fix by adjusting `FC Cab Settings.prompt` (or LLM models) and retry by sending the webhook again.

### What if the app says `Needs Info`?

That means the email looked like a booking request, but the app could not find one or more required details (like pickup/drop, date/time, or your contact phone).

The app will show the missing details in `FC Raw Email Log.last_error`. If `send_followup_email` is enabled in `FC Ingestion Settings`, it may also email the sender asking for the missing information.

