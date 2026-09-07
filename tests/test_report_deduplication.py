import unittest

from app.services.deduplication.manager import ReportDeduplicationManager


class ReportDeduplicationManagerTests(unittest.TestCase):
    def test_post_report_protection_returns_existing_folio(self):
        manager = ReportDeduplicationManager()
        phone_number = "5218115854586"
        selection_data = {
            "selection1": "984",
            "selection4": "Juegos dañados en parque",
            "selection5": "Parque Rufino Tamayo",
            "selection7": "Valle Oriente",
        }

        manager.mark_report_creation_success(
            phone_number,
            "Folio: 470999",
            selection_data,
        )

        can_create, reason, existing_folio = manager.can_create_report(
            phone_number,
            selection_data,
        )

        self.assertFalse(can_create)
        self.assertIn("Protección post-reporte activa", reason)
        self.assertEqual(existing_folio, "470999")


if __name__ == "__main__":
    unittest.main()
