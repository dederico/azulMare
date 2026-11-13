import ast
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.services.chat2desk_channel_identity import (
    extract_chat2desk_channel_identity,
    normalize_contact_phone,
    resolve_report_contact_phone,
    webhook_conversation_key,
)
from app.services.conversation_control import (
    activate_human_control,
    get_active_human_control,
    release_human_control,
)
from app.services.whatsapp_failover import load_whatsapp_failover_config


class Chat2DeskChannelIdentityTests(unittest.TestCase):
    def test_process_request_never_replaces_platform_conversation_key_with_client_phone(self):
        source = Path("app/api/original_routes.py").read_text(encoding="utf-8")
        module = ast.parse(source)
        handler = next(
            node
            for node in module.body
            if isinstance(node, ast.AsyncFunctionDef)
            and node.name == "_process_whatsapp_request"
        )
        assignments = [
            node
            for node in ast.walk(handler)
            if isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name) and target.id == "from_number"
                for target in node.targets
            )
        ]
        canonical_assignment = next(
            node
            for node in assignments
            if ast.unparse(node.value) == "channel_identity.conversation_key"
        )
        raw_phone_reassignments = [
            node.lineno
            for node in assignments
            if node.lineno > canonical_assignment.lineno
            and "payload" in ast.unparse(node.value)
            and "client" in ast.unparse(node.value)
            and "phone" in ast.unparse(node.value)
        ]

        self.assertEqual(
            raw_phone_reassignments,
            [],
            "Facebook/Telegram must retain channel_identity.conversation_key; "
            "payload.client.phone cannot replace it later in the handler.",
        )

    def test_campaign_guards_use_contact_phone_not_scoped_conversation_key(self):
        source = Path("app/api/original_routes.py").read_text(encoding="utf-8")
        module = ast.parse(source)
        handler = next(
            node
            for node in module.body
            if isinstance(node, ast.AsyncFunctionDef)
            and node.name == "_process_whatsapp_request"
        )
        guarded_calls = [
            node
            for node in ast.walk(handler)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id
            in {
                "record_outgoing_campaign_reply",
                "get_active_proactive_campaign_guard",
            }
        ]

        self.assertEqual(len(guarded_calls), 2)
        self.assertTrue(
            all(ast.unparse(call.args[1]) == "contact_phone" for call in guarded_calls)
        )
        parents = {
            child: parent
            for parent in ast.walk(handler)
            for child in ast.iter_child_nodes(parent)
        }
        for call in guarded_calls:
            ancestor = parents.get(call)
            while ancestor is not None and not isinstance(ancestor, ast.If):
                ancestor = parents.get(ancestor)
            self.assertIsNotNone(ancestor)
            self.assertIn(
                "is_phone_transport(transport)",
                ast.unparse(ancestor.test),
            )

        special_number_guard = next(
            node
            for node in ast.walk(handler)
            if isinstance(node, ast.If)
            and "SPECIAL_NUMBER" in ast.unparse(node.test)
        )
        self.assertIn(
            "is_phone_transport(transport)",
            ast.unparse(special_number_guard.test),
        )

    def test_failover_identity_only_collapses_allowlisted_phone(self):
        config = load_whatsapp_failover_config(
            {
                "WHATSAPP_CHANNEL_ROUTING_MODE": "failover",
                "WHATSAPP_PRIMARY_CHANNEL_ID": "43906",
                "WHATSAPP_FAILOVER_CHANNEL_ID": "43943",
                "WHATSAPP_FAILOVER_ALLOWED_PHONES": "5215625189364",
            }
        )

        def payload(phone, channel_id):
            return {
                "transport": "wa_direct",
                "channel_id": channel_id,
                "client_id": channel_id,
                "client": {"id": channel_id, "phone": phone},
            }

        with patch(
            "app.services.chat2desk_channel_identity."
            "load_whatsapp_failover_config",
            return_value=config,
        ):
            allowed_primary = extract_chat2desk_channel_identity(
                payload("5215625189364", 43906)
            )
            allowed_temporary = extract_chat2desk_channel_identity(
                payload("5215625189364", 43943)
            )
            excluded_primary = extract_chat2desk_channel_identity(
                payload("5218112121212", 43906)
            )
            excluded_temporary = extract_chat2desk_channel_identity(
                payload("5218112121212", 43943)
            )

        self.assertEqual(
            allowed_primary.conversation_key,
            allowed_temporary.conversation_key,
        )
        self.assertIn(":failover:phone:5215625189364", allowed_primary.conversation_key)
        self.assertNotEqual(
            excluded_primary.conversation_key,
            excluded_temporary.conversation_key,
        )
        self.assertIn(":channel:43906:", excluded_primary.conversation_key)
        self.assertIn(":channel:43943:", excluded_temporary.conversation_key)

    def test_whatsapp_channels_isolate_conversation_state_and_keep_contact_phone(self):
        primary_payload = {
            "transport": "wa_direct",
            "channel_id": 43906,
            "client_id": 101,
            "client": {"id": 101, "phone": "+52 1 81 1212 1212"},
        }
        temporary_payload = {
            "transport": "wa_direct",
            "channel_id": 43943,
            "client_id": 101,
            "client": {"id": 101, "phone": "+52 1 81 1212 1212"},
        }
        primary = extract_chat2desk_channel_identity(primary_payload)
        temporary = extract_chat2desk_channel_identity(temporary_payload)

        self.assertEqual(primary.contact_phone, "5218112121212")
        self.assertEqual(temporary.contact_phone, "5218112121212")
        self.assertEqual(
            primary.conversation_key,
            "chat2desk:wa_direct:channel:43906:client:101",
        )
        self.assertEqual(
            temporary.conversation_key,
            "chat2desk:wa_direct:channel:43943:client:101",
        )
        self.assertNotEqual(
            webhook_conversation_key(primary_payload),
            webhook_conversation_key(temporary_payload),
        )

        try:
            activate_human_control(
                primary.conversation_key,
                expires_at=None,
                source="channel-isolation-test",
            )
            self.assertIsNotNone(
                get_active_human_control(primary.conversation_key)
            )
            self.assertIsNone(
                get_active_human_control(temporary.conversation_key)
            )
        finally:
            release_human_control(primary.conversation_key)
            release_human_control(temporary.conversation_key)

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

    def test_scoped_conversation_key_never_normalizes_as_phone(self):
        self.assertIsNone(
            normalize_contact_phone(
                "chat2desk:wa_direct:channel:43906:client:305183524"
            )
        )

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

    def test_whatsapp_scoped_key_keeps_real_phone_for_report(self):
        self.assertEqual(
            resolve_report_contact_phone(
                "chat2desk:wa_direct:channel:43906:client:101",
                {
                    "uses_platform_identity": False,
                    "contact_phone": "5218112121212",
                },
            ),
            "5218112121212",
        )

    def test_whatsapp_scoped_key_without_contact_phone_is_blocked_for_ciac(self):
        self.assertIsNone(
            resolve_report_contact_phone(
                "chat2desk:wa_direct:channel:43906:client:305183524",
                {"uses_platform_identity": False},
            )
        )

    def test_matching_legacy_report_state_is_adopted_by_scoped_channel(self):
        import app.services.report_state as report_state

        identity = extract_chat2desk_channel_identity(
            {
                "transport": "wa_direct",
                "channel_id": 43906,
                "client_id": 305183524,
                "client": {
                    "id": 305183524,
                    "phone": "5218112121212",
                },
            }
        )
        migrated_session = {
            "channel_id": "43906",
            "transport": "wa_direct",
            "contact_phone": "5218112121212",
            "report_intent_confirmed": True,
            "citizen_report_messages": ["Hay un bache"],
        }
        cursor = MagicMock()
        cursor.__enter__.return_value = cursor
        cursor.fetchone.return_value = (
            migrated_session,
            {"selection4": "Hay un bache"},
            3,
        )
        connection = MagicMock()
        connection.cursor.return_value = cursor

        with (
            patch.object(
                report_state,
                "load_report_state",
                return_value=None,
            ),
            patch.object(report_state, "ensure_report_state_storage", return_value=True),
            patch.object(
                report_state,
                "_connect",
                return_value=connection,
            ),
        ):
            adopted = report_state.load_channel_report_state(
                MagicMock(),
                conversation_key=identity.conversation_key,
                contact_phone=identity.contact_phone,
                channel_id=identity.channel_id,
                transport=identity.transport,
                conversation_epoch=3,
            )

        self.assertEqual(adopted["conversation_epoch"], 3)
        self.assertEqual(adopted["report_session"]["channel_id"], "43906")
        sql, params = cursor.execute.call_args_list[0].args
        self.assertIn("ON CONFLICT (phone_number) DO NOTHING", sql)
        self.assertEqual(params[3], 3)
        self.assertIn("DELETE FROM conversation_report_state", cursor.execute.call_args_list[1].args[0])

    def test_stale_legacy_report_epoch_is_not_rewritten_or_adopted(self):
        import app.services.report_state as report_state

        cursor = MagicMock()
        cursor.__enter__.return_value = cursor
        cursor.fetchone.return_value = None
        connection = MagicMock()
        connection.cursor.return_value = cursor

        with (
            patch.object(
                report_state,
                "load_report_state",
                side_effect=[None, None],
            ) as load_state,
            patch.object(report_state, "ensure_report_state_storage", return_value=True),
            patch.object(
                report_state,
                "_connect",
                return_value=connection,
            ),
        ):
            adopted = report_state.load_channel_report_state(
                MagicMock(),
                conversation_key="chat2desk:wa_direct:channel:43906:client:101",
                contact_phone="5218112121212",
                channel_id=43906,
                transport="wa_direct",
                conversation_epoch=8,
            )

        self.assertIsNone(adopted)
        self.assertEqual(load_state.call_count, 2)
        _sql, params = cursor.execute.call_args_list[0].args
        self.assertEqual(params[3], 8)

    def test_platform_transport_never_adopts_legacy_whatsapp_report_state(self):
        import app.services.report_state as report_state

        with (
            patch.object(
                report_state,
                "load_report_state",
                return_value=None,
            ),
            patch.object(
                report_state,
                "ensure_report_state_storage",
                return_value=True,
            ) as ensure_storage,
        ):
            adopted = report_state.load_channel_report_state(
                MagicMock(),
                conversation_key="chat2desk:facebook:channel:43906:client:101",
                contact_phone="5218112121212",
                channel_id=43906,
                transport="facebook",
                conversation_epoch=0,
            )

        self.assertIsNone(adopted)
        ensure_storage.assert_not_called()

    def test_legacy_report_state_from_other_channel_is_not_adopted(self):
        import app.services.report_state as report_state

        identity = extract_chat2desk_channel_identity(
            {
                "transport": "wa_direct",
                "channel_id": 43943,
                "client_id": 305183524,
                "client": {
                    "id": 305183524,
                    "phone": "5218112121212",
                },
            }
        )
        cursor = MagicMock()
        cursor.__enter__.return_value = cursor
        cursor.fetchone.return_value = None
        connection = MagicMock()
        connection.cursor.return_value = cursor

        with (
            patch.object(
                report_state,
                "load_report_state",
                side_effect=[None, None],
            ),
            patch.object(report_state, "ensure_report_state_storage", return_value=True),
            patch.object(report_state, "_connect", return_value=connection),
        ):
            adopted = report_state.load_channel_report_state(
                MagicMock(),
                conversation_key=identity.conversation_key,
                contact_phone=identity.contact_phone,
                channel_id=identity.channel_id,
                transport=identity.transport,
                conversation_epoch=0,
            )

        self.assertIsNone(adopted)


if __name__ == "__main__":
    unittest.main()
