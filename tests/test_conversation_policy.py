import unittest

from app.services.conversation_policy import (
    authorize_transfer,
    classify_emergency_answer,
    resolve_bot_operator_ids,
)


class EmergencyClassificationTests(unittest.TestCase):
    def test_natural_negative_answer(self):
        self.assertIs(classify_emergency_answer("No es una emergencia"), False)

    def test_natural_positive_answer(self):
        self.assertIs(classify_emergency_answer("Emergencia ya que es agua potable"), True)

    def test_risk_answer(self):
        self.assertIs(classify_emergency_answer("Puede ocasionar un socavón"), True)


class BotOperatorClassificationTests(unittest.TestCase):
    def test_current_chat2desk_bot_operator_is_known(self):
        self.assertIn(228544, resolve_bot_operator_ids())

    def test_runtime_operator_ids_extend_defaults(self):
        operator_ids = resolve_bot_operator_ids("228600, 228601")
        self.assertIn(228544, operator_ids)
        self.assertIn(228600, operator_ids)
        self.assertIn(228601, operator_ids)


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
