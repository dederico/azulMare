import time
import unittest

from app.services.conversation_control import (
    activate_human_control,
    get_active_human_control,
    normalize_phone_key,
    release_human_control,
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


if __name__ == "__main__":
    unittest.main()
