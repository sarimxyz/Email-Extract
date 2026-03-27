# Configure Settings (DocTypes Only)

All AI and extraction behavior in `fab_cars` is configured using DocTypes. No API keys are read from `site_config.json`.

## 1) `FC LLM Settings` (singleton)

1. Go to Desk search and open **`FC LLM Settings`**
2. Set:
   - `llm_provider`: choose **Anthropic** or **OpenAI**
   - `anthropic_api_key` (if using Anthropic) OR `openai_api_key` (if using OpenAI)
   - Model IDs:
     - classifier model (cab/not-cab classification)
     - extractor model (booking extraction)

Notes:
- Your keys are stored as encrypted Password fields.
- If a required value is missing, the ingestion will fail and record the error on `FC Raw Email Log`.

## 2) `FC Cab Settings` (singleton)

Open **`FC Cab Settings`** and set:

- `prompt` (Long Text): the extraction prompt template

CRITICAL:

- Your `prompt` MUST include the placeholder `{email_text}`
- The app replaces `{email_text}` with the cleaned email body before calling the LLM

Example pattern (you provide the full prompt, but it must contain this token):

```text
... {email_text} ...
```

## 3) `FC Ingestion Settings` (singleton)

Open **`FC Ingestion Settings`** and set:

- `max_attempts`: maximum number of extraction attempts for a single email
- `send_followup_email` (optional): if enabled, the app can email the sender asking for missing booking details
- `followup_email_subject` (optional): subject line for the follow-up email

Behavior:
- On extraction/LLM/JSON parsing failures, the app retries up to `max_attempts`.
- If the email is missing key details, the app marks the record as `Needs Info` (and may send the follow-up email if `send_followup_email` is enabled).
- When the max is exceeded, the `FC Raw Email Log` is marked `Failed`.

## Recommended setup checklist

1. `FC LLM Settings.llm_provider` is set correctly
2. API key is present for the chosen provider
3. `FC Cab Settings.prompt` includes `{email_text}`
4. `FC Ingestion Settings.max_attempts` is set to a practical value (start with `3` to `5`)

