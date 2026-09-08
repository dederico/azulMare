import unittest

from app.services.media_payload import get_video_from_payload


class MediaPayloadTests(unittest.TestCase):
    def test_reads_top_level_video_url(self):
        self.assertEqual(
            get_video_from_payload({"video": "https://example.test/evidence.mp4"}),
            "https://example.test/evidence.mp4",
        )

    def test_reads_video_attachment_url(self):
        payload = {
            "attachments": [
                {
                    "content_type": "video/mp4",
                    "file": {"url": "https://example.test/evidence.mp4"},
                }
            ]
        }
        self.assertEqual(
            get_video_from_payload(payload),
            "https://example.test/evidence.mp4",
        )

    def test_does_not_misclassify_image_attachment(self):
        payload = {
            "attachments": [
                {
                    "content_type": "image/jpeg",
                    "file": {"url": "https://example.test/evidence.jpg"},
                }
            ]
        }
        self.assertIsNone(get_video_from_payload(payload))


if __name__ == "__main__":
    unittest.main()
