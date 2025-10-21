# Email → Trip Request Automation (Frappe) — README

> **Project**: Automate creation of `Trip Request` documents in ERPNext/Frappe from incoming cab-booking emails.

---

## Table of contents

1. Project overview
2. Architecture & flow (detailed)
3. Frappe doctypes used / created
4. Scripts & key modules (what each file does)
5. Prompt & Claude integration
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

This project listens to incoming emails (specifically **cab booking** mails) recorded in the Frappe `Communication` doctype, extracts booking information (pickup, drop, date/time, employee, contact, notes, attachments) using **Claude** (Anthropic) and converts the structured output into a `Trip Request` document.

Goals:

* Remove manual data entry for cab bookings
* Standardize capture of pickup/drop/time/employee/phone
* Persist attachments or references
* Robust error handling and traceable logs

Audience: devs who maintain the Frappe site, your supervisor, and future contributors.

---

## 2) Architecture & flow (detailed)

### High-level components

* **Frappe server**: primary runtime and database
* **Communication doctype**: incoming emails are stored here by existing email integration
* **Custom doctype: `Extracted Email New`**: intermediate storage of the raw email body + extraction status + AI output
* **AI layer: Claude (Anthropic)**: extracts structured JSON from free-text email content
* **Trip Request doctype**: target doctype where final structured booking is saved
* **Script(s)**: Python scripts (Frappe server-side) that orchestrate the above
* **Logging**: console prints + Frappe logs + document-level status fields

### End-to-end flow (step-by-step)

1. **Fetch incoming emails**

   * Query `Communication` for messages with subject match (e.g. "cab booking") or other filters (status `'Sent'`/`'Received'` depending on setup).

2. **Create/append to `Extracted Email New`**

   * For each fetched email create an `Extracted Email New` document containing `source_emailid`, `subject`, `from`, `raw_html`, `raw_text`, `received_on`, and a `status` field (`pending`, `ai_processed`, `error`).

3. **Parse email body**

   * Use `BeautifulSoup` to extract clean text from HTML email body. Normalize whitespace, remove signatures when possible (a best-effort pattern), keep attachments metadata.

4. **Prepare AI prompt**

   * Construct a deterministic prompt instructing Claude to return a strict JSON object with specific fields. Include examples and validation rules in the prompt.

5. **Call Claude**

   * Send prompt and email text to Claude via the Anthropic client. Receive a text response.

6. **Parse AI output**

   * Attempt to parse the response as JSON. If parsing fails, run fallback attempts (stricter prompt, or regex extraction). Save raw AI output in `Extracted Email New.ai_output`.

7. **Validate & transform**

   * Validate mandatory fields (e.g., `pickup_location`, `drop_location` and `pickup_datetime` where applicable).
   * Normalize `pickup_datetime` into a timezone-aware ISO format used by Frappe.

8. **Create `Trip Request`**

   * Map validated fields into the `Trip Request` doctype fields and `insert()` the document.
   * Save mapping metadata: `extracted_email_id`, `ai_confidence` (if available), `created_by_script` flags.

9. **Handle attachments**

   * Save attachment references to the `Trip Request` (or attach files to the Frappe file system). If inline images are present, create file docs.

10. **Update status & logging**

    * Mark `Extracted Email New.status = 'ai_processed'` or `'error'` with an error message.
    * Console/log prints for each major step.

---

## 3) Frappe doctypes used / created

### Existing

* `Communication` – contains incoming email metadata and body
* `Trip Request` – target doctype in ERPNext

### Custom

* `Extracted Email New`

  * **Fields (recommended)**:

    * `source_emailid` (Data/Link): link back to `Communication` (unique id)
    * `subject` (Data)
    * `from` (Data)
    * `received_on` (Datetime)
    * `raw_html` (Text)
    * `raw_text` (Text)
    * `ai_prompt` (Text)
    * `ai_output` (Text)
    * `ai_parsed` (JSON)
    * `status` (Select): `pending`, `ai_processed`, `error`, `skipped`
    * `error_message` (Text)
    * `trip_request_ref` (Link) — created Trip Request doc name
    * `attachments` (Table / Child table) – list of files metadata

---

## 4) Scripts & key modules

### Files (logical grouping)

* `email_processor.py` — orchestrates fetching, parsing, saving to `Extracted Email New`, calling AI, validation and Trip Request creation.
* `utils/email_parsing.py` — email-specific parsing utilities using BeautifulSoup, signature trimming heuristics.
* `utils/ai_client.py` — wrapper for Claude (Anthropic) client call including rate-limiting and retries.
* `utils/validation.py` — normalization & validation functions (datetime parsing, phone normalization, location heuristics).
* `utils/attachments.py` — saving files into Frappe file system and linking to Trip Request.

### Key functions (pseudocode)

