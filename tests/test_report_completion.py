import unittest

from app.services.report_completion import (
    clear_report_completion,
    get_recent_report_completion,
    is_delayed_pre_completion_event,
    mark_report_completion_notified,
    record_report_completion,
)


class DurableReportCompletionTests(unittest.TestCase):
    def setUp(self):
        clear_report_completion(None, "+52 1 81 1234 5678")

    def tearDown(self):
        clear_report_completion(None, "+52 1 81 1234 5678")

    def test_recent_completion_is_shared_by_normalized_phone(self):
        record_report_completion(
            None,
            "+52 1 81 1234 5678",
            "472626",
            now=100,
        )

        completion = get_recent_report_completion(
            None,
            "5218112345678",
            max_age_seconds=300,
            now=200,
        )

        self.assertEqual(completion["folio"], "472626")

    def test_expired_completion_is_not_returned(self):
        record_report_completion(
            None,
            "5218112345678",
            "472626",
            now=100,
        )

        completion = get_recent_report_completion(
            None,
            "5218112345678",
            max_age_seconds=300,
            now=401,
        )

        self.assertIsNone(completion)

    def test_unnotified_completion_preserves_delivery_recovery_payload(self):
        record_report_completion(
            None,
            "5218112345678",
            "472626",
            now=100,
            notification_message="Tu folio es 472626",
            request_id="request-1",
            origin_uid="inbound-1",
            origin_message_id="message-1",
            client_id="client-1",
            channel_id="channel-1",
            transport="wa_direct",
        )

        completion = get_recent_report_completion(
            None,
            "5218112345678",
            max_age_seconds=300,
            now=200,
        )

        self.assertEqual(completion["notification_message"], "Tu folio es 472626")
        self.assertEqual(completion["origin_uid"], "inbound-1")
        self.assertIsNone(completion["notified_at"])

        self.assertTrue(
            mark_report_completion_notified(
                None,
                "5218112345678",
                now=210,
            )
        )
        notified = get_recent_report_completion(
            None,
            "5218112345678",
            max_age_seconds=300,
            now=220,
        )
        self.assertEqual(notified["notified_at"], 210)

    def test_only_events_clearly_before_folio_are_stale(self):
        completion = {"folio": "472626", "completed_at": 100.0}
        self.assertTrue(is_delayed_pre_completion_event(completion, 90.0))
        self.assertFalse(is_delayed_pre_completion_event(completion, 99.0))
        self.assertFalse(is_delayed_pre_completion_event(completion, 101.0))
        self.assertFalse(is_delayed_pre_completion_event(completion, None))


if __name__ == "__main__":
    unittest.main()
