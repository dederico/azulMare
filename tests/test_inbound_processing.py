import unittest

import app.services.inbound_processing as inbound_processing
from app.services.inbound_processing import (
    claim_inbound_processing,
    is_latest_inbound_processing_claim,
    mark_inbound_processing_delivered,
    release_inbound_processing_claim,
)


class InboundProcessingTests(unittest.TestCase):
    def setUp(self):
        inbound_processing._memory_claims.clear()

    def tearDown(self):
        inbound_processing._memory_claims.clear()

    def test_only_one_worker_can_claim_same_uid(self):
        first = claim_inbound_processing("970485113", "5215625189364")
        second = claim_inbound_processing("970485113", "5215625189364")

        self.assertIsNotNone(first)
        self.assertIsNone(second)

    def test_failed_worker_can_release_claim_for_retry(self):
        first = claim_inbound_processing("970485113", "5215625189364")
        release_inbound_processing_claim("970485113", first)

        self.assertIsNotNone(
            claim_inbound_processing("970485113", "5215625189364")
        )

    def test_delivered_claim_cannot_be_reclaimed(self):
        first = claim_inbound_processing("970485113", "5215625189364")
        mark_inbound_processing_delivered("970485113", first)

        self.assertIsNone(
            claim_inbound_processing("970485113", "5215625189364")
        )

    def test_claim_remains_latest_without_newer_inbound(self):
        first = claim_inbound_processing("970485113", "5215625189364")

        self.assertTrue(
            is_latest_inbound_processing_claim(
                "970485113", "5215625189364", first
            )
        )

    def test_newer_inbound_supersedes_older_response(self):
        first = claim_inbound_processing("970485113", "5215625189364")
        second = claim_inbound_processing("970485114", "5215625189364")

        self.assertFalse(
            is_latest_inbound_processing_claim(
                "970485113", "5215625189364", first
            )
        )
        self.assertTrue(
            is_latest_inbound_processing_claim(
                "970485114", "5215625189364", second
            )
        )

    def test_other_phone_inbound_does_not_supersede_response(self):
        first = claim_inbound_processing("970485113", "5215625189364")
        claim_inbound_processing("970485114", "5218111111111")

        self.assertTrue(
            is_latest_inbound_processing_claim(
                "970485113", "5215625189364", first
            )
        )

    def test_late_delivery_of_older_uid_does_not_supersede_newer_message(self):
        current = claim_inbound_processing("970485114", "5215625189364")
        claim_inbound_processing("970485113", "5215625189364")

        self.assertTrue(
            is_latest_inbound_processing_claim(
                "970485114", "5215625189364", current
            )
        )

    def test_invalid_token_is_not_latest(self):
        claim_inbound_processing("970485113", "5215625189364")

        self.assertFalse(
            is_latest_inbound_processing_claim(
                "970485113", "5215625189364", "invalid-token"
            )
        )


if __name__ == "__main__":
    unittest.main()
