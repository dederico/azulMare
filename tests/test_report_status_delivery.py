import unittest

from app.services.report_completion import clear_report_completion, record_report_completion
from app.services.report_status_delivery import (
    claim_report_status_delivery,
    clear_report_status_delivery_memory,
    get_report_status_delivery,
    mark_report_status_delivered,
    mark_report_status_failed,
    record_report_status_route,
)


class ReportStatusDeliveryTests(unittest.TestCase):
    def setUp(self):
        clear_report_status_delivery_memory()

    def tearDown(self):
        clear_report_status_delivery_memory()

    def test_route_is_keyed_by_folio_and_preserves_originating_channel(self):
        durable = record_report_status_route(
            None,
            "489932",
            conversation_key="chat2desk:wa_direct:channel:43943:client:88",
            client_id=88,
            channel_id=43943,
            transport="wa_direct",
            now=100,
        )

        route = get_report_status_delivery(None, "489932")

        self.assertFalse(durable)
        self.assertEqual(route["client_id"], "88")
        self.assertEqual(route["channel_id"], "43943")
        self.assertEqual(route["transport"], "wa_direct")

    def test_report_completion_records_route_for_later_ciac_callback(self):
        conversation_key = "chat2desk:wa_direct:channel:43943:client:88"
        try:
            record_report_completion(
                None,
                conversation_key,
                "489932",
                client_id=88,
                channel_id=43943,
                transport="wa_direct",
                now=100,
            )

            route = get_report_status_delivery(None, "489932")

            self.assertEqual(route["client_id"], "88")
            self.assertEqual(route["channel_id"], "43943")
        finally:
            clear_report_completion(None, conversation_key)

    def test_consecutive_duplicate_status_is_suppressed(self):
        first = claim_report_status_delivery(
            None,
            "489932",
            "concluido",
            now=100,
        )
        self.assertIsNotNone(first)
        self.assertTrue(
            mark_report_status_delivered(
                None,
                "489932",
                first,
                provider_message_id="msg-1",
                now=101,
            )
        )

        duplicate = claim_report_status_delivery(
            None,
            "489932",
            "concluido",
            now=200,
        )

        self.assertIsNone(duplicate)
        self.assertEqual(
            get_report_status_delivery(None, "489932")["provider_message_id"],
            "msg-1",
        )

    def test_valid_close_reactivate_close_lifecycle_is_delivered(self):
        statuses = ("concluido", "reactivado", "concluido")

        for index, status in enumerate(statuses, start=1):
            token = claim_report_status_delivery(
                None,
                "489932",
                status,
                now=index * 100,
            )
            self.assertIsNotNone(token)
            self.assertTrue(
                mark_report_status_delivered(
                    None,
                    "489932",
                    token,
                    provider_message_id=f"msg-{index}",
                    now=index * 100 + 1,
                )
            )

        row = get_report_status_delivery(None, "489932")
        self.assertEqual(row["last_status"], "concluido")
        self.assertEqual(row["provider_message_id"], "msg-3")

    def test_definite_failure_can_retry_same_status(self):
        first = claim_report_status_delivery(None, "489932", "concluido", now=100)
        mark_report_status_failed(None, "489932", first, now=101)

        retry = claim_report_status_delivery(None, "489932", "concluido", now=102)

        self.assertIsNotNone(retry)
        self.assertNotEqual(first, retry)

    def test_ambiguous_failure_suppresses_unsafe_retry(self):
        first = claim_report_status_delivery(None, "489932", "concluido", now=100)
        mark_report_status_failed(
            None,
            "489932",
            first,
            ambiguous=True,
            now=101,
        )

        retry = claim_report_status_delivery(None, "489932", "concluido", now=500)

        self.assertIsNone(retry)

    def test_stale_processing_claim_can_be_recovered(self):
        first = claim_report_status_delivery(
            None,
            "489932",
            "concluido",
            now=100,
            claim_ttl_seconds=10,
        )

        retry = claim_report_status_delivery(
            None,
            "489932",
            "concluido",
            now=111,
            claim_ttl_seconds=10,
        )

        self.assertIsNotNone(retry)
        self.assertNotEqual(first, retry)


if __name__ == "__main__":
    unittest.main()
