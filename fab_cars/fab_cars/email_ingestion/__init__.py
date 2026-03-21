# Copyright (c) 2026, fab_cars and contributors
# For license information, please see license.txt

"""
Email ingestion (webhook → raw log → extraction).

- ``thread_resolution`` — merge replies into the correct ``FC Raw Email Log``
- ``payload`` — webhook validation and hash helpers
- ``ingest_flow`` — raw log upsert and thread success shortcuts
- ``thread_plain_text`` — aggregate thread bodies for the LLM
- ``followup`` / ``communication`` — missing-info replies and Frappe mail threading
"""
