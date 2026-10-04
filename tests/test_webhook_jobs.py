import unittest
from unittest.mock import MagicMock, patch

from app.services.webhook_jobs import (
    build_webhook_event_key,
    has_newer_pending_inbound_job,
)


class WebhookJobTests(unittest.TestCase):
    def test_message_events_have_stable_transport_specific_key(self):
        payload = {
            "message_id": 970590378,
            "hook_type": "inbox",
            "type": "from_client",
            "text": "Hola",
        }
        self.assertEqual(
            build_webhook_event_key(payload),
            "inbox:from_client:970590378",
        )

    def test_inbox_and_outbox_with_same_id_do_not_collide(self):
        inbound = {
            "message_id": 1,
            "hook_type": "inbox",
            "type": "from_client",
        }
        outbound = {
            "message_id": 1,
            "hook_type": "outbox",
            "type": "to_client",
        }
        self.assertNotEqual(
            build_webhook_event_key(inbound),
            build_webhook_event_key(outbound),
        )

    def test_events_without_message_id_use_stable_hash(self):
        first = {"hook_type": "dialog_transferred", "dialog_id": 22, "client_id": 3}
        second = {"client_id": 3, "dialog_id": 22, "hook_type": "dialog_transferred"}
        self.assertEqual(
            build_webhook_event_key(first),
            build_webhook_event_key(second),
        )

    @patch("app.services.webhook_jobs.ensure_webhook_job_storage", return_value=True)
    @patch("app.services.webhook_jobs._connect")
    def test_detects_newer_pending_inbound_for_same_conversation(
        self,
        connect,
        _ensure_storage,
    ):
        cursor = MagicMock()
        cursor.fetchone.return_value = (True,)
        connection = MagicMock()
        connection.cursor.return_value.__enter__.return_value = cursor
        connect.return_value = connection

        found = has_newer_pending_inbound_job(
            MagicMock(),
            conversation_key="5218125868648",
            current_job_id=120,
        )

        self.assertTrue(found)
        parameters = cursor.execute.call_args.args[1]
        self.assertEqual(parameters, ("5218125868648", 120))


if __name__ == "__main__":
    unittest.main()
