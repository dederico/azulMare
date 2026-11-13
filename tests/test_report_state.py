import unittest
from datetime import datetime, timezone

from app.services.report_state import (
    _json_safe,
    ensure_report_session_defaults,
)


class ReportStateTests(unittest.TestCase):
    def test_datetime_state_is_json_serializable(self):
        timestamp = datetime(2026, 9, 8, 12, 30, tzinfo=timezone.utc)
        result = _json_safe({"timestamp": timestamp, "images": ["https://example.test/a.jpg"]})
        self.assertEqual(result["timestamp"], timestamp.isoformat())
        self.assertEqual(result["images"], ["https://example.test/a.jpg"])

    def test_pre_report_emergency_state_is_promoted_to_full_session(self):
        timestamp = datetime(2026, 11, 12, 22, 22, tzinfo=timezone.utc)
        session = {
            "declared_emergency": False,
            "report_intent_confirmed": False,
            "channel_id": 43943,
        }

        result = ensure_report_session_defaults(
            session,
            timestamp=timestamp,
            started_at=123.0,
        )

        self.assertIs(result, session)
        self.assertFalse(result["declared_emergency"])
        self.assertIsNone(result["location"])
        self.assertEqual(result["images"], [])
        self.assertEqual(result["image_descriptions"], [])
        self.assertEqual(result["pending_images"], [])
        self.assertEqual(result["pending_image_descriptions"], [])
        self.assertEqual(result["citizen_report_messages"], [])
        self.assertEqual(result["timestamp"], timestamp)
        self.assertEqual(result["started_at"], 123.0)
        self.assertEqual(result["channel_id"], 43943)

    def test_session_promotion_preserves_existing_report_values(self):
        session = {
            "declared_emergency": False,
            "location": "Vasconcelos",
            "images": ["https://example.test/a.jpg"],
            "image_prompted": True,
        }

        result = ensure_report_session_defaults(session, started_at=123.0)

        self.assertEqual(result["location"], "Vasconcelos")
        self.assertEqual(result["images"], ["https://example.test/a.jpg"])
        self.assertTrue(result["image_prompted"])


if __name__ == "__main__":
    unittest.main()
