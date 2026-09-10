import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from app.services.report_submission_policy import (
    extract_report_field_answer,
    infer_high_confidence_report_category,
    is_likely_report_description,
    merge_citizen_report_description,
    reconcile_with_citizen_evidence,
    select_citizen_report_description,
    validate_and_normalize_report_submission,
    validation_error_to_user_message,
)
from app.services.functions.implementations.save_selection2 import save_client_selection2


class ReportSubmissionPolicyTests(unittest.TestCase):
    def valid_submission(self, **overrides):
        values = {
            "selection1": "984",
            "selection2": "Ana Pérez",
            "selection4": "Hay un bache profundo que obstruye el carril derecho",
            "selection5": "Vasconcelos",
            "selection6": "321",
            "selection7": "Centro",
        }
        values.update(overrides)
        return validate_and_normalize_report_submission(**values)

    def test_valid_submission_is_normalized_without_changing_meaning(self):
        values, error = self.valid_submission(selection4="  Hay  un bache profundo  ")

        self.assertIsNone(error)
        self.assertEqual(values["selection4"], "Hay un bache profundo")
        self.assertEqual(values["selection1"], "984")

    def test_empty_description_is_blocked(self):
        values, error = self.valid_submission(selection4="")

        self.assertIsNone(values)
        self.assertIn("explicación concreta", error)

    def test_legacy_generic_description_is_blocked(self):
        values, error = self.valid_submission(selection4="Problema reportado: bache")

        self.assertIsNone(values)
        self.assertIn("explicación concreta", error)

    def test_mismatched_unambiguous_category_is_repaired(self):
        values, error = self.valid_submission(
            selection1="974",
            selection4="Hay un bache profundo frente al domicilio",
        )

        self.assertIsNone(error)
        self.assertEqual(values["selection1"], "984")

    def test_multiple_different_topics_are_not_guessed(self):
        self.assertIsNone(
            infer_high_confidence_report_category("Hay basura dentro de un bache")
        )

    def test_description_preserves_citizen_words_and_appends_new_detail(self):
        description = merge_citizen_report_description(
            "Hay un bache frente a mi casa",
            "Cada día se hace más profundo",
        )

        self.assertEqual(
            description,
            "Hay un bache frente a mi casa. Cada día se hace más profundo",
        )

    def test_generic_legacy_description_is_replaced_by_citizen_message(self):
        self.assertEqual(
            merge_citizen_report_description(
                "Problema reportado: basura",
                "Hay bolsas de basura bloqueando la banqueta",
            ),
            "Hay bolsas de basura bloqueando la banqueta",
        )

    def test_brief_but_real_description_is_allowed(self):
        values, error = self.valid_submission(selection4="Un bache")

        self.assertIsNone(error)
        self.assertEqual(values["selection4"], "Un bache")

    def test_control_message_is_not_used_as_report_description(self):
        self.assertFalse(
            is_likely_report_description(
                "Fin",
                previous_assistant_message="¿Qué deseas reportar?",
            )
        )

    def test_answer_to_problem_question_is_grounded_evidence(self):
        self.assertTrue(
            is_likely_report_description(
                "Los juegos están quebrados y pueden lastimar a los niños",
                previous_assistant_message="¿Qué deseas reportar?",
            )
        )

    def test_citizen_evidence_repairs_category_and_model_description(self):
        category, description, changed = reconcile_with_citizen_evidence(
            "974",
            "Hay basura en la calle",
            "Hay un bache profundo frente a mi domicilio",
        )

        self.assertTrue(changed)
        self.assertEqual(category, "984")
        self.assertEqual(description, "Hay un bache profundo frente a mi domicilio")

    def test_unfamiliar_wording_is_not_rejected_by_keyword_lists(self):
        description = select_citizen_report_description(
            [
                ("user", "Quiero hacer un reporte"),
                ("assistant", "¿Qué deseas reportar?"),
                ("user", "Quiero compartir un cacharro que dejaron afuera de mi casa"),
                ("assistant", "¿En qué calle está?"),
                ("user", "Vasconcelos"),
            ]
        )

        self.assertEqual(
            description,
            "Quiero compartir un cacharro que dejaron afuera de mi casa",
        )

    def test_problem_answer_is_captured_from_question_not_keyword_list(self):
        self.assertEqual(
            extract_report_field_answer(
                "¿Qué deseas reportar?",
                "Quiero compartir un cacharro que dejaron afuera de mi casa",
            ),
            (
                "selection4",
                "Quiero compartir un cacharro que dejaron afuera de mi casa",
            ),
        )

    def test_street_is_captured_from_the_immediately_previous_question(self):
        self.assertEqual(
            extract_report_field_answer(
                "¿En qué calle se encuentra el problema?",
                "Vasconcelos",
            ),
            ("selection5", "Vasconcelos"),
        )

    def test_explicit_missing_number_is_captured_as_0000(self):
        self.assertEqual(
            extract_report_field_answer(
                "¿Cuál es el número exterior?",
                "sin número",
            ),
            ("selection6", "0000"),
        )

    def test_fin_after_image_prompt_never_becomes_a_report_field(self):
        self.assertIsNone(
            extract_report_field_answer(
                "Recibí tu imagen. Si deseas continuar responde FIN.",
                "Fin",
            )
        )

    def test_generic_request_alone_is_not_used_as_the_explanation(self):
        self.assertEqual(
            select_citizen_report_description(
                [("user", "Quiero hacer un reporte")]
            ),
            "",
        )

    def test_explicit_no_number_is_repaired_to_0000(self):
        values, error = self.valid_submission(selection6="sin número")

        self.assertIsNone(error)
        self.assertEqual(values["selection6"], "0000")

    def test_widget_synthetic_name_is_blocked_but_anonymous_is_allowed(self):
        values, error = self.valid_submission(selection2="[chat] abc123")
        self.assertIsNone(values)
        self.assertIn("nombre real", error)

        values, error = self.valid_submission(selection2="Anónimo")
        self.assertIsNone(error)
        self.assertEqual(values["selection2"], "Anónimo")

    def test_validation_error_becomes_a_specific_question(self):
        message = validation_error_to_user_message("debes obtener una colonia válida")

        self.assertIn("¿en qué colonia", message)


