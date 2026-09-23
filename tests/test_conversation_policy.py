import unittest
from datetime import datetime, timedelta, timezone

from app.services.conversation_policy import (
    WIDGET_EMPTY_RESPONSE_FALLBACK,
    OUT_OF_SCOPE_REDIRECT,
    apply_widget_empty_response_fallback,
    automatic_report_timeouts_enabled,
    authorize_transfer,
    classify_emergency_answer,
    context_reset_marker_uid,
    dialog_transfer_confirms_pending_control,
    event_precedes_context_boundary,
    extract_confirmed_folio,
    greeting_display_name,
    inactivity_snapshot_is_still_stale,
    is_explicit_report_finalization_token,
    is_contextual_handoff_request,
    is_bot_return_message,
    is_human_takeover_message,
    is_known_automated_outbound,
    is_likely_bot_echo,
    is_non_authoritative_control_source,
    is_report_reactivation_notification,
    is_trusted_human_control,
    is_verified_public_phone,
    return_greeting_covers_current_inbound,
    resolve_high_confidence_out_of_scope_response,
    should_replace_unconfirmed_transfer_response,
    should_confirm_operator_outbox_takeover,
    should_accept_bot_return_event,
    should_send_initial_greeting,
)


class AutomaticReportPolicyTests(unittest.TestCase):
    def test_context_reset_marker_is_stable_for_same_webhook_uid(self):
        first = context_reset_marker_uid("new-request", 972178561)
        retry = context_reset_marker_uid("new-request", "972178561")

        self.assertEqual(first, "conversation-reset-new-request-972178561")
        self.assertEqual(retry, first)

    def test_automatic_reports_are_disabled_by_default(self):
        self.assertFalse(automatic_report_timeouts_enabled(None))
        self.assertFalse(automatic_report_timeouts_enabled("false"))

    def test_automatic_reports_require_explicit_opt_in(self):
        self.assertTrue(automatic_report_timeouts_enabled("true"))


class OutOfScopePolicyTests(unittest.TestCase):
    def test_programming_requests_are_redirected(self):
        self.assertEqual(
            resolve_high_confidence_out_of_scope_response(
                "Hazme un Hola Mundo en Python"
            ),
            OUT_OF_SCOPE_REDIRECT,
        )
        self.assertEqual(
            resolve_high_confidence_out_of_scope_response(
                "Escribe código fuente en JavaScript"
            ),
            OUT_OF_SCOPE_REDIRECT,
        )

    def test_isolated_arithmetic_is_redirected(self):
        self.assertEqual(
            resolve_high_confidence_out_of_scope_response("¿Cuánto es 25 + 38?"),
            OUT_OF_SCOPE_REDIRECT,
        )
        self.assertEqual(
            resolve_high_confidence_out_of_scope_response("2+2"),
            OUT_OF_SCOPE_REDIRECT,
        )

    def test_municipal_calculations_remain_available(self):
        self.assertIsNone(
            resolve_high_confidence_out_of_scope_response(
                "¿Cuánto sería el predial con un descuento de 10%?"
            )
        )
        self.assertIsNone(
            resolve_high_confidence_out_of_scope_response(
                "Quiero reportar que el sistema muestra el código Python"
            )
        )

    def test_normal_municipal_and_greeting_messages_continue_to_the_model(self):
        self.assertIsNone(
            resolve_high_confidence_out_of_scope_response(
                "Quiero información de actividades en Parque Mississippi"
            )
        )
        self.assertIsNone(resolve_high_confidence_out_of_scope_response("Hola"))


class FolioValidationTests(unittest.TestCase):
    def test_accepts_only_numeric_backend_folio(self):
        self.assertEqual(extract_confirmed_folio("Folio: 471149"), "471149")
        self.assertEqual(extract_confirmed_folio("Folio: *471149*"), "471149")

    def test_rejects_errors_disguised_as_folios(self):
        self.assertIsNone(extract_confirmed_folio("Folio: Error 500"))
        self.assertIsNone(extract_confirmed_folio("Error al procesar la solicitud"))
        self.assertIsNone(extract_confirmed_folio("No pude crear el reporte"))


