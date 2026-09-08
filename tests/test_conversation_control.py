import time
import unittest
from unittest.mock import patch

import app.services.conversation_control as conversation_control

from app.services.conversation_control import (
    activate_human_control,
    consume_human_control,
    get_active_human_control,
    normalize_phone_key,
    release_human_control,
    release_human_control_if_matches,
)


class ConversationControlTests(unittest.TestCase):
    phone = "+52 1 81 1234 5678"

    def tearDown(self):
        release_human_control(self.phone)

    def test_phone_normalization(self):
        self.assertEqual(normalize_phone_key(self.phone), "5218112345678")

    def test_active_takeover_is_shared_through_canonical_key(self):
        activate_human_control(
            self.phone,
            expires_at=time.time() + 60,
            source="test",
        )

        control = get_active_human_control("5218112345678")
        self.assertIsNotNone(control)
        self.assertEqual(control["mode"], "human")
        self.assertEqual(control["source"], "test")

    def test_expired_takeover_is_released(self):
        activate_human_control(
            self.phone,
            expires_at=time.time() - 1,
            source="test",
        )

        self.assertIsNone(get_active_human_control(self.phone))

    def test_takeover_without_expiration_requires_explicit_release(self):
        activate_human_control(
            self.phone,
            expires_at=None,
            source="test",
        )

        control = get_active_human_control(self.phone)
        self.assertIsNotNone(control)
        self.assertIsNone(control["expires_at"])

        release_human_control(self.phone)
        self.assertIsNone(get_active_human_control(self.phone))

    def test_conditional_release_cannot_remove_a_newer_takeover(self):
        activate_human_control(
            self.phone,
            expires_at=None,
            source="confirmed_operator_outbox:1",
            transfer_message_id=200,
        )

        self.assertFalse(release_human_control_if_matches(self.phone, 100))
        self.assertIsNotNone(get_active_human_control(self.phone))
        self.assertTrue(release_human_control_if_matches(self.phone, 200))
        self.assertIsNone(get_active_human_control(self.phone))

    def test_persistent_absence_clears_stale_replica_memory(self):
        class EmptyCursor:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_value, traceback):
                return False

            def execute(self, query, params):
                return None

            def fetchone(self):
                return None

        class EmptyConnection:
            def cursor(self):
                return EmptyCursor()

            def close(self):
                return None

        activate_human_control(
            self.phone,
            expires_at=None,
            source="stale-replica-test",
        )

        with (
            patch.object(conversation_control, "ensure_conversation_control_storage", return_value=True),
            patch.object(conversation_control, "_connect", return_value=EmptyConnection()),
        ):
            self.assertIsNone(get_active_human_control(self.phone, storage=object()))

        self.assertIsNone(get_active_human_control(self.phone))

    def test_trusted_takeover_can_only_be_consumed_once(self):
        activate_human_control(
            self.phone,
            expires_at=None,
            source="chat2desk_takeover_message",
        )

        first = consume_human_control(self.phone)
        second = consume_human_control(self.phone)

        self.assertIsNotNone(first)
        self.assertEqual(first["source"], "chat2desk_takeover_message")
        self.assertIsNone(second)

    def test_all_human_takeover_sources_can_be_consumed_by_authoritative_return(self):
        for source in (
            "explicit_user_request",
            "chat2desk_takeover_message",
            "confirmed_operator_outbox:228531",
            "tool:verified_no_context",
            "dialog_transferred:228522",
        ):
            activate_human_control(
                self.phone,
                expires_at=None,
                source=source,
            )
            consumed = consume_human_control(self.phone)
            self.assertIsNotNone(consumed)
            self.assertEqual(consumed["source"], source)


if __name__ == "__main__":
    unittest.main()
