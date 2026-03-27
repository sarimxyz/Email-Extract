# Quickstart: First `FC Trip Request`

This guide helps you set up the app so incoming **cab/taxi/vehicle booking emails** automatically create an **`FC Trip Request`** in Frappe/ERPNext.

## What you need

1. Access to your Frappe site as **System Manager**.
2. Credentials for your LLM provider.
3. An email ingestion method that can POST the incoming email to this app (Gmail or SendGrid webhook).

## Step 1: Install / migrate the app

1. Install the `fab_cars` app in your bench environment (or update your existing app).
2. Run a migration so the DocTypes are created:
   - `bench --site <your_site> migrate`
3. Confirm the following singletons exist in Desk search:
   - `FC LLM Settings`
   - `FC Cab Settings`
   - `FC Ingestion Settings`

## Step 2: Configure LLM + extraction prompt (Desk UI)

1. Open **`FC LLM Settings`**
   - Choose `llm_provider` = **Anthropic** or **OpenAI**
   - Enter the provider API key
   - Enter model IDs for:
     - classifier model
     - extractor model
2. Open **`FC Cab Settings`**
   - Set `prompt` to your extraction prompt template
   - IMPORTANT: `prompt` must include the placeholder `{email_text}`
3. Open **`FC Ingestion Settings`**
   - Set `max_attempts` (how many times the app will retry extraction for a single email if extraction fails)

## Step 3: Configure webhook ingestion (production-ready)

For production (no extra daemon), configure your email provider to POST directly to these Frappe endpoints.

## Step 4: Connect your email provider

Configure your provider to POST to one of:

1. SendGrid:
   - `POST /api/method/fab_cars.fab_cars.api.email_provider_webhook_api.sendgrid_webhook`
2. Gmail (Pub/Sub push):
   - `POST /api/method/fab_cars.fab_cars.api.email_provider_webhook_api.gmail_webhook`

These endpoints extract/normalize plain text and run the extraction pipeline inside Frappe.

Optional security (recommended):
- If you set `WEBHOOK_SHARED_SECRET` for your Frappe/bench processes, also send header `X-FC-Webhook-Token`.

## Step 5: Verify end-to-end

After a test email is sent:

1. Open the **`FC Raw Email Log`** doctype.
   - You should see the email appear with `status = Pending` then move to one of:
     - `Successful` (a trip was created)
     - `Needs Info` (the email is missing key details; an optional follow-up email may be sent)
     - `Failed` (check `last_error` for the reason)
     - `Skipped` (this doesn’t look like a cab/taxi/vehicle booking)
2. Open **`FC Trip Request`**.
   - A new trip will be created and filled in only when the related `FC Raw Email Log` shows `Successful`.

To view recent extraction activity, open the app page **`email-extraction`** (see docs for monitoring).

