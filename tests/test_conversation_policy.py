import unittest
from datetime import datetime, timedelta, timezone

from app.services.conversation_policy import (
    automatic_report_timeouts_enabled,
    authorize_transfer,
    classify_emergency_answer,
    extract_confirmed_folio,
    inactivity_snapshot_is_still_stale,
    is_bot_return_message,
    is_human_takeover_message,
    is_known_automated_outbound,
    is_non_authoritative_control_source,
    is_trusted_human_control,
    is_verified_public_phone,
    should_replace_unconfirmed_transfer_response,
    should_confirm_operator_outbox_takeover,
    should_accept_bot_return_event,
    should_send_initial_greeting,
)


class AutomaticReportPolicyTests(unittest.TestCase):
    def test_automatic_reports_are_disabled_by_default(self):
        self.assertFalse(automatic_report_timeouts_enabled(None))
        self.assertFalse(automatic_report_timeouts_enabled("false"))

    def test_automatic_reports_require_explicit_opt_in(self):
        self.assertTrue(automatic_report_timeouts_enabled("true"))


class FolioValidationTests(unittest.TestCase):
    def test_accepts_only_numeric_backend_folio(self):
        self.assertEqual(extract_confirmed_folio("Folio: 471149"), "471149")
        self.assertEqual(extract_confirmed_folio("Folio: *471149*"), "471149")

    def test_rejects_errors_disguised_as_folios(self):
        self.assertIsNone(extract_confirmed_folio("Folio: Error 500"))
        self.assertIsNone(extract_confirmed_folio("Error al procesar la solicitud"))
        self.assertIsNone(extract_confirmed_folio("No pude crear el reporte"))


class PublicPhoneValidationTests(unittest.TestCase):
    def test_official_public_numbers_are_allowed(self):
        self.assertTrue(is_verified_public_phone("81 89 88 20 00"))
        self.assertTrue(is_verified_public_phone("81 84 00 44 00"))
        self.assertTrue(is_verified_public_phone("81 12 12 12 12"))

    def test_unverified_number_is_rejected(self):
        self.assertFalse(is_verified_public_phone("81 89 88 11 00"))


class EmergencyClassificationTests(unittest.TestCase):
    def test_natural_negative_answer(self):
        self.assertIs(classify_emergency_answer("No es una emergencia"), False)

    def test_natural_positive_answer(self):
        self.assertIs(classify_emergency_answer("Emergencia ya que es agua potable"), True)

    def test_risk_answer(self):
        self.assertIs(classify_emergency_answer("Puede ocasionar un socavón"), True)


class HumanControlPolicyTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