* `fetch_unprocessed_emails(filter)` — returns list of `Communication` docs
* `create_extracted_email_doc(comm_doc)` — creates `Extracted Email New` doc and returns it
* `clean_email_body(raw_html)` — returns `raw_text`
* `build_claude_prompt(clean_text)` — returns string prompt
* `call_claude(prompt)` — returns AI text response
* `parse_ai_response_to_json(ai_text)` — returns dict or raises
* `validate_and_map_to_trip(parsed_json)` — returns `trip_data` or raises validation error
* `create_trip_request(trip_data)` — inserts Trip Request and returns doc
* `attach_files(trip_doc, files)` — link attachments

Include defensive `try/except` and patch failures to `Extracted Email New.error_message`.

---

## 5) Prompt & Claude integration

### Prompt Design Principles

* Use a **single, clear instruction**: produce **strict JSON** with exact keys and types.
* Provide **examples** (1–2 short examples) in the prompt so Claude learns the shape.
* State **constraints** explicitly: e.g., `pickup_datetime` must be ISO 8601 or `null`.
* Ask Claude to return only JSON and nothing else.
* Set a token limit on Claude call if supported.

### Example prompt (representative)

```text
You are a data extraction assistant. Given the plain text of an email, output ONLY a single JSON object (no preface, no comments) with the following keys:
- pickup_location (string or null)
- drop_location (string or null)
- pickup_datetime (string in ISO 8601, timezone-aware, or null)
- employee_name (string or null)
- phone_number (string or null, digits, include country code if present)
- seats_required (integer or null)
- additional_notes (string or null)
- attachments_present (boolean)
If a field cannot be determined, use null.

Email text:
"""
<PUT CLEAN EMAIL TEXT HERE>
"""

Return the JSON now.
```

### Claude client notes

* We *fully* use Claude (Anthropic) instead of OpenAI — ensure your Anthropic client is configured and keys are in environment variables (e.g. `ANTHROPIC_API_KEY`).
* The wrapper `ai_client.py` should:

  * Log request/response sizes (for debugging token usage)
  * Save the raw prompt and raw response to `Extracted Email New` for traceability
  * Apply a retry strategy: `try up to 2 more times with a stricter prompt` if response isn't valid JSON

---

## 6) Data validation & mapping rules

When mapping extracted JSON to `Trip Request` fields, apply the following rules:

* **Mandatory fields**: `pickup_location`, `drop_location`. If missing — mark `status='error'` and leave for manual review.
* **Datetime parsing**:

  * Accept formats: `DD-MM-YYYY`, `DD/MM/YYYY`, `YYYY-MM-DD`, with optional time.
  * If *date* present but no *time*, default to company policy time (e.g., `09:00`) or `null` per policy.
  * Always convert to ISO 8601 with timezone (use server timezone or email timezone if provided).
* **Phone numbers**: strip all non-digit chars, preserve leading `+` if present. Validate length (min 7 digits).
* **Employee identification**: try to map `employee_name` to an existing Employee doctype by fuzzy match; if multiple matches, do not create trip automatically — mark for manual review.
* **Duplicate detection**: check for existing `Trip Request` with same `pickup_datetime`, `pickup_location`, and `employee` within a time-window (e.g., 30 minutes) to avoid duplicate creation.

---

## 7) Attachment handling (current + future)

### Current state

* Attachments are detected from `Communication` metadata and references are saved in `Extracted Email New.attachments` as metadata (filename, size, content-type).
* Full file saving into Frappe `File` doctype or linking to `Trip Request` is a stub (implementation pending), though the code path collects and logs attachments.

### Recommended implementation

* For each attachment:

  * Save to Frappe files using `frappe.get_doc({"doctype": "File", "file_name": filename, "content": base64_content, "attached_to_doctype": "Trip Request", "attached_to_name": trip_doc.name}).insert()`
  * For large files or PDFs, consider storing in S3 / external and keep reference URL in the Trip Request.
* If attachment is an image of a booking screenshot, optionally send to OCR (Tesseract or cloud OCR) to extract additional info as fallback.

---

## 8) Key issues encountered & how they were resolved

Below are the concrete issues you reported and the exact fixes applied. Keep these verbatim in the README for traceability.

### Issue: Claude token usage showing 0 in responses

**Symptoms**: After calling Claude, the response object didn't show token usage (0s) in logs.
**Root cause & reasoning**:

* Claude/Anthropic client returns different metadata fields compared to OpenAI. Code expecting OpenAI-style `.usage` or `.get('usage')` would fail or yield zeros. Also older/trial keys or certain response types might omit usage fields.
  **Fix applied**:
* Standardize the wrapper `ai_client.py` to never rely on OpenAI-specific fields. Instead:

  * Save full raw response JSON into `Extracted Email New.ai_output`.
  * Log request size and response size locally (len of strings) to approximate token counts for debugging.
  * Add defensive code: `response_metadata = getattr(response, 'metadata', None) or response` and then inspect keys safely.