class ReportFinalizationPolicyTests(unittest.TestCase):
    def test_fin_token_matches_the_instruction_shown_to_citizen(self):
        self.assertTrue(is_explicit_report_finalization_token("FIN"))
        self.assertTrue(is_explicit_report_finalization_token("  fin  "))

    def test_fin_must_be_an_exact_token(self):
        self.assertFalse(is_explicit_report_finalization_token("al fin"))
        self.assertFalse(is_explicit_report_finalization_token("finalizar después"))

    def test_fin_inside_bot_instruction_is_not_classified_as_echo(self):
        self.assertFalse(
            is_likely_bot_echo(
                "FIN",
                ["Si deseas continuar con tu reporte, responde FIN."],
            )
        )

    def test_short_citizen_reply_is_not_classified_by_substring(self):
        self.assertFalse(
            is_likely_bot_echo(
                "Sí",
                ["Si deseas continuar con tu reporte, responde FIN."],
            )
        )

    def test_real_long_bot_echo_is_detected(self):
        message = "Tu reporte fue registrado correctamente con el folio 472626."
        self.assertTrue(is_likely_bot_echo(message, [message]))


class PublicPhoneValidationTests(unittest.TestCase):
    def test_official_public_numbers_are_allowed(self):
        self.assertTrue(is_verified_public_phone("81 89 88 20 00"))
        self.assertTrue(is_verified_public_phone("81 84 00 44 00"))
        self.assertTrue(is_verified_public_phone("81 12 12 12 12"))

    def test_unverified_number_is_rejected(self):
        self.assertFalse(is_verified_public_phone("81 89 88 11 00"))

    def test_department_phone_returned_by_official_tool_is_allowed(self):
        official_directory = "Dirección de Deportes: 81 8676 5365."
        self.assertTrue(
            is_verified_public_phone(
                "81 86 76 53 65",
                [official_directory],
            )
        )

    def test_number_absent_from_official_tool_remains_blocked(self):
        official_directory = "Dirección de Deportes: 81 8676 5365."
        self.assertFalse(
            is_verified_public_phone(
                "81 11 11 11 11",
                [official_directory],
            )
        )


class EmergencyClassificationTests(unittest.TestCase):
    def test_natural_negative_answer(self):
        self.assertIs(classify_emergency_answer("No es una emergencia"), False)

    def test_natural_positive_answer(self):
        self.assertIs(classify_emergency_answer("Emergencia ya que es agua potable"), True)

    def test_risk_answer(self):
        self.assertIs(classify_emergency_answer("Puede ocasionar un socavón"), True)


