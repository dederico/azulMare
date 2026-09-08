import unittest
from types import SimpleNamespace

from app.services.image_analysis import (
    analyze_image_url,
    build_image_acknowledgement,
)


class ImmediateQueue:
    async def add_task(self, task_func, *args, **kwargs):
        return await task_func(*args, **kwargs)


class FakeResponses:
    def __init__(self, *, output_text="", error=None):
        self.output_text = output_text
        self.error = error
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        if self.error:
            raise self.error
        return SimpleNamespace(output_text=self.output_text, output=[])


class ImageAnalysisTests(unittest.IsolatedAsyncioTestCase):
    async def test_image_url_is_sent_directly_to_responses(self):
        responses = FakeResponses(output_text="Un bache profundo sobre el pavimento.")
        client = SimpleNamespace(responses=responses)
        url = "https://storage.chat2desk.com.mx/example.jpg"

        description = await analyze_image_url(client, url, queue=ImmediateQueue())

        self.assertEqual(description, "Un bache profundo sobre el pavimento.")
        self.assertEqual(responses.kwargs["input"][0]["content"][1]["image_url"], url)
        self.assertFalse(responses.kwargs["store"])

    async def test_analysis_failure_returns_none_instead_of_public_error(self):
        responses = FakeResponses(error=TimeoutError())
        client = SimpleNamespace(responses=responses)

        description = await analyze_image_url(
            client,
            "https://storage.chat2desk.com.mx/example.jpg",
            queue=ImmediateQueue(),
        )

        self.assertIsNone(description)

    def test_acknowledgement_does_not_expose_analysis_failure(self):
        message = build_image_acknowledgement("Claudia", None, 1)

        self.assertIn("recibí tu imagen y la he guardado", message)
        self.assertNotIn("Error", message)

    def test_acknowledgement_includes_successful_description(self):
        message = build_image_acknowledgement(
            "Claudia",
            "un bache profundo sobre el pavimento",
            1,
        )

        self.assertIn("veo un bache profundo sobre el pavimento", message)


if __name__ == "__main__":
    unittest.main()
