# Email → Trip Request Automation (Frappe) — README

> **Project**: Automate creation of `FC Trip Request` documents in ERPNext/Frappe from incoming cab-booking emails.

---

## Table of contents

1. Project overview
2. Architecture & flow (detailed)
3. Frappe doctypes used / created
4. Scripts & key modules (what each file does)
5. Prompt & LLM integration (Anthropic / OpenAI)
6. Data validation & mapping rules
7. Attachment handling (current + future)
8. Key issues encountered & how they were resolved
9. Debugging & observability (how to debug end-to-end)
10. Deployment / scheduling / bench notes
11. Testing & QA checklist
12. Future improvements / TODOs
13. Appendix: useful commands, sample logs, example input/output

---

## 1) Project overview

This project listens to incoming emails (specifically **cab booking** mails) recorded in the Frappe `Communication` doctype, extracts booking information using **Claude** (Anthropic) and converts the structured output into an `FC Trip Request` document.

Goals:

* Remove manual data entry for cab bookings
* Standardize capture of pickup/drop/time/employee/phone
* Persist extracted booking data and parse failures for review
* Robust error handling and traceable logs

Audience: devs who maintain the Frappe site, your supervisor, and future contributors.

---

## 2) Architecture & flow (detailed)

### High-level components

* **Frappe server**: primary runtime and database
* **Communication doctype**: incoming emails are stored here by existing email integration
* **Custom doctype: `FC Extracted Email`**: intermediate storage of the extracted email text + extraction status
* **AI layer: Claude (Anthropic)**: extracts structured JSON from free-text email content
* **Trip Request doctype**: `FC Trip Request` doctype where final structured booking is saved
* **Script(s)**: Python scripts (Frappe server-side) that orchestrate the above
* **Logging**: console prints + Frappe logs + document-level status fields

### End-to-end flow (step-by-step)

1. **Fetch incoming emails**

   * Query `Communication` for received emails, then use Claude to classify whether each email is a cab/taxi/vehicle booking.

2. **Create/append to `FC Extracted Email`**

   * For each candidate email create an `FC Extracted Email` document containing `source_email_id`, `sender`, `subject`, `message_body`, `received_date`, and `communication_link`.

3. **Parse email body**

   * Use `BeautifulSoup` to extract clean plain text from the HTML email body. Normalize whitespace and remove signatures when possible (best-effort); attachments are not parsed in the current version.

4. **Prepare AI prompt**

   * Construct a deterministic prompt instructing Claude to return a strict JSON object with specific fields. Include examples and validation rules in the prompt.

5. **Call Claude**

   * Send prompt and email text to Claude via the Anthropic client. Receive a text response.

6. **Parse AI output**

   * Attempt to parse the Claude response as JSON. If parsing fails, the processor marks `FC Extracted Email.trip_request_status = "Failed"` and stores details in `FC Extracted Email.trip_request_error`.

7. **Transform & insert**

8. **Create `FC Trip Request`**

   * Map extracted JSON into the `FC Trip Request` doctype fields and `insert()` the document.

9. **Handle attachments**

   * Not implemented in the current version: the processor extracts only plain text from the email body.

10. **Update status & logging**

    * Mark `FC Extracted Email.trip_request_status` to `"Successful"` or `"Failed"` (and record an error message on failure).
    * Console/log prints for each major step.

---

## 3) Frappe doctypes used / created

### Existing

* `Communication` – contains incoming email metadata and body
* `FC Trip Request` – target doctype in Frappe

### Custom

* `FC Extracted Email`

  * **Fields (actual in this app)**:

    * `sender` (Data)
    * `subject` (Data)
    * `message_body` (Long Text)
    * `received_date` (Data)
    * `communication_link` (Link -> `Communication`)
    * `trip_request_status` (Select: `Pending`, `Successful`, `Failed`)
    * `trip_request_error` (Long Text)
    * `source_email_id` (Data)
    * `has_multiple_bookings` (Check)
    * `number_of_bookings` (Int)

