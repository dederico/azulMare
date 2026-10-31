import time

import pytest

from app.services import whatsapp_failover as failover


@pytest.fixture(autouse=True)
def clear_memory_failover_state():
    with failover._memory_lock:
        failover._memory_routes.clear()
        failover._memory_pending.clear()
    yield
    with failover._memory_lock:
        failover._memory_routes.clear()
        failover._memory_pending.clear()


def enabled_config(**overrides):
    values = {
        "WHATSAPP_FAILOVER_ENABLED": "true",
        "WHATSAPP_PRIMARY_CHANNEL_ID": "43906",
        "WHATSAPP_FAILOVER_CHANNEL_ID": "43943",
        "WHATSAPP_FAILOVER_TEMPLATE": "continuidad_canal_temporal",
        "WHATSAPP_FAILOVER_TEMPLATE_LANGUAGE": "es_mx",
    }
    values.update(overrides)
    return failover.load_whatsapp_failover_config(values)


def inbound(message_id="original-1", text="Quiero reportar una luminaria"):
    return {
        "message_id": message_id,
        "hook_type": "inbox",
        "type": "from_client",
        "transport": "wa_direct",
        "channel_id": 43906,
        "client_id": 101,
        "client": {"phone": "5218112345678", "name": "Vecino"},
        "text": text,
        "photo": "https://example.test/evidencia.jpg",
        "coordinates": {"latitude": 25.65, "longitude": -100.35},
    }


def test_failover_is_disabled_by_default():
    config = failover.load_whatsapp_failover_config({})

    assert config.enabled is False
    assert config.primary_channel_id == 43906
    assert config.failover_channel_id == 43943


def test_builds_chat2desk_hsm_command():
    assert (
        failover.build_failover_hsm_text(enabled_config())
        == "@HSM@\ncontinuidad_canal_temporal|es_mx"
    )


@pytest.mark.parametrize(
    ("message_type", "transport", "channel_id", "replay", "expected"),
    [
        ("from_client", "wa_direct", 43906, False, True),
        ("from_client", "wa_direct", "43943", False, True),
        ("from_client", "widget", 43906, False, False),
        ("to_client", "wa_direct", 43906, False, False),
        ("from_client", "wa_direct", 99999, False, False),
        ("from_client", "wa_direct", 43943, True, False),
    ],
)
def test_only_intercepts_the_two_whatsapp_channels(
    message_type,
    transport,
    channel_id,
    replay,
    expected,
):
    assert (
        failover.is_failover_candidate(
            config=enabled_config(),
            message_type=message_type,
            transport=transport,
            channel_id=channel_id,
            replay=replay,
        )
        is expected
    )


def test_durable_handoff_flow_preserves_the_full_original_payload():
    config = enabled_config()
    first = inbound()

    decision = failover.stage_primary_inbound(
        None,
        phone_number="5218112345678",
        primary_client_id=101,
        payload=first,
        config=config,
    )
    assert decision == {"action": "send_hsm"}

    failover.mark_failover_hsm_result(
        None,
        phone_number="5218112345678",
        success=True,
    )
    second = inbound("original-2", "También está tirando chispas")
    assert failover.stage_primary_inbound(
        None,
        phone_number="5218112345678",
        primary_client_id=101,
        payload=second,
        config=config,
    ) == {"action": "wait"}

    pending = failover.activate_failover_and_list_pending(
        None,
        phone_number="5218112345678",
        failover_client_id=202,
        config=config,
    )
    assert [row["original_message_id"] for row in pending] == [
        "original-1",
        "original-2",
    ]

    replay = failover.build_failover_replay_payload(
        pending[0]["payload"],
        failover_client_id=202,
        failover_channel_id=43943,
    )
    assert replay["message_id"] == "original-1:sam-failover"
    assert replay["client_id"] == 202
    assert replay["channel_id"] == 43943
    assert replay["photo"] == first["photo"]
    assert replay["coordinates"] == first["coordinates"]
    assert replay["text"] == first["text"]
    assert replay["_sam_failover_replay"] is True


def test_active_route_replays_new_primary_messages_without_another_hsm():
    config = enabled_config()
    payload = inbound()
    failover.stage_primary_inbound(
        None,
        phone_number="5218112345678",
        primary_client_id=101,
        payload=payload,
        config=config,
    )
    failover.activate_failover_and_list_pending(
        None,
        phone_number="5218112345678",
        failover_client_id=202,
        config=config,
    )
    failover.mark_pending_replayed(
        None,
        phone_number="5218112345678",
        original_message_id="original-1",
    )

    decision = failover.stage_primary_inbound(
        None,
        phone_number="5218112345678",
        primary_client_id=101,
        payload=inbound("original-3"),
        config=config,
    )
    assert decision == {"action": "replay", "failover_client_id": "202"}

    assert failover.resolve_failover_outbound(
        None,
        client_id=101,
        channel_id=43906,
        transport="wa_direct",
        phone_number="5218112345678",
        config=config,
    ) == ("202", 43943)


def test_expired_route_requires_a_new_hsm():
    config = enabled_config()
    failover.stage_primary_inbound(
        None,
        phone_number="5218112345678",
        primary_client_id=101,
        payload=inbound(),
        config=config,
    )
    failover.activate_failover_and_list_pending(
        None,
        phone_number="5218112345678",
        failover_client_id=202,
        config=config,
    )
    with failover._memory_lock:
        failover._memory_routes["5218112345678"]["expires_at"] = time.time() - 1

    decision = failover.stage_primary_inbound(
        None,
        phone_number="5218112345678",
        primary_client_id=101,
        payload=inbound("original-4"),
        config=config,
    )
    assert decision == {"action": "send_hsm"}


def test_widget_routing_is_never_changed():
    config = enabled_config()
    assert failover.resolve_failover_outbound(
        None,
        client_id=101,
        channel_id=123,
        transport="widget",
        phone_number="5218112345678",
        config=config,
    ) == (101, 123)

