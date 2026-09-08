import unittest

import app.services.conversation_lifecycle as lifecycle
from app.services.conversation_lifecycle import (
    build_session_key,
    claim_inactivity_close,
    claim_session_greeting,
    get_lifecycle_state,
    inactivity_claim_is_current,
    list_inactivity_candidates,
    mark_inactivity_close_sent,
    mark_reopen_greeting_pending,
    mark_session_greeting_sent,
    record_inbound_activity,
    release_inactivity_claim,
    reset_conversation_lifecycle,
)


class ConversationLifecycleTests(unittest.TestCase):
    def setUp(self):
        lifecycle._memory_state.clear()
        self.phone = "5215625189364"

    def test_session_key_prefers_request_id(self):
        self.assertEqual(build_session_key(114127775, 31675339), "request:114127775")
        self.assertEqual(build_session_key(None, 31675339), "dialog:31675339")

    def test_repeated_new_request_only_claims_one_greeting(self):
        session_key = build_session_key(114127775, 31675339)
        record_inbound_activity(self.phone, 970485004, session_key, now=100)

        self.assertTrue(
            claim_session_greeting(
                self.phone, session_key, boundary_requested=True
            )
        )
        self.assertFalse(
            claim_session_greeting(
                self.phone, session_key, boundary_requested=True
            )
        )

    def test_new_request_id_can_claim_next_session_greeting(self):
        first_key = build_session_key(1, 10)
        second_key = build_session_key(2, 10)
        record_inbound_activity(self.phone, 100, first_key, now=100)
        self.assertTrue(
            claim_session_greeting(self.phone, first_key, boundary_requested=True)
        )
        record_inbound_activity(self.phone, 101, second_key, now=200)
        self.assertTrue(
            claim_session_greeting(self.phone, second_key, boundary_requested=True)
        )

    def test_failed_immediate_return_greeting_is_claimed_by_next_inbound(self):
        session_key = build_session_key(1, 10)
        record_inbound_activity(self.phone, 100, session_key, now=100)
        mark_session_greeting_sent(self.phone, session_key)
        mark_reopen_greeting_pending(self.phone)

        self.assertTrue(
            claim_session_greeting(
                self.phone, session_key, boundary_requested=False
            )
        )

    def test_immediate_return_greeting_blocks_duplicate_inbound_greeting(self):
        session_key = build_session_key(1, 10)
        mark_reopen_greeting_pending(self.phone, reset_activity=True)

        self.assertTrue(
            claim_session_greeting(
                self.phone, session_key, boundary_requested=True
            )
        )
        self.assertFalse(
            claim_session_greeting(
                self.phone, session_key, boundary_requested=True
            )
        )

    def test_human_return_does_not_inherit_old_inactivity_timer(self):
        session_key = build_session_key(1, 10)
        record_inbound_activity(self.phone, 100, session_key, now=100)
        mark_reopen_greeting_pending(self.phone, reset_activity=True)

        self.assertEqual(
            list_inactivity_candidates(threshold_seconds=900, now=5000),
            [],
        )
        self.assertIsNone(get_lifecycle_state(self.phone)["last_inbound_uid"])

    def test_only_one_replica_claims_inactivity_close(self):
        session_key = build_session_key(1, 10)
        record_inbound_activity(self.phone, 100, session_key, now=100)

        first = claim_inactivity_close(
            self.phone, threshold_seconds=900, now=1001
        )
        second = claim_inactivity_close(
            self.phone, threshold_seconds=900, now=1001
        )

        self.assertEqual(first, "100")
        self.assertIsNone(second)

    def test_inactivity_candidates_survive_without_local_session_object(self):
        session_key = build_session_key(1, 10)
        record_inbound_activity(self.phone, 100, session_key, now=100)

        self.assertEqual(
            list_inactivity_candidates(threshold_seconds=900, now=1001),
            [self.phone],
        )

    def test_new_inbound_cancels_pending_inactivity_claim(self):
        session_key = build_session_key(1, 10)
        record_inbound_activity(self.phone, 100, session_key, now=100)
        claim_uid = claim_inactivity_close(
            self.phone, threshold_seconds=900, now=1001
        )
        record_inbound_activity(self.phone, 101, session_key, now=1002)

        self.assertFalse(inactivity_claim_is_current(self.phone, claim_uid))
        self.assertFalse(mark_inactivity_close_sent(self.phone, claim_uid))

    def test_successful_inactivity_close_forces_one_reopen_greeting(self):
        session_key = build_session_key(1, 10)
        record_inbound_activity(self.phone, 100, session_key, now=100)
        mark_session_greeting_sent(self.phone, session_key)
        claim_uid = claim_inactivity_close(
            self.phone, threshold_seconds=900, now=1001
        )
        self.assertTrue(mark_inactivity_close_sent(self.phone, claim_uid))

        record_inbound_activity(self.phone, 101, session_key, now=1002)
        self.assertTrue(
            claim_session_greeting(
                self.phone, session_key, boundary_requested=False
            )
        )
        self.assertFalse(
            claim_session_greeting(
                self.phone, session_key, boundary_requested=False
            )
        )

    def test_failed_close_can_be_retried(self):
        session_key = build_session_key(1, 10)
        record_inbound_activity(self.phone, 100, session_key, now=100)
        claim_uid = claim_inactivity_close(
            self.phone, threshold_seconds=900, now=1001
        )
        release_inactivity_claim(self.phone, claim_uid)

        self.assertEqual(
            claim_inactivity_close(
                self.phone, threshold_seconds=900, now=1002
            ),
            "100",
        )

    def test_state_tracks_newest_numeric_uid(self):
        session_key = build_session_key(1, 10)
        record_inbound_activity(self.phone, 101, session_key, now=100)
        record_inbound_activity(self.phone, 99, session_key, now=200)

        self.assertEqual(get_lifecycle_state(self.phone)["last_inbound_uid"], "101")

    def test_admin_reset_removes_lifecycle_state(self):
        session_key = build_session_key(1, 10)
        record_inbound_activity(self.phone, 101, session_key, now=100)

        self.assertTrue(reset_conversation_lifecycle(self.phone))
        self.assertIsNone(get_lifecycle_state(self.phone))


if __name__ == "__main__":
    unittest.main()