class HumanControlPolicyTests(unittest.TestCase):
    def test_fresh_dialog_event_confirms_locally_pending_transfer(self):
        self.assertTrue(
            dialog_transfer_confirms_pending_control(
                {
                    "source": "pending_transfer:explicit_user_request",
                    "updated_at": 100.0,
                },
                100.1,
            )
        )

    def test_dialog_event_cannot_create_takeover_without_local_pending_state(self):
        self.assertFalse(
            dialog_transfer_confirms_pending_control(
                {"source": "explicit_user_request", "updated_at": 100.0},
                101.0,
            )
        )
        self.assertFalse(
            dialog_transfer_confirms_pending_control(
                {
                    "source": "pending_transfer:explicit_user_request",
                    "updated_at": 100.0,
                },
                90.0,
            )
        )

    def test_explicit_user_transfer_is_trusted(self):
        self.assertTrue(
            is_trusted_human_control(
                {"mode": "human", "source": "explicit_user_request"}
            )
        )

    def test_guarded_tool_transfer_is_trusted(self):
        self.assertTrue(
            is_trusted_human_control(
                {"mode": "human", "source": "tool:verified_no_context"}
            )
        )

    def test_operator_takeover_macro_is_trusted(self):
        self.assertTrue(
            is_trusted_human_control(
                {"mode": "human", "source": "chat2desk_takeover_message"}
            )
        )

    def test_dialog_transfer_assignment_is_not_trusted(self):
        self.assertFalse(
            is_trusted_human_control(
                {"mode": "human", "source": "dialog_transferred:228522"}
            )
        )
        self.assertTrue(
            is_non_authoritative_control_source("dialog_transferred:228522")
        )

    def test_trusted_sources_are_not_marked_for_cleanup(self):
        self.assertFalse(
            is_non_authoritative_control_source("chat2desk_takeover_message")
        )
        self.assertFalse(
            is_non_authoritative_control_source("explicit_user_request")
        )

    def test_legacy_operator_outbox_is_not_trusted(self):
        self.assertFalse(
            is_trusted_human_control(
                {"mode": "human", "source": "operator_outbox:228543"}
            )
        )

    def test_confirmed_operator_message_is_trusted(self):
        self.assertTrue(
            is_trusted_human_control(
                {
                    "mode": "human",
                    "source": "confirmed_operator_outbox:228543",
                }
            )
        )

    def test_dialog_confirmation_linked_to_local_pending_transfer_is_trusted(self):
        self.assertTrue(
            is_trusted_human_control(
                {
                    "mode": "human",
                    "source": "confirmed_dialog_transferred_after_pending:228543",
                }
            )
        )

    def test_fresh_non_bot_operator_outbox_confirms_takeover(self):
        self.assertTrue(
            should_confirm_operator_outbox_takeover(
                message_type="to_client",
                hook_type="outbox",
                operator_id=228543,
                is_bot_echo=False,
                stale=False,
                in_return_grace=False,
            )
        )

    def test_bot_and_stale_outbox_do_not_confirm_takeover(self):
        common = {
            "message_type": "to_client",
            "hook_type": "outbox",
            "operator_id": 228522,
            "stale": False,
            "in_return_grace": False,
        }
        self.assertFalse(
            should_confirm_operator_outbox_takeover(
                **common,
                is_bot_echo=True,
            )
        )
        self.assertFalse(
            should_confirm_operator_outbox_takeover(
                **{**common, "stale": True},
                is_bot_echo=False,
            )
        )

    def test_return_greeting_grace_does_not_retake_conversation(self):
        self.assertFalse(
            should_confirm_operator_outbox_takeover(
                message_type="to_client",
                hook_type="outbox",
                operator_id=228522,
                is_bot_echo=False,
                stale=False,
                in_return_grace=True,
            )
        )

    def test_missing_control_is_not_trusted(self):
        self.assertFalse(is_trusted_human_control(None))

    def test_official_operator_greeting_confirms_takeover(self):
        self.assertTrue(
            is_human_takeover_message(
                "Buen día, gracias por comunicarse a Atención Ciudadana, "
                "le atiende Ana Silvia Reyes Tovar ¿en qué le puedo ayudar?"
            )
        )

    def test_fresh_return_macro_can_release_takeover(self):
        text = (
            "Gracias por comunicarse a Atención Ciudadana. Procederé a reiniciar "
            "el chatbot para que pueda generar más reportes usando SAM."
        )
        self.assertTrue(
            should_accept_bot_return_event(
                message_type="to_client",
                text=text,
                stale=False,
            )
        )

    def test_stale_return_macro_cannot_release_current_takeover(self):
        text = (
            "Gracias por comunicarse a Atención Ciudadana. Procederé a reiniciar "
            "el chatbot para que pueda generar más reportes usando SAM."
        )
        self.assertFalse(
            should_accept_bot_return_event(
                message_type="to_client",
                text=text,
                stale=True,
            )
        )

    def test_automated_report_notice_is_not_operator_takeover(self):
        self.assertFalse(
            is_human_takeover_message(
                "Te informamos que tu reporte con folio 471071 fue asignado exitosamente."
            )
        )

    def test_rendered_reactivation_notice_is_automated(self):
        text = (
            "Tu reporte con folio 472988 ha sido reactivado y continuará con el "
            "proceso de atención. Gracias por tus comentarios."
        )
        self.assertTrue(is_report_reactivation_notification(text))
        self.assertTrue(is_known_automated_outbound(text))

    def test_reactivation_hsm_is_automated(self):
        text = "@HSM@\nnotifica_reactivacion|es_mx\n\n472988"
        self.assertTrue(is_report_reactivation_notification(text))
        self.assertTrue(is_known_automated_outbound(text))

    def test_unrelated_hsm_is_not_reactivation(self):
        text = "@HSM@\nnotifica_conclusion|es_mx\n\n472988"
        self.assertFalse(is_report_reactivation_notification(text))

    def test_official_return_macro_is_recognized(self):
        self.assertTrue(
            is_bot_return_message(
                "Gracias por comunicarse a Atención Ciudadana. Procederé a reiniciar "
                "el chatbot para que pueda generar más reportes usando SAM."
            )
        )

    def test_inactivity_notice_is_not_return_macro(self):
        self.assertFalse(
            is_bot_return_message(
                "Parece que te ausentaste. La conversación se cerró por inactividad."
            )
        )

    def test_blocked_transfer_claim_is_replaced(self):
        self.assertTrue(
            should_replace_unconfirmed_transfer_response(
                transfer_attempted=True,
                transfer_succeeded=False,
                response="Como solicitaste hablar con una persona, te canalizaré.",
            )
        )

    def test_normal_response_survives_blocked_transfer_attempt(self):
        self.assertFalse(
            should_replace_unconfirmed_transfer_response(
                transfer_attempted=True,
                transfer_succeeded=False,
                response="Entendido, no es una emergencia. ¿Qué deseas reportar?",
            )
        )

    def test_confirmed_transfer_response_is_not_replaced(self):
        self.assertFalse(
            should_replace_unconfirmed_transfer_response(
                transfer_attempted=True,
                transfer_succeeded=True,
                response="Te transfiero con atención humana.",
            )
        )


