import unittest

from app.services.pending_evaluation_reports import (
    build_resumed_report_payload,
    clear_pending_evaluation_reports,
    delete_pending_evaluation_report,
    get_pending_evaluation_reports,
    stage_pending_evaluation_report,
)


class PendingEvaluationReportTests(unittest.TestCase):
    def setUp(self):
        self.phone = "5218110000088"
        clear_pending_evaluation_reports(None, self.phone)

    def tearDown(self):
        clear_pending_evaluation_reports(None, self.phone)

    def test_report_turn_survives_outside_request_memory(self):
        staged = stage_pending_evaluation_report(
            None,
            self.phone,
            evaluation_folio="475667",
            payload={
                "message_id": 1001,
                "type": "from_client",
                "text": "Hay un bache en Vasconcelos 321",
                "client": {"phone": self.phone},
            },
            query_params={"source": "chat2desk"},
            now=1000,
        )

        pending = get_pending_evaluation_reports(None, self.phone)

        self.assertFalse(staged["durable"])
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["evaluation_folio"], "475667")
        self.assertEqual(
            pending[0]["payload"]["text"],
            "Hay un bache en Vasconcelos 321",
        )
        self.assertEqual(pending[0]["query_params"]["source"], "chat2desk")

    def test_retries_do_not_duplicate_the_same_paused_turn(self):
        payload = {
            "message_id": 1001,
            "type": "from_client",
            "text": "Hay basura sin recoger",
        }

        stage_pending_evaluation_report(
            None,
            self.phone,
            evaluation_folio="475667",
            payload=payload,
            now=1000,
        )
        stage_pending_evaluation_report(
            None,
            self.phone,
            evaluation_folio="475667",
            payload=payload,
            now=1001,
        )

        self.assertEqual(len(get_pending_evaluation_reports(None, self.phone)), 1)

    def test_replay_gets_fresh_identity_without_losing_citizen_evidence(self):
        record = stage_pending_evaluation_report(
            None,
            self.phone,
            evaluation_folio="475667",
            payload={
                "message_id": 1001,
                "request_id": 2002,
                "event_time": "2026-10-06T10:00:00Z",
                "_sam_webhook_received_at": 1000,
                "type": "from_client",
                "text": "Hay un bache",
                "photo": "https://storage.chat2desk.com/image.jpg",
            },
        )

        replay = build_resumed_report_payload(record)

        self.assertNotEqual(replay["message_id"], 1001)
        self.assertEqual(replay["request_id"], replay["message_id"])
        self.assertEqual(replay["_sam_original_message_id"], 1001)
        self.assertTrue(replay["_sam_resumed_after_evaluation"])
        self.assertEqual(replay["text"], "Hay un bache")
        self.assertEqual(
            replay["photo"],
            "https://storage.chat2desk.com/image.jpg",
        )
        self.assertNotIn("event_time", replay)
        self.assertNotIn("_sam_webhook_received_at", replay)

    def test_each_turn_is_deleted_only_after_it_is_requeued(self):
        staged = stage_pending_evaluation_report(
            None,
            self.phone,
            evaluation_folio="475667",
            payload={"message_id": 1001, "text": "Hay un bache"},
        )

        self.assertTrue(
            delete_pending_evaluation_report(
                None,
                self.phone,
                staged["event_key"],
            )
        )
        self.assertEqual(get_pending_evaluation_reports(None, self.phone), [])


if __name__ == "__main__":
    unittest.main()
