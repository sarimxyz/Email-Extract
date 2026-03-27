# Copyright (c) 2025, sarim and Contributors
# See license.txt

import hashlib
import json
import uuid
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

import fab_cars.fab_cars.api.email_ingestion_api as email_ingestion_api
from fab_cars.fab_cars.api.email_ingestion_api import ingest_email
from fab_cars.fab_cars.doctype.fc_extracted_email.fc_extracted_email import process_payload_to_trip_request
from fab_cars.fab_cars.email_ingestion.addresses import extract_sender_email
from fab_cars.fab_cars.email_ingestion.followup import (
	send_booking_confirmation,
	send_missing_info_followup,
)
from fab_cars.fab_cars.email_ingestion.payload import validate_webhook_payload
from fab_cars.fab_cars.email_ingestion.raw_log_messages import parent_inbound_message_id_for_followup_reply
from fab_cars.fab_cars.email_ingestion.thread_resolution import resolve_thread_root_log_name
from fab_cars.fab_cars.email_ingestion_service import webhook_server as ingestion_webhook_server
from fab_cars.fab_cars.llm.llm_client import LLMResult
from fab_cars.hooks_handlers import ensure_references_header_for_threading


def _make_test_extraction_json(
	*,
	pickup_date: str | None = "2026-03-19",
	pickup_time: str | None = "10:00",
	pickup_location: str | None = "A",
	drop_location: str | None = "B",
	drop_date: str | None = "2026-03-19",
	drop_time: str | None = "11:00",
):
	return {
		"has_multiple_bookings": True,
		"number_of_bookings": 1,
		"vehicle_type": "Sedan",
		"city": "Gotham",
		"miscellaneous_requirements": "",
		"duty_type": "Official",
		"request_type": "Pickup",
		"special_request": "",
		"remarks": "Test remarks",
		"notes": "",
		"booked_by": {"name": "Bob", "email": "bob@example.com", "number": "123"},
		"billed_to": {"name": "ACME", "email": "billing@example.com", "number": "456"},
		"point_of_contact": {"name": "Eve", "email": "eve@example.com", "number": "789"},
		"bookings": [
			{
				"passenger_name": "Alice",
				"passenger_number": "1",
				"pickup_location": pickup_location,
				"drop_location": drop_location,
				"pickup_date": pickup_date,
				"drop_date": drop_date,
				"pickup_time": pickup_time,
				"drop_time": drop_time,
				"reporting_time": "09:30",
				"passenger_special_request": "VIP",
			}
		],
	}