class OperatorOutboxClassificationTests(unittest.TestCase):

    def test_delayed_operator_event_before_reset_is_stale(self):
        self.assertTrue(
            event_precedes_context_boundary(
                event_timestamp=100.0,
                boundary_timestamp=200.0,
            )
        )

    def test_operator_event_after_reset_remains_a_valid_takeover(self):
        self.assertFalse(
            event_precedes_context_boundary(
                event_timestamp=201.1,
                boundary_timestamp=200.0,
            )
        )

    def test_known_sam_welcome_is_automated(self):
        self.assertTrue(
            is_known_automated_outbound(
                "¡Bienvenido! Soy SAM, tu asistente virtual de Atención Ciudadana de SPGG."
            )
        )

    def test_known_inactivity_notice_is_automated(self):
        self.assertTrue(
            is_known_automated_outbound(
                "Parece que te ausentaste. La conversación se cerró por inactividad."
            )
        )

    def test_known_operator_farewell_is_automated(self):
        self.assertTrue(
            is_known_automated_outbound(
                "Le atendió Karyme Montserrat, ¡Que tenga un buen día!"
            )
        )

    def test_known_report_assignment_notice_is_automated(self):
        self.assertTrue(
            is_known_automated_outbound(
                "Te informamos que tu reporte con folio *471071* fue asignado "
                "exitosamente con el área correspondiente. Te daremos seguimiento "
                "a través de este chat. ¡Gracias por reportar!"
            )
        )

    def test_normal_operator_text_is_not_automated(self):
        self.assertFalse(is_known_automated_outbound("Buen día, revisaré personalmente su reporte."))


