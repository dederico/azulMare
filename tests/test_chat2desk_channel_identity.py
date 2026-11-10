import unittest

from app.services.chat2desk_channel_identity import (
    extract_chat2desk_channel_identity,
    normalize_contact_phone,
    resolve_report_contact_phone,
    webhook_conversation_key,
)


class Chat2DeskChannelIdentityTests(unittest.TestCase):
    def test_whatsapp_preserves_phone_as_conversation_key(self):
        identity = extract_chat2desk_channel_identity(
            {
                "transport": "wa_direct",
                "channel_id": 43906,
                "client_id": 305183524,
                "client": {"id": 305183524, "phone": "+52 1 81 1212 1212"},
            }
        )

        self.assertEqual(identity.conversation_key, "5218112121212")
        self.assertEqual(identity.contact_phone, "5218112121212")
        self.assertFalse(identity.uses_platform_identity)

    def test_telegram_id_is_scoped_and_is_not_treated_as_phone(self):
        payload = {
            "transport": "telegram_api",
            "channel_id": 44010,
            "client_id": 9001,
            "client": {"id": 9001, "phone": "[tg] 249695626"},
        }
        identity = extract_chat2desk_channel_identity(payload)

        self.assertEqual(
            identity.conversation_key,
            "chat2desk:telegram_api:channel:44010:client:9001",
        )
        self.assertIsNone(identity.contact_phone)
        self.assertEqual(webhook_conversation_key(payload), identity.conversation_key)

    def test_official_chat2desk_telegram_webhook_shape(self):
        identity = extract_chat2desk_channel_identity(
            {
                "message_id": 115816153,
                "type": "from_client",
                "text": "Hello!",
                "transport": "telegram",
                "client_id": 30247382,
                "dialog_id": 4236638,
                "channel_id": 18337,
                "client": {
                    "id": 30247382,
                    "phone": "[tg] 734937551",
                    "client_phone": "",
                    "name": "Olga",
                },
                "hook_type": "inbox",
            }
        )

        self.assertEqual(
            identity.conversation_key,
            "chat2desk:telegram:channel:18337:client:30247382",
        )
        self.assertIsNone(identity.contact_phone)

    def test_facebook_and_telegram_ids_cannot_collide(self):
        telegram = extract_chat2desk_channel_identity(
            {
                "transport": "telegram_api",
                "channel_id": 10,
                "client_id": 123,
                "client": {"phone": "123"},
            }
        )
        facebook = extract_chat2desk_channel_identity(
            {
                "transport": "facebook_messenger",
                "channel_id": 11,
                "client_id": 123,
                "client": {"phone": "123"},
            }
        )

        self.assertNotEqual(telegram.conversation_key, facebook.conversation_key)

    def test_shared_phone_is_contact_data_but_does_not_replace_platform_key(self):
        identity = extract_chat2desk_channel_identity(
            {
                "transport": "facebook",
                "channel_id": 22,
                "client_id": 456,
                "client": {
                    "id": 456,
                    "phone": "[fb] 99887766",
                    "client_phone": "+52 81 1234 5678",
                },
            }
        )

        self.assertEqual(identity.contact_phone, "528112345678")
        self.assertEqual(
            identity.conversation_key,
            "chat2desk:facebook:channel:22:client:456",
        )

    def test_widget_without_phone_gets_stable_scoped_key(self):
        identity = extract_chat2desk_channel_identity(
            {
                "transport": "widget",
                "channel_id": 1,
                "client_id": 77,
                "dialog_id": 88,
                "client": {"id": 77, "phone": None},
            }
        )

        self.assertEqual(
            identity.conversation_key,
            "chat2desk:widget:channel:1:client:77",
        )

    def test_messenger_identifier_never_normalizes_as_phone(self):
        self.assertIsNone(normalize_contact_phone("[tg] 249695626"))

    def test_platform_conversation_key_is_never_sent_as_report_phone(self):
        conversation_key = "chat2desk:telegram:channel:44:client:249695626"

        self.assertIsNone(
            resolve_report_contact_phone(
                conversation_key,
                {"uses_platform_identity": True},
            )
        )

    def test_explicitly_shared_phone_can_be_used_for_platform_report(self):
        conversation_key = "chat2desk:facebook:channel:45:client:9988"

        self.assertEqual(
            resolve_report_contact_phone(
                conversation_key,
                {
                    "uses_platform_identity": True,
                    "contact_phone": "+52 81 1234 5678",
                },
            ),
            "528112345678",
        )

    def test_whatsapp_conversation_key_remains_report_phone(self):
        self.assertEqual(
            resolve_report_contact_phone(
                "5218112121212",
                {"uses_platform_identity": False},
            ),
            "5218112121212",
        )


if __name__ == "__main__":
    unittest.main()