class TestExtractedEmail(FrappeTestCase):
	def setUp(self):
		super().setUp()
		# Test isolation:
		# Do NOT modify the real singleton `FC Cab Settings` stored in the site DB.
		# Instead, mock what the extractor reads during these unit tests.
		self._real_get_single = frappe.get_single
		self._cab_settings_mock = type("_CabSettingsMock", (), {"prompt": "{email_text}"})()

		self._get_single_patcher = patch(
			"fab_cars.fab_cars.doctype.fc_extracted_email.fc_extracted_email.frappe.get_single"
		)
		self._mock_get_single = self._get_single_patcher.start()

		def _get_single_side_effect(doctype: str, *args, **kwargs):
			if doctype == "FC Cab Settings":
				return self._cab_settings_mock
			return self._real_get_single(doctype, *args, **kwargs)

		self._mock_get_single.side_effect = _get_single_side_effect
		self.addCleanup(self._get_single_patcher.stop)

	def test_process_payload_maps_bookings_into_trip_request(self):
		extracted_email = frappe.get_doc(
			{
				"doctype": "FC Extracted Email",
				"source_email_id": "src-1",
				"sender": "sender@example.com",
				"subject": "Subject",
				"message_body": "original email",
				"received_date": "2026-03-19",
				"trip_request_status": "Pending",
				"trip_request_error": "",
				"has_multiple_bookings": False,
				"number_of_bookings": 0,
			}
		)
		extracted_email.insert()
		frappe.db.commit()

		extraction_json = _make_test_extraction_json()

		with patch(
			"fab_cars.fab_cars.doctype.fc_extracted_email.fc_extracted_email.llm_invoke_text",
			return_value=LLMResult(text=json.dumps(extraction_json), total_tokens=150),
		):
			result = process_payload_to_trip_request(
				plain_text="PLAIN TEXT",
				email_subject="Subject",
				email_sender="sender@example.com",
				received_date="2026-03-19",
				source_message_id="src-1",
				base_name=extracted_email.name,
				extracted_email_doc=extracted_email,
				raw_email_log_doc=None,
				mail_link_value=None,
				is_cab_booking=True,
			)

		self.assertEqual(result["status"], "ok")
		self.assertEqual(extracted_email.reload().trip_request_status, "Successful")

		trip_name = frappe.db.get_value("FC Trip Request", {"trip_name": extracted_email.name}, "name")
		self.assertTrue(trip_name)

		trip = frappe.get_doc("FC Trip Request", trip_name)
		self.assertEqual(len(trip.table_lftf), 1)
		self.assertEqual(trip.table_lftf[0].passenger_special_request, "VIP")
		self.assertEqual(trip.table_lftf[0].pickup_date, "2026-03-19")
		self.assertEqual(trip.table_lftf[0].pickup_time, "10:00")
		self.assertEqual(trip.table_lftf[0].drop_date, "2026-03-19")
		self.assertEqual(trip.table_lftf[0].drop_time, "11:00")

	def test_ingest_email_is_idempotent_on_same_message_id(self):
		extraction_json = _make_test_extraction_json()

		payload = {
			"message_id": "<msg-1@example.com>",
			"sender": "sender@example.com",
			"subject": "Cab booking",
			"received_at": "2026-03-19T10:00:00Z",
			"plain_text": "cab booking details",
			"correlation_id": "corr-1",
		}

		def _fake_llm_invoke_text(*, prompt: str, model: str, max_tokens: int):
			if max_tokens == 1024:
				return LLMResult(text=json.dumps({"is_cab_booking": True, "reason": "test"}), total_tokens=50)
			return LLMResult(text=json.dumps(extraction_json), total_tokens=150)

		with patch(
			"fab_cars.fab_cars.doctype.fc_extracted_email.fc_extracted_email.llm_invoke_text",
			side_effect=_fake_llm_invoke_text,
		):
			res1 = ingest_email(payload)
			res2 = ingest_email(payload)

		self.assertEqual(res1["status"], "ok")
		self.assertEqual(res2["status"], "ok")
		self.assertEqual(res1["trip_request"], res2["trip_request"])
		trip_count = frappe.db.count("FC Trip Request", {"trip_name": res1["raw_log"]})
		self.assertEqual(trip_count, 1)

	def test_ingest_thread_reply_merges_into_same_raw_log_via_fc_thread_token(self):
		"""Replies that include FC-THREAD-ROOT:FCR_* update one log; do not create FCR_{hash(new_msg)}."""
		# Globally unique RFC ids — `message_id` is unique on `FC Raw Email Log`.
		u = uuid.uuid4().hex
		mid1 = f"<thread-root-merge-1-{u}@example.com>"
		mid2 = f"<thread-reply-merge-2-{u}@example.com>"
		h1 = hashlib.sha256(mid1.encode("utf-8")).hexdigest()
		root_name = f"FCR_{h1}"
		h2 = hashlib.sha256(mid2.encode("utf-8")).hexdigest()
		synthetic_new_doc = f"FCR_{h2}"

		if frappe.db.exists("FC Raw Email Log", root_name):
			frappe.delete_doc("FC Raw Email Log", root_name, force=True)
			frappe.db.commit()

		raw_log = frappe.get_doc(
			{
				"doctype": "FC Raw Email Log",
				"message_id": mid1,
				"email_hash": h1,
				"sender": "sender@example.com",
				"subject": "Cab booking",
				"received_at": frappe.utils.get_datetime("2026-03-19T10:00:00Z").replace(tzinfo=None),
				"plain_text": "Full booking body with name phone pickup date time",
				"status": "Pending",
				"attempt_count": 1,
				"correlation_id": root_name,
				"thread_root_message_id": mid1,
				"ingested_message_ids": f"{mid1}\n",
				"last_error": None,
			}
		)
		raw_log.insert()
		frappe.db.commit()
		self.assertEqual(raw_log.name, root_name)
		raw_log.reload()
		self.assertEqual(raw_log.message_id, mid1)
		self.assertNotEqual(synthetic_new_doc, root_name)

		reply_payload = {
			"message_id": mid2,
			"sender": "sender@example.com",
			"subject": "Re: Cab booking",
			"received_at": "2026-03-19T11:00:00Z",
			"plain_text": f"FC-THREAD-ROOT:{root_name}\nDrop location is Mumbai airport",
			# Must be unique: ingest_email treats any prior Successful log with same correlation_id as thread-complete.
			"correlation_id": f"corr-merge-reply-{uuid.uuid4().hex}",
		}
		self.assertEqual(validate_webhook_payload(reply_payload)["message_id"], mid2)

		with patch(
			"fab_cars.fab_cars.api.email_ingestion_api.process_payload_to_trip_request",
			return_value={"status": "ok", "trip_request": None},
		) as mock_process:
			res = ingest_email(reply_payload)
			mock_process.assert_called_once()

		self.assertEqual(res["raw_log"], root_name)
		self.assertFalse(frappe.db.exists("FC Raw Email Log", synthetic_new_doc))

		doc = frappe.get_doc("FC Raw Email Log", root_name)
		self.assertIn("Mumbai airport", doc.plain_text or "")
		self.assertIn("Full booking body", doc.plain_text or "")
		self.assertEqual(doc.message_id, mid2)
		self.assertEqual(doc.thread_root_message_id, mid1)

	def test_ingest_thread_reply_merges_into_same_raw_log_via_references_header(self):
		"""Replies linked by RFC References / In-Reply-To merge without FC-THREAD-ROOT token."""
		u = uuid.uuid4().hex
		mid1 = f"<thread-ref-hdr-{u}@example.com>"
		mid2 = f"<thread-reply-hdr-{u}@example.com>"
		h1 = hashlib.sha256(mid1.encode("utf-8")).hexdigest()
		root_name = f"FCR_{h1}"
		synthetic_new_doc = f"FCR_{hashlib.sha256(mid2.encode('utf-8')).hexdigest()}"

		if frappe.db.exists("FC Raw Email Log", root_name):
			frappe.delete_doc("FC Raw Email Log", root_name, force=True)
			frappe.db.commit()

		raw_log = frappe.get_doc(
			{
				"doctype": "FC Raw Email Log",
				"message_id": mid1,
				"email_hash": h1,
				"sender": "sender@example.com",
				"subject": "Cab booking",
				"received_at": frappe.utils.get_datetime("2026-03-19T10:00:00Z").replace(tzinfo=None),
				"plain_text": "Full booking body with name phone pickup date time",
				"status": "Pending",
				"attempt_count": 1,
				"correlation_id": root_name,
				"thread_root_message_id": mid1,
				"ingested_message_ids": f"{mid1}\n",
				"last_error": None,
			}
		)
		raw_log.insert()
		frappe.db.commit()

		reply_payload = {
			"message_id": mid2,
			"sender": "sender@example.com",
			"subject": "Re: Cab booking",
			"received_at": "2026-03-19T11:00:00Z",
			"plain_text": "Drop location is Mumbai airport",
			"correlation_id": f"corr-hdr-reply-{uuid.uuid4().hex}",
			"references": f"{mid1} {mid2}",
			"in_reply_to": mid1,
		}

		with patch(
			"fab_cars.fab_cars.api.email_ingestion_api.process_payload_to_trip_request",
			return_value={"status": "ok", "trip_request": None},
		) as mock_process:
			res = ingest_email(reply_payload)
			mock_process.assert_called_once()

		self.assertEqual(res["raw_log"], root_name)
		self.assertFalse(frappe.db.exists("FC Raw Email Log", synthetic_new_doc))
		doc = frappe.get_doc("FC Raw Email Log", root_name)
		self.assertIn("Mumbai airport", doc.plain_text or "")
		self.assertIn("Full booking body", doc.plain_text or "")

	def test_merge_extraction_payloads_combines_thread_segments(self):
		from fab_cars.fab_cars.doctype.fc_extracted_email.fc_extracted_email import _merge_extraction_payloads

		a = {
			"bookings": [{"pickup_location": "Hotel", "drop_location": "", "pickup_date": "2026-03-20"}],
			"booked_by": {"name": "Bob", "number": ""},
		}
		b = {
			"bookings": [{"drop_location": "Airport", "pickup_time": "09:00"}],
			"booked_by": {"number": "999"},
		}
		m = _merge_extraction_payloads(a, b)
		self.assertEqual(m["bookings"][0]["pickup_location"], "Hotel")
		self.assertEqual(m["bookings"][0]["drop_location"], "Airport")
		self.assertEqual(m["bookings"][0]["pickup_time"], "09:00")
		self.assertEqual(m["booked_by"]["name"], "Bob")
		self.assertEqual(m["booked_by"]["number"], "999")

	def test_ingest_email_does_not_extract_when_raw_log_in_processing(self):
		"""
		Validation for the ingestion processing lock:
		if a raw log is already in `Processing`, concurrent ingest calls must not
		re-run the extractor or create duplicate trip requests.
		"""
		payload = {
			"message_id": "<msg-lock-1@example.com>",
			"sender": "sender@example.com",
			"subject": "Cab booking",
			"received_at": "2026-03-19T10:00:00Z",
			"plain_text": "cab booking details",
			"correlation_id": "corr-lock-1",
		}
		message_id = payload["message_id"]
		email_hash = hashlib.sha256(str(message_id).encode("utf-8")).hexdigest()

		raw_log_name = f"FCR_{email_hash}"
		if frappe.db.exists("FC Raw Email Log", raw_log_name):
			raw_log = frappe.get_doc("FC Raw Email Log", raw_log_name)
			raw_log.status = "Processing"
			raw_log.last_error = None
			raw_log.correlation_id = payload["correlation_id"]
			raw_log.attempt_count = 1
			raw_log.save()
			frappe.db.commit()
		else:
			raw_log = frappe.get_doc(
				{
					"doctype": "FC Raw Email Log",
					"email_hash": email_hash,
					"message_id": message_id,
					"sender": payload["sender"],
					"subject": payload["subject"],
					"received_at": frappe.utils.get_datetime(payload["received_at"]).replace(tzinfo=None),
					"plain_text": payload["plain_text"],
					"status": "Processing",
					"attempt_count": 1,
					"last_error": None,
					"correlation_id": payload["correlation_id"],
				}
			)
			raw_log.insert()
			frappe.db.commit()

		def _fake_llm_invoke_text(*, prompt: str, model: str, max_tokens: int):
			# Existing Processing raw log skips the classifier; extractor must not run.
			raise AssertionError("LLM must not run while raw log is Processing")

		with patch(
			"fab_cars.fab_cars.doctype.fc_extracted_email.fc_extracted_email.llm_invoke_text",
			side_effect=_fake_llm_invoke_text,
		):
			res = ingest_email(payload)

		self.assertEqual(res["status"], "ok")
		self.assertEqual(res["raw_log"], raw_log_name)
		self.assertFalse(res.get("trip_request"))

		trip_count = frappe.db.count("FC Trip Request", {"trip_name": raw_log_name})
		self.assertEqual(trip_count, 0)

	def test_ingest_email_marks_skipped_when_not_cab_booking(self):
		mid = f"<msg-skipped-{uuid.uuid4().hex}@example.com>"  # avoids stale FCR_* breaking apply_cab_gate
		payload = {
			"message_id": mid,
			"sender": "marketing@example.com",
			"subject": "Quick question",
			"received_at": "2026-03-19T10:00:00Z",
			"plain_text": "How is the weather today?",
			"correlation_id": f"corr-2-{uuid.uuid4().hex}",
		}

		def _fake_llm_invoke_text(*, prompt: str, model: str, max_tokens: int):
			if max_tokens == 1024:
				return LLMResult(
					text=json.dumps({"is_cab_booking": False, "reason": "test"}), total_tokens=20
				)
			raise AssertionError("Extraction should not run for skipped emails")

		with patch(
			"fab_cars.fab_cars.doctype.fc_extracted_email.fc_extracted_email.llm_invoke_text",
			side_effect=_fake_llm_invoke_text,
		):
			res = ingest_email(payload)

		self.assertEqual(res["status"], "skipped")
		self.assertIsNone(res.get("raw_log"))
		self.assertFalse(frappe.db.exists("FC Raw Email Log", {"message_id": mid}))

	def test_ingest_email_skips_without_raw_log_when_payload_flags_not_cab(self):
		"""Explicit ``is_cab_booking: false`` skips before any raw log insert (no LLM)."""
		payload = {
			"message_id": "<msg-heuristic-false@example.com>",
			"sender": "a@example.com",
			"subject": "Anything",
			"received_at": "2026-03-19T10:00:00Z",
			"plain_text": "pickup airport taxi booking",
			"is_cab_booking": False,
		}

		def _must_not_call_llm(*args, **kwargs):
			raise AssertionError("Classifier must not run when is_cab_booking is False")

		with patch(
			"fab_cars.fab_cars.doctype.fc_extracted_email.fc_extracted_email.llm_invoke_text",
			side_effect=_must_not_call_llm,
		):
			res = ingest_email(payload)

		self.assertEqual(res["status"], "skipped")
		self.assertIsNone(res.get("raw_log"))

	def test_ingest_email_skips_aws_bounce_without_llm_or_raw_log(self):
		"""Bounce / AWS system mail is rejected by substring gate before classifier (no LLM)."""
		payload = {
			"message_id": "<aws-bounce-1@example.com>",
			"sender": "no-reply@amazonaws.com",
			"subject": "Automatic reply",
			"received_at": "2026-03-21T10:00:00Z",
			"plain_text": (
				"Greetings from Amazon Web Services.\n\n"
				"We're sorry. You've written to an address that cannot accept incoming e-mail.\n"
				"Visit http://www.aws.amazon.com/contact-us .\n"
			),
		}

		def _must_not_call_llm(*args, **kwargs):
			raise AssertionError("LLM must not run for AWS/bounce mail")

		with patch(
			"fab_cars.fab_cars.doctype.fc_extracted_email.fc_extracted_email.llm_invoke_text",
			side_effect=_must_not_call_llm,
		):
			res = ingest_email(payload)

		self.assertEqual(res["status"], "skipped")
		self.assertIsNone(res.get("raw_log"))

	def test_process_payload_derives_drop_date_time_when_missing(self):
		extracted_email = frappe.get_doc(
			{
				"doctype": "FC Extracted Email",
				"source_email_id": "src-derive-drop",
				"sender": "sender@example.com",
				"subject": "Subject",
				"message_body": "original email",
				"received_date": "2026-03-19",
				"trip_request_status": "Pending",
				"trip_request_error": "",
				"has_multiple_bookings": False,
				"number_of_bookings": 0,
			}
		)
		extracted_email.insert()
		frappe.db.commit()

		extraction_json = _make_test_extraction_json(drop_date=None, drop_time=None, drop_location="B")

		with patch(
			"fab_cars.fab_cars.doctype.fc_extracted_email.fc_extracted_email.llm_invoke_text",
			return_value=LLMResult(text=json.dumps(extraction_json), total_tokens=150),
		):
			result = process_payload_to_trip_request(
				plain_text="PLAIN TEXT",
				email_subject="Subject",
				email_sender="sender@example.com",
				received_date="2026-03-19",
				source_message_id="src-derive-drop",
				base_name=extracted_email.name,
				extracted_email_doc=extracted_email,
				raw_email_log_doc=None,
				mail_link_value=None,
				is_cab_booking=True,
			)

		self.assertEqual(result["status"], "ok")
		self.assertEqual(extracted_email.reload().trip_request_status, "Successful")

		trip_name = frappe.db.get_value("FC Trip Request", {"trip_name": extracted_email.name}, "name")
		trip = frappe.get_doc("FC Trip Request", trip_name)

		self.assertEqual(len(trip.table_lftf), 1)
		self.assertEqual(trip.table_lftf[0].drop_date, trip.table_lftf[0].pickup_date)
		self.assertEqual(trip.table_lftf[0].drop_time, trip.table_lftf[0].pickup_time)

	def test_process_payload_needs_info_only_when_pickup_or_contact_missing(self):
		extracted_email = frappe.get_doc(
			{
				"doctype": "FC Extracted Email",
				"source_email_id": "src-needs-pickup",
				"sender": "sender@example.com",
				"subject": "Subject",
				"message_body": "original email",
				"received_date": "2026-03-19",
				"trip_request_status": "Pending",
				"trip_request_error": "",
				"has_multiple_bookings": False,
				"number_of_bookings": 0,
			}
		)
		extracted_email.insert()
		frappe.db.commit()

		extraction_json = _make_test_extraction_json(pickup_date=None)

		with patch(
			"fab_cars.fab_cars.doctype.fc_extracted_email.fc_extracted_email.llm_invoke_text",
			return_value=LLMResult(text=json.dumps(extraction_json), total_tokens=150),
		):
			result = process_payload_to_trip_request(
				plain_text="PLAIN TEXT",
				email_subject="Subject",
				email_sender="sender@example.com",
				received_date="2026-03-19",
				source_message_id="src-needs-pickup",
				base_name=extracted_email.name,
				extracted_email_doc=extracted_email,
				raw_email_log_doc=None,
				mail_link_value=None,
				is_cab_booking=True,
			)

		self.assertEqual(result["status"], "needs_info")
		self.assertIn("Pickup date", result.get("missing_fields") or [])
		self.assertNotIn("Drop date", result.get("missing_fields") or [])
		self.assertNotIn("Drop time", result.get("missing_fields") or [])

	def test_process_payload_needs_info_when_drop_location_missing(self):
		extracted_email = frappe.get_doc(
			{
				"doctype": "FC Extracted Email",
				"source_email_id": "src-needs-drop",
				"sender": "sender@example.com",
				"subject": "Subject",
				"message_body": "original email",
				"received_date": "2026-03-19",
				"trip_request_status": "Pending",
				"trip_request_error": "",
				"has_multiple_bookings": False,
				"number_of_bookings": 0,
			}
		)
		extracted_email.insert()
		frappe.db.commit()

		extraction_json = _make_test_extraction_json(drop_location=None)

		with patch(
			"fab_cars.fab_cars.doctype.fc_extracted_email.fc_extracted_email.llm_invoke_text",
			return_value=LLMResult(text=json.dumps(extraction_json), total_tokens=150),
		):
			result = process_payload_to_trip_request(
				plain_text="PLAIN TEXT",
				email_subject="Subject",
				email_sender="sender@example.com",
				received_date="2026-03-19",
				source_message_id="src-needs-drop",
				base_name=extracted_email.name,
				extracted_email_doc=extracted_email,
				raw_email_log_doc=None,
				mail_link_value=None,
				is_cab_booking=True,
			)

		self.assertEqual(result["status"], "needs_info")
		self.assertIn("Drop location", result.get("missing_fields") or [])

	def test_process_payload_fills_poc_and_booker_email_from_sender_and_maps_trip_summary(self):
		extracted_email = frappe.get_doc(
			{
				"doctype": "FC Extracted Email",
				"source_email_id": "src-poc-fallback",
				"sender": "John Doe <john.doe@example.com>",
				"subject": "Subject",
				"message_body": "original email",
				"received_date": "2026-03-19",
				"trip_request_status": "Pending",
				"trip_request_error": "",
				"has_multiple_bookings": False,
				"number_of_bookings": 0,
			}
		)
		extracted_email.insert()
		frappe.db.commit()

		extraction_json = _make_test_extraction_json()
		extraction_json["trip_summary"] = "Trip summary from LLM"
		extraction_json["booked_by"]["email"] = None
		# Simulate extractor not returning POC at all (or returning empty values).
		extraction_json["point_of_contact"] = {"name": None, "email": None, "number": None}

		with patch(
			"fab_cars.fab_cars.doctype.fc_extracted_email.fc_extracted_email.llm_invoke_text",
			return_value=LLMResult(text=json.dumps(extraction_json), total_tokens=150),
		):
			result = process_payload_to_trip_request(
				plain_text="PLAIN TEXT",
				email_subject="Subject",
				email_sender="John Doe <john.doe@example.com>",
				received_date="2026-03-19",
				source_message_id="src-poc-fallback",
				base_name=extracted_email.name,
				extracted_email_doc=extracted_email,
				raw_email_log_doc=None,
				mail_link_value=None,
				is_cab_booking=True,
			)

		self.assertEqual(result["status"], "ok")
		trip_name = frappe.db.get_value("FC Trip Request", {"trip_name": extracted_email.name}, "name")
		trip = frappe.get_doc("FC Trip Request", trip_name)

		self.assertEqual(trip.summary, "Trip summary from LLM")
		self.assertEqual(trip.booked_by_email, "john.doe@example.com")
		# POC should be filled even when the extractor returns nulls.
		self.assertEqual(trip.poc_name, "John Doe")
		self.assertEqual(trip.poc_number, trip.booked_by_number)
		self.assertEqual(trip.poc_email, "john.doe@example.com")

	def test_process_payload_retries_when_llm_returns_non_json_then_succeeds(self):
		extracted_email = frappe.get_doc(
			{
				"doctype": "FC Extracted Email",
				"source_email_id": "src-retry-non-json",
				"sender": "sender@example.com",
				"subject": "Subject",
				"message_body": "original email",
				"received_date": "2026-03-19",
				"trip_request_status": "Pending",
				"trip_request_error": "",
				"has_multiple_bookings": False,
				"number_of_bookings": 0,
			}
		)
		extracted_email.insert()
		frappe.db.commit()

		extraction_json = _make_test_extraction_json()

		call_count = {"n": 0}

		def _side_effect(*, prompt: str, model: str, max_tokens: int):
			# First extraction attempt returns non-JSON; second returns valid JSON.
			call_count["n"] += 1
			if call_count["n"] == 1:
				return LLMResult(text="I will help you with that.", total_tokens=10)
			return LLMResult(text=json.dumps(extraction_json), total_tokens=150)

		with patch(
			"fab_cars.fab_cars.doctype.fc_extracted_email.fc_extracted_email.llm_invoke_text",
			side_effect=_side_effect,
		):
			result = process_payload_to_trip_request(
				plain_text="PLAIN TEXT",
				email_subject="Subject",
				email_sender="sender@example.com",
				received_date="2026-03-19",
				source_message_id="src-retry-non-json",
				base_name=extracted_email.name,
				extracted_email_doc=extracted_email,
				raw_email_log_doc=None,
				mail_link_value=None,
				is_cab_booking=True,
			)

		self.assertEqual(result["status"], "ok")
		self.assertEqual(call_count["n"], 2)
		self.assertEqual(extracted_email.reload().trip_request_status, "Successful")

	def test_extract_sender_email_is_robust_to_real_from_header_strings(self):
		self.assertEqual(extract_sender_email("john.doe@example.com"), "john.doe@example.com")
		self.assertEqual(
			extract_sender_email("John Doe <john.doe@example.com>"),
			"john.doe@example.com",
		)
		# Should extract the first email address even if there is extra text after it.
		self.assertEqual(
			extract_sender_email("john.doe@example.com (via example-newsletter)"),
			"john.doe@example.com",
		)
		# When no email address exists, follow-up should not be sent.
		self.assertIsNone(extract_sender_email("Just a display name"))

	def test_parent_inbound_message_id_prefers_thread_root_then_latest(self):
		self.assertEqual(
			parent_inbound_message_id_for_followup_reply(
				raw_log={
					"thread_root_message_id": "<root@example.com>",
					"message_id": "<latest@example.com>",
				},
				payload_message_id=None,
				payload_correlation_id=None,
			),
			"<root@example.com>",
		)

	def test_parent_inbound_message_id_prefers_raw_log_then_payload(self):
		self.assertEqual(
			parent_inbound_message_id_for_followup_reply(
				raw_log={"message_id": "<stored-on-log@example.com>"},
				payload_message_id="<payload@example.com>",
				payload_correlation_id="<corr@example.com>",
			),
			"<stored-on-log@example.com>",
		)
		self.assertEqual(
			parent_inbound_message_id_for_followup_reply(
				raw_log={"message_id": None},
				payload_message_id="<payload@example.com>",
				payload_correlation_id="<corr@example.com>",
			),
			"<payload@example.com>",
		)

	def test_parent_inbound_message_id_skips_fcr_correlation_token(self):
		"""`FCR_*` is our raw-log name / thread token, not the customer's Message-ID."""
		self.assertEqual(
			parent_inbound_message_id_for_followup_reply(
				raw_log=None,
				payload_message_id=None,
				payload_correlation_id="FCR_abc123deadbeef",
			),
			None,
		)
		self.assertEqual(
			parent_inbound_message_id_for_followup_reply(
				raw_log=None,
				payload_message_id="<only@example.com>",
				payload_correlation_id="FCR_ignored",
			),
			"<only@example.com>",
		)

	def test_webhook_server_correlation_id_prefers_references_root_over_in_reply_to(self):
		raw_mime = """From: John Doe <john.doe@example.com>
Subject: Re: Cab booking
Date: Mon, 01 Jan 2024 00:00:00 +0000
Message-ID: <reply@example.com>
In-Reply-To: <followup-bot@example.com>
References: <initial@example.com> <followup-bot@example.com>
Content-Type: text/plain; charset=utf-8

Hi, pickup details: I can provide the phone number.
"""
		parsed = ingestion_webhook_server._parse_raw_mime(raw_mime)
		self.assertEqual(parsed.get("correlation_id"), "initial@example.com")

	def test_resolve_thread_root_log_name_fallbacks_to_thread_root_message_id(self):
		"""
		When webhook correlation_id is a RFC Message-ID (not our `FCR_*` token),
		we should still map it back to the existing `FC Raw Email Log`.
		"""

		def _fake_get_value(doctype, filters, fieldname):
			if doctype != "FC Raw Email Log" or fieldname != "name":
				return None
			if filters == {"thread_root_message_id": "stored-on-log@example.com"}:
				return "FCR_hash_1"
			if filters == {"message_id": "stored-on-log@example.com"}:
				return None
			return None

		with patch(
			"fab_cars.fab_cars.email_ingestion.message_ids.frappe.db.get_value",
			side_effect=_fake_get_value,
		):
			res = resolve_thread_root_log_name(
				plain_text="no token in body",
				correlation_id="<stored-on-log@example.com>",
			)
			self.assertEqual(res, "FCR_hash_1")

	def test_resolve_thread_root_log_name_fallbacks_to_latest_message_id(self):
		def _fake_get_value(doctype, filters, fieldname):
			if doctype != "FC Raw Email Log" or fieldname != "name":
				return None
			if filters == {"thread_root_message_id": "stored-on-log@example.com"}:
				return None
			if filters == {"message_id": "stored-on-log@example.com"}:
				return "FCR_hash_2"
			return None

		with patch(
			"fab_cars.fab_cars.email_ingestion.message_ids.frappe.db.get_value",
			side_effect=_fake_get_value,
		):
			res = resolve_thread_root_log_name(
				plain_text="no token in body",
				correlation_id="<stored-on-log@example.com>",
			)
			self.assertEqual(res, "FCR_hash_2")

	def test_send_missing_info_followup_sets_in_reply_to_for_threading(self):
		class _SettingsMock:
			send_followup_email = 1
			followup_email_subject = None

		with patch(
			"fab_cars.fab_cars.email_ingestion.followup.get_ingestion_settings",
			return_value=_SettingsMock(),
		):
			# Frappe sendmail threading: `in_reply_to` must be Communication.name
			# (see EmailQueue.prepare_email_content), not the raw Message-ID string.
			with patch(
				"fab_cars.fab_cars.email_ingestion.followup.ensure_stub_communication_for_parent_message",
				return_value=None,
			):
				with patch(
					"fab_cars.fab_cars.email_ingestion.followup.communication_name_for_sendmail_in_reply_to",
					return_value="COM-THREAD-PARENT-1",
				):
					with patch("fab_cars.fab_cars.email_ingestion.followup.frappe.sendmail") as sendmail_mock:
						send_missing_info_followup(
							to_sender="John Doe <john.doe@example.com>",
							missing_fields=["Pickup location"],
							in_reply_to="<msg-1@example.com>",
							original_subject="Cab booking request",
							thread_root_token="FCR_root_1",
						)

						sendmail_mock.assert_called_once()
						_, kwargs = sendmail_mock.call_args
						self.assertEqual(kwargs.get("in_reply_to"), "COM-THREAD-PARENT-1")
						self.assertIsNone(kwargs.get("message_id"))
						self.assertEqual(kwargs.get("subject"), "Re: Cab booking request")
						self.assertIn("Fab Cars", kwargs.get("message") or "")
						self.assertIn("Pickup location", kwargs.get("message") or "")
						self.assertIn("FC-THREAD-ROOT:FCR_root_1", kwargs.get("message") or "")

	def test_send_missing_info_followup_stashes_parent_message_id_when_no_communication(self):
		"""When no Communication row exists, Frappe cannot set In-Reply-To; we stash Message-ID for the email hook."""

		class _SettingsMock:
			send_followup_email = 1
			followup_email_subject = None

		seen = {}

		def _capture_sendmail(*args, **kwargs):
			seen["flag_during_send"] = frappe.flags.get("fab_cars_thread_parent_message_id")

		with patch(
			"fab_cars.fab_cars.email_ingestion.followup.get_ingestion_settings",
			return_value=_SettingsMock(),
		):
			with patch(
				"fab_cars.fab_cars.email_ingestion.followup.ensure_stub_communication_for_parent_message",
				return_value=None,
			):
				with patch(
					"fab_cars.fab_cars.email_ingestion.followup.communication_name_for_sendmail_in_reply_to",
					return_value=None,
				):
					with patch(
						"fab_cars.fab_cars.email_ingestion.followup.frappe.sendmail",
						side_effect=_capture_sendmail,
					):
						send_missing_info_followup(
							to_sender="John Doe <john.doe@example.com>",
							missing_fields=["Pickup location"],
							in_reply_to="<msg-1@example.com>",
							original_subject="Cab booking request",
							thread_root_token="FCR_root_1",
						)

		self.assertEqual(seen.get("flag_during_send"), "<msg-1@example.com>")
		self.assertIsNone(frappe.flags.get("fab_cars_thread_parent_message_id"))

	def test_send_missing_info_followup_prefers_original_subject_over_custom_when_threading(self):
		"""Custom follow-up subject must not break Gmail threading; match the inbound thread subject."""

		class _SettingsMock:
			send_followup_email = 1
			followup_email_subject = "We need a few details to confirm your cab booking"

		with patch(
			"fab_cars.fab_cars.email_ingestion.followup.get_ingestion_settings",
			return_value=_SettingsMock(),
		):
			with patch(
				"fab_cars.fab_cars.email_ingestion.followup.ensure_stub_communication_for_parent_message",
				return_value=None,
			):
				with patch(
					"fab_cars.fab_cars.email_ingestion.followup.communication_name_for_sendmail_in_reply_to",
					return_value="COM-THREAD-PARENT-1",
				):
					with patch("fab_cars.fab_cars.email_ingestion.followup.frappe.sendmail") as sendmail_mock:
						send_missing_info_followup(
							to_sender="John Doe <john.doe@example.com>",
							missing_fields=["Drop location"],
							in_reply_to="<msg-1@example.com>",
							original_subject="Cab booking from Mumbai",
							thread_root_token="FCR_root_1",
						)
						_, kwargs = sendmail_mock.call_args
						self.assertEqual(kwargs.get("subject"), "Re: Cab booking from Mumbai")

	def test_send_booking_confirmation_sets_in_reply_to_for_threading(self):
		class _SettingsMock:
			send_booking_confirmation_email = 1
			booking_confirmation_email_subject = None

		with patch(
			"fab_cars.fab_cars.email_ingestion.followup.get_ingestion_settings",
			return_value=_SettingsMock(),
		):
			with patch(
				"fab_cars.fab_cars.email_ingestion.followup.ensure_stub_communication_for_parent_message",
				return_value=None,
			):
				with patch(
					"fab_cars.fab_cars.email_ingestion.followup.communication_name_for_sendmail_in_reply_to",
					return_value="COM-THREAD-PARENT-1",
				):
					with patch("fab_cars.fab_cars.email_ingestion.followup.frappe.sendmail") as sendmail_mock:
						send_booking_confirmation(
							to_sender="Jane Doe <jane@example.com>",
							trip_request_name="FC-TRIP-00001",
							in_reply_to="<msg-1@example.com>",
							original_subject="Cab booking request",
							thread_root_token="FCR_root_1",
						)

						sendmail_mock.assert_called_once()
						_, kwargs = sendmail_mock.call_args
						self.assertEqual(kwargs.get("in_reply_to"), "COM-THREAD-PARENT-1")
						self.assertEqual(kwargs.get("subject"), "Re: Cab booking request")
						msg = kwargs.get("message") or ""
						self.assertIn("FC-TRIP-00001", msg)
						self.assertIn("FC-THREAD-ROOT:FCR_root_1", msg)
						self.assertIn("Fab Cars", msg)

	def test_send_booking_confirmation_respects_send_booking_confirmation_email_disabled(self):
		class _SettingsMock:
			send_booking_confirmation_email = 0
			booking_confirmation_email_subject = None

		with patch(
			"fab_cars.fab_cars.email_ingestion.followup.get_ingestion_settings",
			return_value=_SettingsMock(),
		):
			with patch("fab_cars.fab_cars.email_ingestion.followup.frappe.sendmail") as sendmail_mock:
				send_booking_confirmation(
					to_sender="jane@example.com",
					trip_request_name="FC-TRIP-00001",
					in_reply_to="<msg-1@example.com>",
					original_subject="Cab booking request",
					thread_root_token="FCR_root_1",
				)
				sendmail_mock.assert_not_called()

	def test_ensure_references_header_sets_in_reply_to_from_flag(self):
		class _FakeEmailBody:
			def __init__(self):
				self.msg_root = {}

			def set_header(self, key, value):
				self.msg_root[key] = value

		body = _FakeEmailBody()
		frappe.flags.fab_cars_thread_parent_message_id = "raw-id@mail.example"
		ensure_references_header_for_threading(body)
		self.assertEqual(body.msg_root.get("In-Reply-To"), "<raw-id@mail.example>")
		self.assertEqual(body.msg_root.get("References"), "<raw-id@mail.example>")
		self.assertIsNone(frappe.flags.get("fab_cars_thread_parent_message_id"))

	def test_ensure_references_header_does_not_override_existing_in_reply_to(self):
		class _FakeEmailBody:
			def __init__(self):
				self.msg_root = {}

			def set_header(self, key, value):
				self.msg_root[key] = value

		body = _FakeEmailBody()
		body.msg_root["In-Reply-To"] = "<existing@example.com>"
		frappe.flags.fab_cars_thread_parent_message_id = "<ignored@example.com>"
		ensure_references_header_for_threading(body)
		self.assertEqual(body.msg_root.get("In-Reply-To"), "<existing@example.com>")
		self.assertEqual(body.msg_root.get("References"), "<existing@example.com>")
		self.assertIsNone(frappe.flags.get("fab_cars_thread_parent_message_id"))