class InactivityPolicyTests(unittest.TestCase):
    def test_unchanged_stale_snapshot_can_close(self):
        observed = datetime.now(timezone.utc) - timedelta(minutes=16)
        self.assertTrue(
            inactivity_snapshot_is_still_stale(
                observed_last_active=observed,
                current_last_active=observed,
                now=datetime.now(timezone.utc),
                threshold_seconds=15 * 60,
                human_control_active=False,
            )
        )

    def test_new_activity_cancels_pending_close(self):
        observed = datetime.now(timezone.utc) - timedelta(minutes=16)
        refreshed = datetime.now(timezone.utc)
        self.assertFalse(
            inactivity_snapshot_is_still_stale(
                observed_last_active=observed,
                current_last_active=refreshed,
                now=refreshed,
                threshold_seconds=15 * 60,
                human_control_active=False,
            )
        )


class InitialGreetingPolicyTests(unittest.TestCase):
    def test_widget_hides_synthetic_chat_name(self):
        self.assertEqual(
            greeting_display_name("[chat] 62ddf69ec67f6bf087b3", "widget"),
            "",
        )

    def test_whatsapp_keeps_same_name_even_if_it_looks_synthetic(self):
        self.assertEqual(
            greeting_display_name("[chat] 62ddf69ec67f6bf087b3", "wa_direct"),
            "[chat] 62ddf69ec67f6bf087b3",
        )

    def test_widget_keeps_real_display_name(self):
        self.assertEqual(greeting_display_name("María", "widget"), "María")

    def test_return_boundary_owns_greeting_before_first_inbound_is_stored(self):
        self.assertTrue(
            return_greeting_covers_current_inbound(
                "conversation-reset-human-return-970590300",
                [{"direction": "outbound", "message": "saludo"}],
            )
        )

    def test_return_boundary_stops_owning_greeting_after_inbound(self):
        self.assertFalse(
            return_greeting_covers_current_inbound(
                "conversation-reset-human-return-970590300",
                [{"direction": "inbound", "message": "Hola"}],
            )
        )

    def test_new_request_gets_institutional_greeting(self):
        self.assertTrue(
            should_send_initial_greeting(
                is_new_request=True,
                history_available=True,
                has_prior_conversation_history=True,
                resetting_after_human=False,
            )
        )

    def test_empty_history_gets_institutional_greeting(self):
        self.assertTrue(
            should_send_initial_greeting(
                is_new_request=False,
                history_available=True,
                has_prior_conversation_history=False,
                resetting_after_human=False,
            )
        )

    def test_active_conversation_does_not_repeat_greeting(self):
        self.assertFalse(
            should_send_initial_greeting(
                is_new_request=False,
                history_available=True,
                has_prior_conversation_history=True,
                resetting_after_human=False,
            )
        )

    def test_return_webhook_owns_its_greeting(self):
        self.assertFalse(
            should_send_initial_greeting(
                is_new_request=False,
                history_available=True,
                has_prior_conversation_history=False,
                resetting_after_human=True,
            )
        )

    def test_human_takeover_cancels_pending_close(self):
        observed = datetime.now(timezone.utc) - timedelta(minutes=16)
        self.assertFalse(
            inactivity_snapshot_is_still_stale(
                observed_last_active=observed,
                current_last_active=observed,
                now=datetime.now(timezone.utc),
                threshold_seconds=15 * 60,
                human_control_active=True,
            )
        )


class WidgetResponsePolicyTests(unittest.TestCase):
    def test_empty_widget_response_gets_safe_fallback(self):
        self.assertEqual(
            apply_widget_empty_response_fallback("", "widget"),
            WIDGET_EMPTY_RESPONSE_FALLBACK,
        )

    def test_nonempty_widget_response_is_unchanged(self):
        response = "La oficina se encuentra en La Leona."
        self.assertEqual(
            apply_widget_empty_response_fallback(response, "widget"),
            response,
        )

    def test_empty_whatsapp_response_is_not_changed(self):
        self.assertEqual(
            apply_widget_empty_response_fallback("", "wa_direct"),
            "",
        )