* **`FC Cab Settings`** (singleton)

  * **`prompt`** (Long Text) — extraction prompt template; must include `{email_text}`.

* **`FC LLM Settings`** (singleton) — **primary place to configure AI providers** (doctype-only at runtime).

  * **`llm_provider`** — `Anthropic` or `OpenAI`.
  * **`anthropic_api_key`** / **`openai_api_key`** — stored as **Password** fields (encrypted in the database).
  * **Model IDs** — classifier and extractor model names per provider (defaults match the code’s built-in fallbacks).
  * **OpenAI** — optional `openai_base_url` (e.g. Azure OpenAI or compatible gateways) and `openai_timeout_seconds`.

  Runtime configuration is sourced from **`FC LLM Settings` only** (no `frappe.local.conf` / site_config fallbacks).

* **`FC Ingestion Settings`** (singleton)
  * `max_attempts` — maximum number of extraction attempts for a single `FC Raw Email Log`.

* **`FC Raw Email Log`** — audit + idempotency for the event-driven ingestion API (`ingest_email`): raw metadata, `plain_text`, status, errors, link to `FC Trip Request`.

---

## 4) Scripts & key modules

### Files (logical grouping)

* `fab_cars/doctype/fc_extracted_email/fc_extracted_email.py` — classifier + extraction + `FC Trip Request` creation (`process_payload_to_trip_request`; legacy `Communication` polling may still exist but is disabled via hooks when using ingestion only).
* `fab_cars/llm/llm_client.py` — **provider-agnostic** LLM calls (Anthropic or OpenAI) using **`FC LLM Settings` only**.
* `BeautifulSoup` — optional; used for legacy HTML email cleanup when reading `Communication`.
* `FC Cab Settings.prompt` — extraction prompt template (must include `{email_text}`).
* `FC LLM Settings` — API keys and model names for Anthropic/OpenAI (Desk UI).
* Attachments — not processed yet (the current version only sends email body text to Claude).

### Core processor (what to look for in code)

* `process_received_emails_to_trip_requests()` — end-to-end flow:
  * fetch received `Communication` docs
  * classifier Claude call: cab/taxi booking or not
  * create `FC Extracted Email`
  * extraction Claude call using `FC Cab Settings.prompt`
  * parse JSON and insert `FC Trip Request` (+ `FC Multiple Booking` child rows)

Failures are handled defensively:
* if Claude/extraction fails or output is not JSON, the processor sets `FC Extracted Email.trip_request_status = "Failed"` and writes details into `FC Extracted Email.trip_request_error`.

---

## 5) Prompt & LLM integration (Anthropic / OpenAI)

### Prompt Design Principles

* Use a **single, clear instruction**: produce **strict JSON** with exact keys and types.
* Provide **examples** (1–2 short examples) in the prompt so Claude learns the shape.
* State **constraints** explicitly: e.g., `pickup_datetime` must be ISO 8601 or `null`.
* Ask Claude to return only JSON and nothing else.
* Set a token limit on Claude call if supported.

### Example prompt (representative)

```text
You are a data extraction assistant. Given the plain text of an email, output ONLY a single JSON object (no preface, no comments) with the following keys:
- summary (string or null)
- vehicle_type (string or null)
- city (string or null)
- miscellaneous_requirements (string or null)
- duty_type (string or null)
- request_type (string or null)
- special_request (string or null)
- remarks (string or null)
- notes (string or null)
- booked_by (object or null) with keys: name, email, number
- billed_to (object or null) with keys: name, email, number
- point_of_contact (object or null) with keys: name, email, number
- has_multiple_bookings (boolean)
- number_of_bookings (integer)
- bookings (array of booking objects)

Where each booking object contains:
- passenger_name (string or null)
- passenger_number (string or null)
- pickup_location (string or null)
- drop_location (string or null)
- pickup_date (string or null)
- pickup_time (string or null)
- drop_time (string or null)
- reporting_time (string or null)
- passenger_specific_request (string or null)
If a field cannot be determined, use null.

Email text:
"""
<PUT CLEAN EMAIL TEXT HERE>
"""

Return the JSON now.
```

