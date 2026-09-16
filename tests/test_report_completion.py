import unittest

from app.services.report_completion import (
    clear_report_completion,
    get_recent_report_completion,
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


if __name__ == "__main__":
    unittest.main()