### Issue: `Trip Request` not created while `Extracted Email New` exists

**Symptoms**: `Extracted Email New` documents were being created, but Trip Request creation failed silently.
**Root cause**:

* Uncaught exceptions during validation or insert (e.g., `InvalidDocTypeError` or mapping key missing) were swallowed, or `autocommit` behaviour in Frappe prevented the insert from persisting.
  **Fix applied**:
* Add `try/except` around mapping + creation and save stacktrace to `Extracted Email New.error_message`.
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

* Add request timeouts and retries in `ai_client.py`.
* Use `frappe.enqueue()` for processing each email as a background job when running under production with workers, or run the script in a non-blocking thread when called from bench console.
* Put a hard cap on attachments processed per email (configurable) and stream large file uploads rather than holding in memory.

### Issue: Debugging from console unclear

**Symptoms**: Developers couldn't easily reproduce errors or see stack traces.
**Fix applied**:

* Add a `--verbose` flag in the script that sets `frappe.logger.setLevel(logging.DEBUG)` and `print()`s stepwise progress.
* Write the last exception traceback into `Extracted Email New.error_message` so it's visible in Desk.
* Add a `frappe.get_doc('Extracted Email New', name).print_format()` helper for quick inspection.

### Issue: `source_emailid` mapping problems

**Symptoms**: Incorrect or missing link to original `Communication`.
**Fix applied**:

* Use stable unique key `communication.name` (the docname) as `source_emailid`. When fetching, ensure the script uses `comm_doc.name` (not `comm_doc.reference` or `id`).
* Save `communication_id` and `communication_creation` timestamps in `Extracted Email New` for traceability.

---

## 9) Debugging & observability

### Logs to check

* Frappe error log (bench logs)
* `Extracted Email New` documents (status, error_message, ai_output)
* Console STDOUT if run manually

### Helpful commands

* Run interactive function from bench:

```bash
bench --site yoursite execute path.to.email_processor.process_received_emails_to_trip_requests --args "[]"
```

* Inspect an `Extracted Email New` doc from bench console:

```python
import frappe
doc = frappe.get_doc('Extracted Email New', 'NAME')
print(doc.status)
print(doc.ai_output)
print(doc.error_message)
```

* Create a Trip Request manually for debugging:

```python
from frappe.utils import now
trip = frappe.new_doc('Trip Request')
trip.employee = 'EMP/0001'
trip.pickup_location = 'A'
trip.drop_location = 'B'
trip.pickup_datetime = now()
trip.insert()
frappe.db.commit()
```

### Common failure points & how to inspect

* **AI returned non-JSON**: open `Extracted Email New.ai_output`; re-run parsing function locally, save exception.
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
*/5 * * * * cd /path/to/frappe-bench && bench --site yoursite execute path.to.email_processor.process_received_emails_to_trip_requests >> /var/log/email_processor.log 2>&1
```

**Important**: If using cron do not forget `frappe.db.commit()` in code paths where changes must persist.

### Resource considerations

* Keep AI requests batched sensibly if you have rate limits.
* Monitor worker slots and memory if attachments are processed.

---

## 11) Testing & QA checklist

* [ ] Unit tests for `clean_email_body` against common HTML variants
* [ ] Unit tests for `parse_ai_response_to_json` including malformed outputs
* [ ] Integration test: run script on a sample mailbox replica
* [ ] End-to-end test: ensure a real email creates a `Trip Request` in a test site
* [ ] Fuzzy match tests for mapping `employee_name` → Employee doctype
* [ ] Duplicate detection tests

---

## 12) Future improvements / TODOs

* Full implementation of attachments → `File` docs + linking
* OCR pipeline for screenshots to extract addresses/dates as fallback
* Improve fuzzy matching for Employee mapping (use trigram similarity or external search index)
* Add an Admin UI in Desk to review `Extracted Email New` items that failed parsing
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
  "pickup_location": "Rama Metro Life, C Tower, Opposite D Mart",
  "drop_location": "Bel apartment",
  "pickup_datetime": "2025-10-16T09:30:00+05:30",
  "employee_name": "Rohit",
  "phone_number": "+919876543210",
  "seats_required": 1,
  "additional_notes": null,
  "attachments_present": false
}
```

### Example: final Trip Request mapping to doctype fields

* `trip_request.employee_name` ← `employee_name`
* `trip_request.contact_number` ← `phone_number`
* `trip_request.pickup_from` ← `pickup_location`
* `trip_request.drop_at` ← `drop_location`
* `trip_request.pickup_datetime` ← `pickup_datetime`
* `trip_request.notes` ← `additional_notes`
* Attach `File` docs to trip request if present

---

## Contributing / contact

If you need changes, open an issue in the repository or contact the maintainer (Sohail) directly. Include the `Extracted Email New` doc id when reporting a specific failing email.

---

## License

Include your chosen license here (e.g., MIT) — or copy the organization standard license.

---

*End of README*