### LLM client notes (`llm_client.py`)

* Configure **Anthropic** or **OpenAI** in **`FC LLM Settings`** (recommended). API keys are encrypted Password fields.
* Default models (if you leave the model fields blank in the form, the code still applies built-in defaults): Anthropic `claude-4-sonnet-20250514`, OpenAI `gpt-4o-mini` — override per field in `FC LLM Settings` as needed.
* The extraction prompt is stored in singleton **`FC Cab Settings`** (`prompt`); the processor replaces `{email_text}` with the cleaned email body.
* The app expects the model to return **JSON**; parsing or LLM failures mark `FC Extracted Email.trip_request_status = "Failed"` and/or `FC Raw Email Log.status = Failed` with `last_error` where applicable.

---

## 6) Data validation & mapping rules

When mapping extracted JSON to `FC Trip Request` fields, the processor assumes Claude returns a JSON object in the shape that `process_received_emails_to_trip_requests()` expects.

If the Claude call fails or the extraction output is not valid JSON, the processor sets:
* `FC Extracted Email.trip_request_status = "Failed"`
* `FC Extracted Email.trip_request_error = <details>`

---

## 7) Attachment handling (current + future)

### Current state

* Attachments are not processed by the current implementation. The processor extracts plain text from the email HTML (`Communication.content`) and sends it to Claude.

### Recommended implementation
* In the future, implement attachment saving (`File` docs) and/or OCR for screenshots, then include extracted text back into Claude for better parsing.

---

## 8) Key issues encountered & how they were resolved

Below are the concrete issues you reported and the exact fixes applied. Keep these verbatim in the README for traceability.

### Issue: Claude token usage showing 0 in responses

**Symptoms**: After calling Claude, the response object didn't show token usage (0s) in logs.
**Root cause & reasoning**:

* Claude/Anthropic client returns different metadata fields compared to OpenAI. Code expecting OpenAI-style `.usage` or `.get('usage')` would fail or yield zeros. Also older/trial keys or certain response types might omit usage fields.
  **Fix applied**:
* Update the processor logic to never rely on OpenAI-specific response metadata. Instead:

  * Save the raw extraction JSON into `FC Trip Request.ai_json_response` (and store parse errors on `FC Extracted Email.trip_request_error`).
  * Log request size and response size locally (len of strings) to approximate token counts for debugging.
  * Add defensive code: `response_metadata = getattr(response, 'metadata', None) or response` and then inspect keys safely.

### Issue: `FC Trip Request` not created while `FC Extracted Email` exists

**Symptoms**: `FC Extracted Email` documents were being created, but `FC Trip Request` creation failed silently.
**Root cause**:

* Uncaught exceptions during validation or insert (e.g., `InvalidDocTypeError` or mapping key missing) were swallowed, or `autocommit` behaviour in Frappe prevented the insert from persisting.
  **Fix applied**:
* Add `try/except` around mapping + creation and save stacktrace to `FC Extracted Email.trip_request_error`.
* Use `trip_doc.insert()` followed by `frappe.db.commit()` to ensure persistence in non-HTTP contexts (scripts run from bench console need explicit commit).
* Add checks for mandatory fields and early return with clear status and message.

### Issue: Duplicate or empty AI responses

**Symptoms**: AI returned empty strings or non-JSON text.
**Cause**: Prompt ambiguous, or Claude returned a short reply instead of JSON.
**Fix applied**:

* Strengthened prompt to include "Return ONLY JSON" and added 2 examples
* Implement fallback: if parsing fails, call Claude again with a stricter directive (wrap email text in triple quotes, ask to output JSON strictly) and log both attempts.
* Add Post-check: ensure presence of at least one of the critical fields (`pickup_location` or `drop_location`) after parsing else mark for manual review.

### Issue: Bench process hanging on long tasks

**Symptoms**: Long-running script calls blocked bench worker or terminal.
**Cause**: synchronous calls to network (AI) without timeouts, large attachments, or running within limited worker slots.
**Fix applied**:

