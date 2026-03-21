# Copyright (c) 2026, fab_cars and contributors
# For license information, please see license.txt

from unittest.mock import MagicMock, patch

from frappe.tests.utils import FrappeTestCase

from fab_cars.fab_cars.email_ingestion.ingestion_cutoff import should_enqueue_ingestion_for_communication


class TestIngestionCutoff(FrappeTestCase):
	def _doc(self, **fields):
		defaults = {
			"communication_medium": "Email",
			"sent_or_received": "Received",
			"email_account": "Test EA",
			"communication_date": "2026-03-20 10:00:00",
			"message_id": "<mid@example.com>",
		}
		defaults.update(fields)
		doc = MagicMock()
		doc.get.side_effect = lambda k, d=None: defaults.get(k, d)
		return doc

	def test_no_email_account_allows_enqueue(self):
		doc = self._doc(email_account="")
		with patch("frappe.db.has_column", return_value=True):
			self.assertTrue(should_enqueue_ingestion_for_communication(doc))

	def test_missing_cutoff_column_allows_enqueue(self):
		doc = self._doc()
		with patch("frappe.db.has_column", return_value=False):
			self.assertTrue(should_enqueue_ingestion_for_communication(doc))

	def test_null_cutoff_allows_enqueue(self):
		doc = self._doc()
		with (
			patch("frappe.db.has_column", return_value=True),
			patch("frappe.db.get_value", return_value=None),
		):
			self.assertTrue(should_enqueue_ingestion_for_communication(doc))

	def test_skips_historical_before_cutoff(self):
		doc = self._doc(communication_date="2018-01-01 09:00:00")
		with (
			patch("frappe.db.has_column", return_value=True),
			patch("frappe.db.get_value", return_value="2020-01-01 00:00:00"),
			patch(
				"fab_cars.fab_cars.email_ingestion.ingestion_cutoff.find_raw_log_name_for_message_id",
				return_value=None,
			),
		):
			self.assertFalse(should_enqueue_ingestion_for_communication(doc))

	def test_allows_new_mail_after_cutoff(self):
		doc = self._doc(communication_date="2026-03-21 15:00:00")
		with (
			patch("frappe.db.has_column", return_value=True),
			patch("frappe.db.get_value", return_value="2026-03-20 12:00:00"),
			patch(
				"fab_cars.fab_cars.email_ingestion.ingestion_cutoff.find_raw_log_name_for_message_id",
				return_value=None,
			),
		):
			self.assertTrue(should_enqueue_ingestion_for_communication(doc))

	def test_skips_when_message_id_already_in_raw_log(self):
		doc = self._doc()
		with (
			patch("frappe.db.has_column", return_value=True),
			patch("frappe.db.get_value", return_value="2010-01-01 00:00:00"),
			patch(
				"fab_cars.fab_cars.email_ingestion.ingestion_cutoff.find_raw_log_name_for_message_id",
				return_value="FCR_abc",
			),
		):
			self.assertFalse(should_enqueue_ingestion_for_communication(doc))