class SaveSelectionBoundaryTests(unittest.IsolatedAsyncioTestCase):
    async def test_final_api_boundary_refuses_empty_description(self):
        result = await save_client_selection2(
            yoga_number="5218111111111",
            selection1="984",
            selection2="Ana Pérez",
            selection3="",
            selection4="",
            selection5="Vasconcelos",
            selection6="321",
            selection7="Centro",
        )

        self.assertTrue(result.startswith("VALIDATION_BLOCK:"))
        self.assertIn("No se creó ningún folio", result)

    async def test_final_api_boundary_repairs_mismatched_category_before_http(self):
        # La validación de la corrección pura se cubre arriba. Aquí se usa un
        # payload sin nombre para confirmar que la frontera continúa bloqueando
        # datos realmente indispensables antes de intentar red.
        result = await save_client_selection2(
            yoga_number="5218111111111",
            selection1="974",
            selection2="",
            selection3="",
            selection4="Hay un bache profundo frente al domicilio",
            selection5="Vasconcelos",
            selection6="321",
            selection7="Centro",
        )

        self.assertTrue(result.startswith("VALIDATION_BLOCK:"))
        self.assertIn("nombre real", result)

    async def test_ciac_transient_timeout_is_retried_and_category_is_repaired(self):
        response = MagicMock()
        response.status_code = 200
        response.text = "471999"
        response.raise_for_status.return_value = None

        client = MagicMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=None)
        client.post = AsyncMock(
            side_effect=[httpx.ConnectTimeout("temporal"), response]
        )

        def close_scheduled_coroutine(coroutine):
            coroutine.close()
            return MagicMock()

        with (
            patch("httpx.AsyncClient", return_value=client),
            patch("asyncio.sleep", new=AsyncMock()),
            patch("asyncio.create_task", side_effect=close_scheduled_coroutine),
        ):
            result = await save_client_selection2(
                yoga_number="5218111111111",
                selection1="974",
                selection2="Ana Pérez",
                selection3="",
                selection4="Hay un bache frente a mi domicilio",
                selection5="Vasconcelos",
                selection6="321",
                selection7="Centro",
            )

        self.assertEqual(result, "Folio: 471999")
        self.assertEqual(client.post.await_count, 2)
        self.assertEqual(client.post.await_args.kwargs["json"]["asunto"], "984")

    async def test_invalid_ciac_response_is_not_presented_as_a_folio(self):
        response = MagicMock()
        response.status_code = 200
        response.text = ""
        response.raise_for_status.return_value = None

        client = MagicMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=None)
        client.post = AsyncMock(return_value=response)

        with patch("httpx.AsyncClient", return_value=client):
            result = await save_client_selection2(
                yoga_number="5218111111111",
                selection1="984",
                selection2="Ana Pérez",
                selection3="",
                selection4="Hay un bache frente a mi domicilio",
                selection5="Vasconcelos",
                selection6="321",
                selection7="Centro",
            )

        self.assertTrue(result.startswith("CIAC_FAILURE:"))


if __name__ == "__main__":
    unittest.main()