* Add request timeouts/retries around the Claude calls in `process_received_emails_to_trip_requests()`.
* Use `frappe.enqueue()` for processing each email as a background job when running under production with workers, or run the script in a non-blocking thread when called from bench console.
* Put a hard cap on attachments processed per email (configurable) and stream large file uploads rather than holding in memory.

### Issue: Debugging from console unclear

**Symptoms**: Developers couldn't easily reproduce errors or see stack traces.
**Fix applied**:

* Add a `--verbose` flag in the script that sets `frappe.logger.setLevel(logging.DEBUG)` and `print()`s stepwise progress.
* Write the last exception traceback into `FC Extracted Email.trip_request_error` so it's visible in Desk.
* Add a `frappe.get_doc('FC Extracted Email', name).print_format()` helper for quick inspection.

### Issue: `source_emailid` mapping problems

**Symptoms**: Incorrect or missing link to original `Communication`.
**Fix applied**:

* Use stable unique key `communication.name` (the docname) as `source_emailid`. When fetching, ensure the script uses `comm_doc.name` (not `comm_doc.reference` or `id`).
* Save `Communication` link (`communication_link`) and `source_email_id` in `FC Extracted Email` for traceability.

---

## 9) Debugging & observability

### Logs to check

* Frappe error log (bench logs)
* `FC Extracted Email` documents (`trip_request_status`, `trip_request_error`)
* Console STDOUT if run manually

### Helpful commands

* Run interactive function from bench:

```bash
bench --site yoursite execute fab_cars.fab_cars.doctype.fc_extracted_email.fc_extracted_email.process_received_emails_to_trip_requests --args "[]"
```

* Inspect an `FC Extracted Email` doc from bench console:

```python
import frappe
doc = frappe.get_doc('FC Extracted Email', 'NAME')
print(doc.trip_request_status)
print(doc.trip_request_error)
print(doc.has_multiple_bookings)
print(doc.number_of_bookings)
```

* Create a `FC Trip Request` manually for debugging:

```python
trip = frappe.new_doc('FC Trip Request')
trip.trip_name = 'DEBUG_TRIP_1'
trip.city = 'Test City'
trip.required_vehicle_type = 'Taxi'
trip.remarks = 'Debug'
trip.mail_link = 'Communication-0000000'
trip.email_message_body = 'Test email body'
trip.ai_json_response = '{}'
trip.ai_token_usage = 0
trip.append(
	'table_lftf',
	{
		'passenger_name': 'Test Passenger',
		'passenger_number': '0000000000',
		'pickup_location': 'A',
		'drop_location': 'B',
		'pickup_date': '',
		'pickup_time': '',
		'drop_time': '',
		'reporting_time': '',
		'passenger_special_request': '',
	},
)
trip.insert()
frappe.db.commit()
```

### Common failure points & how to inspect

* **AI returned non-JSON**: check `FC Extracted Email.trip_request_error`.
* **Datetime parsing issues**: dump `parsed_json['pickup_datetime']` and run `frappe.utils.get_datetime` on it.
* **Insert failing**: wrap creation with `frappe.log_error(str(e), 'trip_creation_failed')` and check `logs/error-log`.

---

## 10) Deployment / scheduling / bench notes

### Running manually

* Use the `bench execute` method described above for ad-hoc runs.

### Scheduling (cron) / recommended setup

* Preferred: use `frappe.enqueue()` with a short scheduler job to avoid long blocking runs. Schedule a small worker task every `1-5` minutes depending on email volume.
* Alternatively, set up a `cron` job on the server calling a bench execute command; example crontab:

```cron
*/5 * * * * cd /path/to/frappe-bench && bench --site yoursite execute fab_cars.fab_cars.doctype.fc_extracted_email.fc_extracted_email.process_received_emails_to_trip_requests >> /var/log/email_processor.log 2>&1
```

**Important**: If using cron do not forget `frappe.db.commit()` in code paths where changes must persist.

