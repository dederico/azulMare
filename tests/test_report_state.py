import unittest
from datetime import datetime, timezone

from app.services.report_state import _json_safe


class ReportStateTests(unittest.TestCase):
    def test_datetime_state_is_json_serializable(self):
        timestamp = datetime(2026, 9, 8, 12, 30, tzinfo=timezone.utc)
        result = _json_safe({"timestamp": timestamp, "images": ["https://example.test/a.jpg"]})
        self.assertEqual(result["timestamp"], timestamp.isoformat())
        self.assertEqual(result["images"], ["https://example.test/a.jpg"])


if __name__ == "__main__":
    unittest.main()