class TransferAuthorizationTests(unittest.TestCase):
    def authorize(self, **overrides):
        values = {
            "explicit_handoff": False,
            "reason": "",
            "reason_code": None,
            "report_intent": False,
            "has_report_session": False,
            "greeting_only": False,
            "emergency_related": False,
            "already_transferred": False,
        }
        values.update(overrides)
        return authorize_transfer(**values)

    def test_explicit_request_is_allowed(self):
        allowed, decision = self.authorize(explicit_handoff=True)
        self.assertTrue(allowed)
        self.assertEqual(decision, "explicit_user_request")

    def test_arbitrary_model_transfer_is_blocked(self):
        allowed, decision = self.authorize(reason="El usuario necesita un operador")
        self.assertFalse(allowed)
        self.assertEqual(decision, "missing_authorized_reason")

    def test_verified_missing_context_is_allowed(self):
        allowed, decision = self.authorize(
            reason_code="verified_no_context",
            reason="No cuento con información para resolver la consulta",
        )
        self.assertTrue(allowed)
        self.assertEqual(decision, "verified_no_context")

    def test_tool_failure_keeps_its_reason_code(self):
        allowed, decision = self.authorize(
            reason_code="tool_failure",
            reason="get_ubicaciones falló con timeout",
        )
        self.assertTrue(allowed)
        self.assertEqual(decision, "tool_failure")

    def test_reason_code_without_explanation_is_blocked(self):
        allowed, decision = self.authorize(reason_code="verified_no_context")
        self.assertFalse(allowed)
        self.assertEqual(decision, "missing_authorized_reason")

    def test_missing_context_cannot_escape_report_flow(self):
        allowed, decision = self.authorize(
            reason_code="verified_no_context",
            reason="No existe información para resolver la consulta",
            report_intent=True,
        )
        self.assertFalse(allowed)
        self.assertEqual(decision, "known_report_flow")

    def test_emergency_is_not_automatically_transferred(self):
        allowed, decision = self.authorize(
            reason_code="verified_no_context",
            reason="No existe información para resolver la consulta",
            emergency_related=True,
        )
        self.assertFalse(allowed)
        self.assertEqual(decision, "known_emergency_flow")

    def test_duplicate_transfer_is_blocked(self):
        allowed, decision = self.authorize(
            explicit_handoff=True,
            already_transferred=True,
        )
        self.assertFalse(allowed)
        self.assertEqual(decision, "already_transferred")

    def test_affirmative_reply_accepts_immediately_preceding_handoff_offer(self):
        previous = "¿Deseas que te comunique con un agente humano para verificarlo?"
        self.assertTrue(is_contextual_handoff_request("Sí Sam", previous))
        self.assertTrue(is_contextual_handoff_request("Porfa", previous))
        self.assertTrue(is_contextual_handoff_request("sí por favor", previous))
        self.assertTrue(is_contextual_handoff_request("Claro que sí, gracias", previous))
        self.assertTrue(is_contextual_handoff_request("Me gustaría", previous))

    def test_pronoun_request_uses_immediately_preceding_agent_context(self):
        self.assertTrue(
            is_contextual_handoff_request(
                "¿Me puedes comunicar con uno?",
                "Para solicitar la cancelación necesitas atención de un agente ciudadano.",
            )
        )

    def test_unrelated_affirmative_is_not_a_handoff(self):
        self.assertFalse(
            is_contextual_handoff_request(
                "Sí",
                "¿La luminaria está apagada por completo?",
            )
        )
        self.assertFalse(
            is_contextual_handoff_request(
                "Sí por favor",
                "¿Deseas agregar una imagen al reporte?",
            )
        )


if __name__ == "__main__":
    unittest.main()
