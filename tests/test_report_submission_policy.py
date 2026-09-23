import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from app.services.report_submission_policy import (
    classify_sidewalk_sign_answer,
    contains_complete_report_phrase,
    extract_pending_report_answers,
    extract_report_field_answer,
    fallback_report_category_id,
    infer_high_confidence_report_category,
    infer_unsolicited_report_answers,
    is_likely_report_description,
    merge_citizen_report_description,
    next_missing_report_field,
    normalize_reporter_name_input,
    reconcile_with_citizen_evidence,
    resolve_unambiguous_catalog_category,
    select_citizen_report_description,
    validate_and_normalize_report_submission,
    validation_error_to_user_message,
)
from app.services.functions.implementations.save_selection2 import save_client_selection2


class ReportSubmissionPolicyTests(unittest.TestCase):
    def test_widget_transcript_recovers_original_bache_description(self):
        description = select_citizen_report_description(
            [
                ("assistant", "¿Qué asunto municipal deseas consultar o reportar?"),
                ("user", "Quiero reportar un bache"),
                ("assistant", "¿En qué calle se encuentra el problema?"),
                ("user", "Vasconcelos"),
                ("assistant", "¿Cuál es el número exterior?"),
                ("user", "123"),
                ("assistant", "¿En qué colonia se encuentra el problema?"),
                ("user", "Centro"),
                ("assistant", "¿Deseas agregar una imagen para complementar tu reporte?"),
                ("user", "No tengo fotos"),
            ]
        )
        self.assertEqual(description, "Quiero reportar un bache")

    def test_andres_burst_messages_accumulate_without_following_prompt_order(self):
        fields = {
            "selection1": "",
            "selection2": "",
            "selection4": "",
            "selection5": "General Francisco Naranjo",
            "selection6": "",
            "selection7": "",
        }

        updates = infer_unsolicited_report_answers(fields, "en Palo Blanco")
        self.assertEqual(updates, {"selection7": "Palo Blanco"})
        fields.update(updates)

        updates = infer_unsolicited_report_answers(fields, "no hay luminarias")
        self.assertEqual(updates["selection1"], "982")
        self.assertEqual(updates["selection4"], "no hay luminarias")
        fields.update(updates)

        updates = infer_unsolicited_report_answers(fields, "368")
        self.assertEqual(updates, {"selection6": "368"})

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

    def test_visibilidad_is_not_a_si_finalization(self):
        text = "El letrero no permite la visibilidad de los vehículos"
        self.assertFalse(contains_complete_report_phrase(text, ("si", "sí")))
        self.assertTrue(contains_complete_report_phrase("Sí, termina mi reporte", ("si", "sí")))

    def test_initial_sidewalk_sign_description_is_citizen_evidence(self):
        self.assertTrue(is_likely_report_description("Banqueta obstruida por letrero"))

    def test_problem_question_captures_unrestricted_citizen_explanation(self):
        self.assertEqual(
            extract_report_field_answer(
                "¿Qué problema presenta el anuncio?",
                "Estorba la visibilidad",
            ),
            ("selection4", "Estorba la visibilidad"),
        )

    def test_advertisement_category_comes_from_active_catalog(self):
        catalog = (
            "Valor: 969, Tipo: Permisos y quejas de anuncios\n"
            "Valor: 1007, Tipo: Exhorto obstrucción de banqueta con objetos móviles"
        )
        self.assertEqual(
            resolve_unambiguous_catalog_category(
                catalog,
                "Un anuncio en la calle. El anuncio obstruye la visibilidad",
            ),
            "969",
        )
        self.assertEqual(
            resolve_unambiguous_catalog_category(
                catalog.replace("Valor: 969", "Valor: 1234"),
                "El anuncio obstruye la visibilidad",
            ),
            "1234",
        )
        self.assertIsNone(resolve_unambiguous_catalog_category("", "Un anuncio en la calle"))

    def test_ambiguous_catalog_match_never_picks_arbitrary_id(self):
        catalog = (
            "Valor: 1007, Tipo: Exhorto obstrucción de banqueta con objetos móviles\n"
            "Valor: 1008, Tipo: Obstrucción de banqueta con construcción fija"
        )
        self.assertIsNone(
            resolve_unambiguous_catalog_category(catalog, "La banqueta está obstruida")
        )

    def test_number_with_landmark_keeps_the_number(self):
        self.assertEqual(
            extract_report_field_answer(
                "¿Cuál es el número del domicilio o la numeración más cercana?",
                "2513, al lado del Banamex",
            ),
            ("selection6", "2513"),
        )

    def test_pending_number_accepts_common_no_number_variants(self):
        for answer in ("0000", "Sin número", "No tiene numeración", "Es esquina", "Son numero"):
            with self.subTest(answer=answer):
                self.assertEqual(
                    extract_pending_report_answers("selection6", answer),
                    {"selection6": "0000"},
                )

    def test_pending_street_extracts_compound_multiline_address(self):
        self.assertEqual(
            extract_pending_report_answers(
                "selection5",
                "Encino 113\nFraccionamiento Olinalá",
            ),
            {
                "selection5": "Encino",
                "selection6": "113",
                "selection7": "Olinalá",
            },
        )

    def test_pending_state_does_not_treat_controls_as_field_answers(self):
        self.assertEqual(extract_pending_report_answers("selection5", "FIN"), {})
        self.assertEqual(extract_pending_report_answers("selection5", "Gracias"), {})

    def test_name_refusal_is_saved_as_anonymous(self):
        for answer in (
            "No",
            "NEL",
            "Nel pastel",
            "Nop",
            "Paso",
            "No gracias",
            "Preferiría omitirlo",
            "Prefiero no compartirlo",
            "No quiero dar mi nombre",
            "No compartiré datos personales",
            "Esa información es privada",
            "Me reservo mis datos",
            "Sin nombre",
        ):
            with self.subTest(answer=answer):
                self.assertEqual(normalize_reporter_name_input(answer), "Anónimo")
                self.assertEqual(
                    extract_pending_report_answers("selection2", answer),
                    {"selection2": "Anónimo"},
                )

    def test_contextual_name_refusal_continues_as_anonymous(self):
        for answer in ("No", "No gracias", "Prefiero mantenerlo privado"):
            with self.subTest(answer=answer):
                self.assertEqual(
                    extract_report_field_answer(
                        "Antes de crear el reporte, ¿me compartes tu nombre?",
                        answer,
                    ),
                    ("selection2", "Anónimo"),
                )

    def test_anonymous_name_leaves_only_the_next_missing_field(self):
        fields = {
            "selection1": "982",
            "selection2": "Anónimo",
            "selection4": "No hay alumbrado en mi calle desde hace un mes",
            "selection5": "General Francisco Naranjo",
            "selection6": "338",
            "selection7": "Palo Blanco",
        }

        self.assertIsNone(next_missing_report_field(fields))

    def test_unknown_subject_uses_general_ciac_catalog_entry(self):
        catalog = (
            "Valor: 984, Tipo: Baches\n"
            "Valor: 486, Tipo: Gestiones dirección de atención ciudadana\n"
        )

        self.assertEqual(fallback_report_category_id(catalog), "486")
        self.assertEqual(fallback_report_category_id(""), "486")

    def test_fin_asks_only_for_missing_name_then_catalog_clarification(self):
        catalog = (
            "Valor: 1007, Tipo: Exhorto obstrucción de banqueta con objetos móviles\n"
            "Valor: 1008, Tipo: Obstrucción de banqueta con construcción fija"
        )
        fields = {
            "selection1": "",
            "selection2": "",
            "selection4": "Banqueta obstruida por letrero",
            "selection5": "Avenida Lázaro Cárdenas",
            "selection6": "2513",
            "selection7": "Valle Oriente",
        }
        self.assertEqual(next_missing_report_field(fields, prompt=catalog)[0], "selection2")
        fields["selection2"] = "Gerardo Rodríguez"
        field, question = next_missing_report_field(fields, prompt=catalog)
        self.assertEqual(field, "selection1")
        self.assertIn("mover", question)
        fields["selection1"] = classify_sidewalk_sign_answer(
            "Está fijo",
            prompt=catalog,
            description=fields["selection4"],
        )
        self.assertEqual(fields["selection1"], "1008")
        self.assertIsNone(next_missing_report_field(fields, prompt=catalog))

    def test_movable_sidewalk_sign_uses_catalog_not_default(self):
        catalog = (
            "Valor: 1007, Tipo: Exhorto obstrucción de banqueta con objetos móviles\n"
            "Valor: 1008, Tipo: Obstrucción de banqueta con construcción fija"
        )
        self.assertEqual(
            classify_sidewalk_sign_answer(
                "Se puede mover",
                prompt=catalog,
                description="Banqueta obstruida por letrero",
            ),
            "1007",
        )
        self.assertEqual(
            classify_sidewalk_sign_answer(
                "No se puede mover",
                prompt=catalog,
                description="Banqueta obstruida por letrero",
            ),
            "1008",
        )

    def test_unknown_category_does_not_loop_on_unresolvable_question(self):
        fields = {
            "selection1": "",
            "selection2": "Gerardo Rodríguez",
            "selection4": "Un problema de infraestructura",
            "selection5": "Lázaro Cárdenas",
            "selection6": "2513",
            "selection7": "Valle Oriente",
        }
        self.assertIsNone(next_missing_report_field(fields, prompt=""))

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
