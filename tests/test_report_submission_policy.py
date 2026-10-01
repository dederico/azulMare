import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from app.services.report_submission_policy import (
    build_ciac_report_summary,
    classify_sidewalk_sign_answer,
    contains_complete_report_phrase,
    establishes_report_intent,
    extract_pending_report_answers,
    extract_citizen_reply_text,
    extract_report_field_answer,
    fallback_report_category_id,
    infer_high_confidence_report_category,
    infer_unsolicited_report_answers,
    is_likely_report_description,
    is_report_intent_only,
    merge_citizen_report_description,
    next_missing_report_detail_before_image,
    next_missing_report_field,
    normalize_report_number_input,
    normalize_reporter_name_input,
    parse_report_catalog,
    report_catalog_contains,
    report_session_has_confirmed_intent,
    reconcile_with_citizen_evidence,
    resolve_unambiguous_catalog_category,
    resolve_trusted_reporter_name,
    sanitize_report_description,
    select_citizen_report_description,
    validate_and_normalize_report_submission,
    determine_report_progress,
    deduplicate_report_media,
    validation_error_to_user_message,
)
from app.services.functions.implementations.save_selection2 import save_client_selection2


class ReportSubmissionPolicyTests(unittest.TestCase):
    def valid_fields(self):
        return {
            "selection1": "984",
            "selection2": "Ana Pérez",
            "selection4": "Hay un bache profundo que obstruye el carril derecho",
            "selection5": "Vasconcelos",
            "selection6": "321",
            "selection7": "Centro",
        }

    def test_emergency_media_deduplication_preserves_matching_descriptions(self):
        images, descriptions = deduplicate_report_media(
            ["photo-a", "photo-a", "photo-b"],
            ["Frente", "Duplicada", "Costado"],
        )

        self.assertEqual(images, ["photo-a", "photo-b"])
        self.assertEqual(descriptions, ["Frente", "Costado"])

    def test_complete_non_emergency_moves_to_optional_image_without_llm(self):
        decision = determine_report_progress(
            self.valid_fields(),
            declared_emergency=False,
            image_prompted=False,
            image_decision=None,
            has_images=False,
        )

        self.assertEqual(decision.action, "ask_image")
        self.assertIn("imagen", decision.response)

    def test_unknown_emergency_state_requests_it_deterministically(self):
        decision = determine_report_progress(
            self.valid_fields(),
            declared_emergency=None,
            image_prompted=False,
            image_decision=None,
            has_images=False,
        )

        self.assertEqual(decision.action, "await_emergency_answer")
        self.assertIn("emergencia", decision.response)

    def test_non_emergency_asks_only_the_actual_missing_field(self):
        fields = self.valid_fields()
        fields["selection7"] = ""

        decision = determine_report_progress(
            fields,
            declared_emergency=False,
            image_prompted=False,
            image_decision=None,
            has_images=False,
        )

        self.assertEqual(decision.action, "ask_field")
        self.assertEqual(decision.field, "selection7")

    def test_complete_emergency_is_ready_for_deterministic_submission(self):
        fields = self.valid_fields()
        fields.update(
            selection1="964",
            selection5="Humberto Lobo cerca de Calzada",
            selection6="",
            selection7="",
        )

        decision = determine_report_progress(
            fields,
            declared_emergency=True,
            image_prompted=False,
            image_decision=None,
            has_images=False,
        )

        self.assertEqual(decision.action, "submit_emergency")

    def test_only_citizen_report_evidence_activates_report_mode(self):
        self.assertTrue(establishes_report_intent("Quiero reportar un bache"))
        self.assertTrue(establishes_report_intent("Reporte normal"))
        self.assertTrue(establishes_report_intent("Hay una luminaria"))
        self.assertTrue(establishes_report_intent("No hay luminarias"))
        self.assertTrue(establishes_report_intent("Hay basura tirada"))
        self.assertTrue(
            establishes_report_intent(
                "Poste de luz dañado a punto de caer en la calzada"
            )
        )
        self.assertTrue(
            establishes_report_intent(
                "Para reportar una persona durmiendo en mi banqueta"
            )
        )
        self.assertTrue(establishes_report_intent("No funciona una luminaria"))
        self.assertTrue(establishes_report_intent("Necesito una patrulla"))
        self.assertTrue(
            establishes_report_intent(
                "No es emergencia, quiero levantar un reporte. "
                "Es un bache, ¿puedo reportar?"
            )
        )
        self.assertTrue(
            establishes_report_intent(
                "Hola, se solicita pintar cordón amarillo en Río San Lorenzo"
            )
        )
        self.assertTrue(
            establishes_report_intent(
                "Se solicita pintar cordón amarillo para evitar que se estacionen, "
                "ubicado en Río San Lorenzo #212, Colonia Fuentes del Valle."
            )
        )
        self.assertFalse(establishes_report_intent("Arreglo todo tipo de ropa"))
        self.assertFalse(establishes_report_intent("Recomendaciones para mi negocio"))
        self.assertFalse(
            establishes_report_intent(
                "¿Dónde puedo solicitar que pinten un cordón amarillo?"
            )
        )
        self.assertFalse(
            establishes_report_intent(
                "Quiero información sobre la solicitud para pintar cordones amarillos"
            )
        )
        self.assertFalse(establishes_report_intent("FIN"))
        self.assertFalse(
            establishes_report_intent(
                "¿Puedo circular sin placas si mi licencia es de otro estado?"
            )
        )

    def test_legacy_session_requires_grounded_citizen_evidence(self):
        self.assertFalse(
            report_session_has_confirmed_intent(
                {"citizen_report_messages": ["Recomendaciones para mi sastrería"]}
            )
        )
        self.assertTrue(
            report_session_has_confirmed_intent(
                {"citizen_report_messages": ["Hay un bache frente a mi casa"]}
            )
        )

    def test_ciac_summary_removes_intent_greeting_repetition_and_uses_location(self):
        summary = build_ciac_report_summary(
            "Quiero levantar un reporte, una luminaria que no funciona. "
            "Hola, quiero levantar un reporte - Ubicación del reporte: "
            "Vasconcelos 123, La colonia es Centro",
            "Vasconcelos",
            "123",
            "Centro",
        )

        self.assertEqual(
            summary,
            "Se reporta una luminaria que no funciona en Vasconcelos 123, "
            "colonia Centro.",
        )

    def test_ciac_summary_does_not_change_original_evidence(self):
        original = "Quiero reportar un bache que obstruye el carril derecho"

        summary = build_ciac_report_summary(
            original,
            "Vasconcelos",
            "321",
            "Centro",
        )

        self.assertEqual(original, "Quiero reportar un bache que obstruye el carril derecho")
        self.assertEqual(
            summary,
            "Se reporta un bache que obstruye el carril derecho en Vasconcelos "
            "321, colonia Centro.",
        )

    def test_ciac_summary_uses_one_key_statement_instead_of_accumulated_chat(self):
        accumulated = (
            "« Entiendo que los troncos y ramas quedaron en la calle y la "
            "banqueta. ¿Hay algún riesgo inmediato o no es una emergencia? » "
            "No, los carros las han arrojado hacia los lados, pero creo alguien "
            "tiene que recogerlas. Buenas tardes! El domingo vinieron los de la "
            "CFE a cortar unas ramas de arboles afuera de mi casa y dejaron lleno "
            "de troncos y ramas tiradas. Las ramas. En la calle, banqueta"
        )

        self.assertEqual(
            build_ciac_report_summary(
                accumulated,
                "San José",
                "0000",
                "Residencial Santa Barbara",
            ),
            "Se reporta que el domingo vinieron los de la CFE a cortar unas ramas "
            "de arboles afuera de mi casa y dejaron lleno de troncos y ramas "
            "tiradas en San José, colonia Residencial Santa Barbara.",
        )

    def test_ciac_summary_preserves_concrete_negative_problem(self):
        self.assertEqual(
            build_ciac_report_summary(
                "No hay luminarias en la calle. No, ya revisé dos veces",
                "Vasconcelos",
                "321",
                "Centro",
            ),
            "Se reporta que no hay luminarias en Vasconcelos 321, "
            "colonia Centro.",
        )

    def test_ciac_summary_removes_conversational_leading_filler(self):
        self.assertEqual(
            build_ciac_report_summary(
                "En que hay bastante basura por la escuela Lauro Aguirre",
                "Lauro Aguirre",
                "100",
                "Centro",
            ),
            "Se reporta que hay bastante basura por la escuela Lauro Aguirre "
            "en Lauro Aguirre 100, colonia Centro.",
        )

    def test_emergency_description_is_captured_after_situation_question(self):
        self.assertEqual(
            extract_report_field_answer(
                "¿Qué está ocurriendo y en qué situación necesitas la patrulla?",
                "Paciente psiquiátrico está teniendo una crisis y gritando",
            ),
            (
                "selection4",
                "Paciente psiquiátrico está teniendo una crisis y gritando",
            ),
        )
    def test_ciac_summary_omits_synthetic_zero_number(self):
        self.assertEqual(
            build_ciac_report_summary(
                "No hay luminarias en la calle",
                "General Francisco Naranjo",
                "0000",
                "Palo Blanco",
            ),
            "Se reporta que no hay luminarias en General Francisco Naranjo, "
            "colonia Palo Blanco.",
        )

    def test_sam_location_acknowledgement_is_removed_from_description(self):
        contaminated = (
            "A todos los vecinos se nos baja la luz. "
            "Ubicación registrada: Calle Plata. Para finalizar tu reporte con "
            "las imágenes que has enviado, avísame cuando estés listo. "
            "Mi vecino se pone a soldar todo el día sin tener permiso alguno. "
            "Ubicación del reporte: Plaza 414, la calle Plaza 419, San Pedro 400"
        )

        self.assertEqual(
            sanitize_report_description(contaminated),
            "A todos los vecinos se nos baja la luz. Mi vecino se pone a soldar "
            "todo el día sin tener permiso alguno",
        )

    def test_submission_sanitizes_legacy_sam_prose_before_ciac(self):
        values, error = self.valid_submission(
            selection4=(
                "Hay un bache profundo. Ubicación registrada: Vasconcelos 321. "
                "Para finalizar tu reporte con las imágenes que has enviado, "
                "avísame cuando estés listo."
            )
        )

        self.assertIsNone(error)
        self.assertEqual(values["selection4"], "Hay un bache profundo")

    def test_transcript_ignores_persisted_sam_prose_mislabeled_as_inbound(self):
        description = select_citizen_report_description(
            [
                ("assistant", "¿Qué deseas reportar?"),
                ("user", "No hay luz en toda la cuadra"),
                ("assistant", "¿En qué calle se encuentra el problema?"),
                (
                    "user",
                    "Ubicación registrada: Calle Plata. Para finalizar tu reporte "
                    "con las imágenes que has enviado, avísame cuando estés listo.",
                ),
            ]
        )

        self.assertEqual(description, "No hay luz en toda la cuadra")

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

    def test_chat2desk_quote_is_context_not_citizen_description(self):
        message = (
            "« Entiendo que las ramas quedaron en la calle. "
            "¿Hay algún riesgo inmediato? »\n"
            "No, los carros las han arrojado hacia los lados"
        )

        self.assertEqual(
            extract_citizen_reply_text(message),
            "No, los carros las han arrojado hacia los lados",
        )
        self.assertEqual(
            sanitize_report_description(message),
            "No, los carros las han arrojado hacia los lados",
        )

    def test_structured_field_answer_does_not_expand_description(self):
        self.assertFalse(
            is_likely_report_description(
                "Las ramas",
                previous_assistant_message=(
                    "¿Cuál es el número exterior? Si no existe, indica sin número."
                ),
            )
        )

    def test_best_problem_turn_excludes_later_workflow_answers(self):
        description = select_citizen_report_description(
            [
                (
                    "user",
                    "El domingo la CFE cortó árboles y dejó troncos y ramas tiradas",
                ),
                ("assistant", "¿Cuál es el número exterior?"),
                ("user", "Las ramas"),
                ("assistant", "¿En qué colonia se encuentra el problema?"),
                ("user", "Residencial Santa Bárbara"),
            ]
        )

        self.assertEqual(
            description,
            "El domingo la CFE cortó árboles y dejó troncos y ramas tiradas",
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

    def test_brenda_address_extracts_street_and_number_before_landmark(self):
        self.assertEqual(
            extract_pending_report_answers(
                "selection5",
                "Río Guadalquivir 136 esquina con Río Tamazunchale",
            ),
            {
                "selection5": "Río Guadalquivir",
                "selection6": "136",
            },
        )

    def test_number_parser_accepts_natural_citizen_wording(self):
        for answer in ("Número 136", "El número es 136", "Número exterior: 136", "#136"):
            with self.subTest(answer=answer):
                self.assertEqual(normalize_report_number_input(answer), "136")
                self.assertEqual(
                    extract_pending_report_answers("selection6", answer),
                    {"selection6": "136"},
                )

    def test_image_question_waits_for_report_details_but_not_reporter_name(self):
        fields = {
            "selection1": "486",
            "selection2": "",
            "selection4": "Música a alto volumen",
            "selection5": "Río Guadalquivir",
            "selection6": "",
            "selection7": "Del Valle",
        }
        missing = next_missing_report_detail_before_image(fields)
        self.assertEqual(missing[0], "selection6")

        fields["selection6"] = "136"
        self.assertIsNone(next_missing_report_detail_before_image(fields))

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
                    {},
                )

    def test_contextual_name_refusal_continues_as_anonymous(self):
        for answer in ("No", "No gracias", "Prefiero mantenerlo privado"):
            with self.subTest(answer=answer):
                self.assertIsNone(
                    extract_report_field_answer(
                        "Antes de crear el reporte, ¿me compartes tu nombre?",
                        answer,
                    )
                )

    def test_reporter_name_comes_from_chat2desk_metadata(self):
        self.assertEqual(
            resolve_trusted_reporter_name("Daniela Escareño L."),
            "Daniela Escareño L.",
        )
        self.assertEqual(resolve_trusted_reporter_name("Usuario"), "Anónimo")
        self.assertEqual(
            resolve_trusted_reporter_name("[chat] c33e236e6b6c5cb06593"),
            "Usuario Web",
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

    def test_emergency_requires_only_description_and_freeform_address(self):
        fields = {
            "selection1": "964",
            "selection2": "Daniela Escareño L.",
            "selection4": (
                "Paciente psiquiátrico está teniendo una crisis y gritando; "
                "existen antecedentes de agresión verbal y física"
            ),
            "selection5": "Titanio 407, colonia San Pedro 400",
            "selection6": "",
            "selection7": "",
        }

        self.assertIsNone(
            next_missing_report_field(fields, declared_emergency=True)
        )

    def test_emergency_submission_defaults_number_and_allows_missing_colony(self):
        values, error = validate_and_normalize_report_submission(
            selection1="964",
            selection2="Daniela Escareño L.",
            selection4=(
                "Paciente psiquiátrico está teniendo una crisis y gritando; "
                "existen antecedentes de agresión verbal y física"
            ),
            selection5="Titanio 407, colonia San Pedro 400",
            selection6="",
            selection7="",
            declared_emergency=True,
        )

        self.assertIsNone(error)
        self.assertEqual(values["selection6"], "0000")
        self.assertEqual(values["selection7"], "")

    def test_declared_emergency_cannot_be_reclassified_as_regular_service(self):
        values, error = validate_and_normalize_report_submission(
            selection1="979",
            selection2="Ana Pérez",
            selection4=(
                "Me están persiguiendo junto a un árbol que está por caer"
            ),
            selection5="Humberto Lobo cerca de Calzada",
            selection6="",
            selection7="",
            declared_emergency=True,
        )

        self.assertIsNone(error)
        self.assertEqual(values["selection1"], "964")

    def test_regular_report_still_requires_number_and_colony(self):
        fields = {
            "selection1": "984",
            "selection2": "Ana Pérez",
            "selection4": "Hay un bache profundo que obstruye el carril derecho",
            "selection5": "Vasconcelos",
            "selection6": "",
            "selection7": "",
        }

        self.assertEqual(next_missing_report_field(fields)[0], "selection6")

    def test_unknown_subject_uses_general_ciac_catalog_entry(self):
        catalog = (
            "Valor: 984, Tipo: Baches\n"
            "Valor: 486, Tipo: Gestiones dirección de atención ciudadana\n"
        )

        self.assertEqual(fallback_report_category_id(catalog), "486")
        self.assertEqual(fallback_report_category_id(""), "486")

    def test_fin_never_asks_name_and_goes_to_catalog_clarification(self):
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
        for message in (
            "Quiero hacer un reporte",
            "Hola, quiero levantar un reporte",
            "Buenas tardes, necesito levantar un reporte por favor",
        ):
            with self.subTest(message=message):
                self.assertTrue(is_report_intent_only(message))
                self.assertFalse(is_likely_report_description(message))
                self.assertEqual(
                    select_citizen_report_description([("user", message)]),
                    "",
                )

    def test_report_intent_with_actual_problem_remains_valid_evidence(self):
        message = "Quiero reportar un bache profundo"

        self.assertFalse(is_report_intent_only(message))
        self.assertTrue(is_likely_report_description(message))
        self.assertEqual(
            select_citizen_report_description([("user", message)]),
            message,
        )

    def test_catalog_parser_supports_runtime_and_emergency_formats(self):
        prompt = (
            "* Valor: 964 - Emergencias con riesgo inmediato.\n"
            "Valor: 984, Tipo: Baches\n"
            "Valor: 486, Tipo: Gestiones dirección de atención ciudadana\n"
        )

        self.assertEqual(
            [(entry.value, entry.label) for entry in parse_report_catalog(prompt)],
            [
                ("964", "Emergencias con riesgo inmediato"),
                ("984", "Baches"),
                ("486", "Gestiones dirección de atención ciudadana"),
            ],
        )
        self.assertTrue(report_catalog_contains(prompt, "984"))
        self.assertFalse(report_catalog_contains(prompt, "999999"))

    def test_submission_rejects_category_not_declared_by_active_catalog(self):
        values, error = self.valid_submission(
            selection1="999999",
            selection4="Un elemento urbano presenta daños visibles",
            allowed_category_ids=("964", "984", "486"),
        )

        self.assertIsNone(values)
        self.assertIn("catálogo CIAC activo", error)

    def test_catalog_validation_allows_unambiguous_category_repair(self):
        values, error = self.valid_submission(
            selection1="999999",
            selection4="Hay un bache profundo frente al domicilio",
            allowed_category_ids=("964", "984", "486"),
        )

        self.assertIsNone(error)
        self.assertEqual(values["selection1"], "984")

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

        with (
            patch("httpx.AsyncClient", return_value=client),
            patch("asyncio.sleep", new=AsyncMock()),
            patch("asyncio.create_task") as create_task,
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
        create_task.assert_not_called()
        self.assertEqual(client.post.await_args.kwargs["json"]["asunto"], "984")
        self.assertEqual(
            client.post.await_args.kwargs["json"]["reporte"],
            "Se reporta que hay un bache frente a mi domicilio en Vasconcelos "
            "321, colonia Centro.",
        )

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
