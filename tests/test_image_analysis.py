import unittest
from types import SimpleNamespace

from app.services.image_analysis import (
    analyze_image_url,
    build_conversational_image_acknowledgement,
    build_image_acknowledgement,
    classify_image_conversation_intent,
    promote_pending_report_images,
    route_inbound_image,
    stage_pending_report_image,
    should_preserve_unconfirmed_image_context,
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

    def test_conversational_image_never_claims_there_is_a_report(self):
        message = build_conversational_image_acknowledgement(
            "Francisco",
            "una tarjeta de presentación de una sastrería",
        )

        self.assertIn("consulta", message)
        self.assertIn("levantar un reporte municipal", message)
        self.assertIn("conservaré esta imagen", message.casefold())
        self.assertNotIn("vuelve a enviar la imagen", message)
        self.assertNotIn("guardado para el reporte", message)
        self.assertNotIn("responde FIN", message)

    async def test_model_resolves_image_as_part_of_current_report(self):
        responses = FakeResponses(output_text="REPORT")
        client = SimpleNamespace(responses=responses)

        decision = await classify_image_conversation_intent(
            client,
            [
                {"role": "user", "content": "Se reporta pintura vial borrada."},
                {
                    "role": "assistant",
                    "content": "¿Deseas agregar una imagen para complementar tu reporte?",
                },
            ],
            queue=ImmediateQueue(),
        )

        self.assertEqual(decision, "report")
        prompt = responses.kwargs["input"][0]["content"][0]["text"]
        self.assertIn("Se reporta pintura vial borrada", prompt)
        self.assertIn("REPORT, CONSULTATION o UNCLEAR", prompt)

    async def test_model_failure_keeps_image_context_unresolved(self):
        responses = FakeResponses(error=TimeoutError())
        client = SimpleNamespace(responses=responses)

        decision = await classify_image_conversation_intent(
            client,
            [{"role": "user", "content": "Mira esta foto"}],
            queue=ImmediateQueue(),
        )

        self.assertEqual(decision, "unclear")

    def test_report_image_prompt_is_authoritative_for_next_image(self):
        destination = route_inbound_image(
            report_intent_confirmed=False,
            awaiting_report_image=True,
            semantic_decision="unclear",
        )

        self.assertEqual(destination, "report")

    def test_semantic_report_decision_can_recover_missing_local_state(self):
        destination = route_inbound_image(
            report_intent_confirmed=False,
            awaiting_report_image=False,
            semantic_decision="report",
        )

        self.assertEqual(destination, "report")

    def test_pending_image_is_deduplicated_and_promoted_without_resend(self):
        session = {
            "images": [],
            "image_descriptions": [],
            "pending_images": [],
            "pending_image_descriptions": [],
        }

        stage_pending_report_image(session, "https://example.test/photo.jpg", None)
        stage_pending_report_image(
            session,
            "https://example.test/photo.jpg",
            "pintura vial borrada",
        )
        promoted = promote_pending_report_images(session)

        self.assertEqual(promoted, 1)
        self.assertEqual(session["images"], ["https://example.test/photo.jpg"])
        self.assertEqual(session["image_descriptions"], ["pintura vial borrada"])
        self.assertEqual(session["pending_images"], [])
        self.assertEqual(session["pending_image_descriptions"], [])

    def test_unconfirmed_pending_image_context_survives_worker_hop(self):
        self.assertTrue(
            should_preserve_unconfirmed_image_context(
                {"awaiting_report_image": True, "pending_images": []}
            )
        )
        self.assertTrue(
            should_preserve_unconfirmed_image_context(
                {"awaiting_report_image": False, "pending_images": ["photo"]}
            )
        )
        self.assertFalse(
            should_preserve_unconfirmed_image_context(
                {"awaiting_report_image": False, "pending_images": []}
            )
        )


if __name__ == "__main__":
    unittest.main()
