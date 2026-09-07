import unittest
from datetime import datetime, timedelta, timezone

from app.services.conversation_policy import (
    authorize_transfer,
    classify_emergency_answer,
    inactivity_snapshot_is_still_stale,
    is_known_automated_outbound,
    should_send_initial_greeting,
    should_activate_human_control,
)


class EmergencyClassificationTests(unittest.TestCase):
    def test_natural_negative_answer(self):
        self.assertIs(classify_emergency_answer("No es una emergencia"), False)

    def test_natural_positive_answer(self):
        self.assertIs(classify_emergency_answer("Emergencia ya que es agua potable"), True)

    def test_risk_answer(self):
        self.assertIs(classify_emergency_answer("Puede ocasionar un socavón"), True)


class OperatorOutboxClassificationTests(unittest.TestCase):
    def test_human_operator_message_activates_control(self):
        self.assertTrue(
            should_activate_human_control(
                message_type="to_client",
                hook_type="outbox",
                operator_id=228544,
                is_bot_echo=False,
                recently_returned_to_bot=False,
            )
        )

    def test_same_operator_on_bot_echo_does_not_activate_control(self):
        self.assertFalse(
            should_activate_human_control(
                message_type="to_client",
                hook_type="outbox",
                operator_id=228544,
                is_bot_echo=True,
                recently_returned_to_bot=False,
            )
        )

    def test_outbox_without_operator_does_not_activate_control(self):
        self.assertFalse(
            should_activate_human_control(
                message_type="to_client",
                hook_type="outbox",
                operator_id=None,
                is_bot_echo=False,
                recently_returned_to_bot=False,
            )
        )

    def test_return_to_bot_grace_suppresses_takeover(self):
        self.assertFalse(
            should_activate_human_control(
                message_type="to_client",
                hook_type="outbox",
                operator_id=228544,
                is_bot_echo=False,
                recently_returned_to_bot=True,
            )
        )

    def test_stale_operator_outbox_does_not_activate_control(self):
        self.assertFalse(
            should_activate_human_control(
                message_type="to_client",
                hook_type="outbox",
                operator_id=228544,
                is_bot_echo=False,
                recently_returned_to_bot=False,
                event_is_stale=True,
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