### Resource considerations

* Keep AI requests batched sensibly if you have rate limits.
* Monitor worker slots and memory for large emails / heavy Claude calls.

---

## 11) Testing & QA checklist

* [ ] Unit tests for HTML-to-plain-text extraction (BeautifulSoup) behavior
* [ ] Unit tests for Claude extraction JSON parsing + failure handling
* [ ] Integration test: run script on a sample mailbox replica
* [ ] End-to-end test: ensure a real email creates an `FC Trip Request` in a test site
* [ ] Fuzzy match tests for mapping `employee_name` → Employee doctype
* [ ] Duplicate detection tests

---

## 12) Future improvements / TODOs

* Full implementation of attachments → `File` docs + linking
* OCR pipeline for screenshots to extract addresses/dates as fallback
* Improve fuzzy matching for Employee mapping (use trigram similarity or external search index)
* Add an Admin UI in Desk to review `FC Extracted Email` items that failed parsing
* Add a small ML model or rule-based post-processor to normalize free-text pickup/drop locations into more canonical names

---

## 13) Appendix: useful commands, sample logs, example input/output

### Example: raw email (input)

```
Subject: Cab booking
From: employee@example.com
Date: 2025-10-15 08:23

Hi,
Please arrange a cab from Rama Metro Life, C Tower (Opp D Mart) to Bel apartment on 16-10-2025 at 9:30 AM for Rohit (phone: +91-98765-43210).
Regards,
Employee Name
```

### Example: ideal Claude JSON response (output)

```json
{
  "summary": "Cab booking request",
  "vehicle_type": "Taxi",
  "city": "Delhi",
  "miscellaneous_requirements": null,
  "duty_type": null,
  "request_type": null,
  "special_request": null,
  "remarks": null,
  "notes": null,
  "booked_by": {
    "name": "Rohit",
    "email": null,
    "number": "+919876543210"
  },
  "billed_to": {
    "name": null,
    "email": null,
    "number": null
  },
  "point_of_contact": {
    "name": null,
    "email": null,
    "number": null
  },
  "has_multiple_bookings": false,
  "number_of_bookings": 1,
  "bookings": [
    {
      "passenger_name": "Rohit",
      "passenger_number": "+919876543210",
      "pickup_location": "Rama Metro Life, C Tower, Opposite D Mart",
      "drop_location": "Bel apartment",
      "pickup_date": "2025-10-16",
      "pickup_time": "09:30",
      "drop_time": null,
      "reporting_time": null,
      "passenger_specific_request": null
    }
  ]
}
```

### Example: final Trip Request mapping to doctype fields

* `FC Trip Request.summary` ← `summary`
* `FC Trip Request.required_vehicle_type` ← `vehicle_type`
* `FC Trip Request.city` ← `city`
* `FC Trip Request.miscellaneous_requirements` ← `miscellaneous_requirements`
* `FC Trip Request.duty_type` ← `duty_type`
* `FC Trip Request.request_type` ← `request_type`
* `FC Trip Request.special_request` ← `special_request`
* `FC Trip Request.remarks` ← `remarks`
* `FC Trip Request.notes` ← `notes`
* `FC Trip Request.booked_by_*` ← `booked_by.{name,email,number}`
* `FC Trip Request.billed_to_*` ← `billed_to.{name,email,number}`
* `FC Trip Request.poc_*` ← `point_of_contact.{name,email,number}`
* `FC Trip Request.table_lftf[]` (type `FC Multiple Booking`) ← each element of `bookings[]` into:
  * `passenger_name`, `passenger_number`
  * `pickup_location`, `drop_location`
  * `pickup_date`, `pickup_time`, `drop_time`, `reporting_time`
  * `passenger_specific_request`

---

## Contributing / contact

If you need changes, open an issue in the repository or contact the maintainer (Sohail) directly. Include the `FC Extracted Email` doc id when reporting a specific failing email.

---

## License

Include your chosen license here (e.g., MIT) — or copy the organization standard license.

---

*End of README*
