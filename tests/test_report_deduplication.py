import unittest

from app.services.deduplication.manager import ReportDeduplicationManager


class ReportDeduplicationManagerTests(unittest.TestCase):
    def setUp(self):
        self.manager = ReportDeduplicationManager()
        self.phone_number = "5218115854586"
        self.first_report = {
            "selection1": "984",
            "selection4": "Juegos dañados en parque",
            "selection5": "Parque Rufino Tamayo",
            "selection6": "100",
            "selection7": "Valle Oriente",
        }

    def test_identical_content_is_blocked_and_returns_existing_folio(self):
        self.manager.mark_report_creation_success(
            self.phone_number,
            "Folio: 470999",
            self.first_report,
        )

        can_create, reason, existing_folio = self.manager.can_create_report(
            self.phone_number,
            self.first_report,
        )

        self.assertFalse(can_create)
        self.assertIn("duplicado", reason.lower())
        self.assertEqual(existing_folio, "470999")

    def test_different_content_from_same_phone_is_allowed_immediately(self):
        self.manager.mark_report_creation_success(
            self.phone_number,
            "Folio: 470999",
            self.first_report,
        )
        self.manager.post_report_protection.pop(self.phone_number)
        different_report = {
            **self.first_report,
            "selection4": "Luminaria apagada",
            "selection5": "Río Amazonas",
        }

        can_create, reason, existing_folio = self.manager.can_create_report(
            self.phone_number,
            different_report,
        )

        self.assertTrue(can_create)
        self.assertEqual(reason, "OK")
        self.assertIsNone(existing_folio)

    def test_post_report_protection_does_not_block_different_content(self):
        self.manager.mark_report_creation_success(
            self.phone_number,
            "Folio: 470999",
            self.first_report,
        )
        different_report = {
            **self.first_report,
            "selection4": "Árbol caído sobre la banqueta",
        }

        can_create, reason, existing_folio = self.manager.can_create_report(
            self.phone_number,
            different_report,
        )

        self.assertTrue(can_create)
        self.assertEqual(reason, "OK")
        self.assertIsNone(existing_folio)

    def test_selection6_is_part_of_report_identity(self):
        manager = ReportDeduplicationManager()
        manager.mark_report_creation_success(
            self.phone_number,
            "Folio: 470999",
            self.first_report,
        )
        same_problem_different_address = {
            **self.first_report,
            "selection6": "200",
        }

        can_create, reason, existing_folio = manager.can_create_report(
            self.phone_number,
            same_problem_different_address,
        )

        self.assertTrue(can_create)
        self.assertEqual(reason, "OK")
        self.assertIsNone(existing_folio)


if __name__ == "__main__":
    unittest.main()
