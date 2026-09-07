import unittest

import app.services.inbound_processing as inbound_processing
from app.services.inbound_processing import (
    claim_inbound_processing,
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


if __name__ == "__main__":
    unittest.main()
