import unittest

from app.services.report_notification_policy import (
    build_report_status_notification,
    extract_ciac_conclusion_attachments,
    normalize_report_status,
)


class ReportNotificationPolicyTests(unittest.TestCase):
    def test_reactivation_status_builds_approved_hsm(self):
        notification = build_report_status_notification(477699, "Reactivación")

        self.assertEqual(notification.status, "reactivado")
        self.assertTrue(notification.is_hsm)
        self.assertEqual(
            notification.text,
            "@HSM@\nnotifica_reactivacion|es_mx\n\n477699",
        )

    def test_status_aliases_are_normalized(self):
        self.assertEqual(normalize_report_status("REACTIVADO"), "reactivado")
        self.assertEqual(normalize_report_status("en proceso"), "en_progreso")
        self.assertIsNone(normalize_report_status("asignado"))

    def test_legacy_ciac_rows_preserve_image_and_pdf_filenames(self):
        attachments = extract_ciac_conclusion_attachments(
            [
                {"imagen": "https://files.test/evidencia.jpeg"},
                {"imagen": "https://files.test/dictamen.pdf"},
            ]
        )

        self.assertEqual(
            [(item.filename, item.content_type) for item in attachments],
            [
                ("evidencia.jpeg", "image/jpeg"),
                ("dictamen.pdf", "application/pdf"),
            ],
        )

    def test_typed_attachment_collections_are_deduplicated(self):
        attachments = extract_ciac_conclusion_attachments(
            {
                "attachments": [
                    {
                        "url": "https://files.test/resolucion",
                        "filename": "resolución.pdf",
                        "content_type": "application/pdf",
                    },
                    {"url": "https://files.test/resolucion"},
                ]
            }
        )

        self.assertEqual(len(attachments), 1)
        self.assertEqual(attachments[0].filename, "resolución.pdf")
        self.assertEqual(attachments[0].content_type, "application/pdf")


if __name__ == "__main__":
    unittest.main()
