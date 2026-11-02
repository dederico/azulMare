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
    assert config.confirmation_retry_seconds == 300
    assert config.pending_replay_window_seconds == 1800
    assert config.allowed_phone_numbers == frozenset()


def test_optional_phone_allowlist_normalizes_common_formats():
    config = enabled_config(
        WHATSAPP_FAILOVER_ALLOWED_PHONES="+52 1 81 1234 5678, 5218187654321"
    )

    assert failover.is_phone_allowed_for_failover("52-1-81-1234-5678", config)
    assert failover.is_phone_allowed_for_failover("5218187654321", config)
    assert not failover.is_phone_allowed_for_failover("5218111111111", config)


def test_builds_chat2desk_hsm_command():
    assert (
        failover.build_failover_hsm_text(enabled_config())
        == "@HSM@\ncontinuidad_canal_temporal|es_mx"
    )


@pytest.mark.parametrize(
    "text",
    [
        "CONTINUAR.",
        "continuar",
        "« @HSM@\ncontinuidad_canal_temporal|es_mx »\nCONTINUAR.",
    ],
)
def test_recognizes_failover_confirmation_text(text):
    assert failover.is_failover_confirmation_text(text, enabled_config())


def test_does_not_treat_ordinary_citizen_text_as_transport_confirmation():
    assert not failover.is_failover_confirmation_text(
        "Quiero continuar con mi reporte de un bache",
        enabled_config(),
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
    assert decision["action"] == "send_hsm"

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

    activation = failover.activate_failover_and_list_pending(
        None,
        phone_number="5218112345678",
        failover_client_id=202,
        config=config,
    )
    assert activation["activated"] is True
    assert activation["previous_status"] == "awaiting_confirmation"
    pending = activation["pending_messages"]
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
    assert decision["action"] == "send_hsm"
    assert decision["reason"] == "new_or_expired_route"


def test_unconfirmed_hsm_is_retried_after_timeout_and_old_pending_expires():
    config = enabled_config(
        WHATSAPP_FAILOVER_CONFIRMATION_RETRY_SECONDS="30",
        WHATSAPP_FAILOVER_PENDING_REPLAY_WINDOW_SECONDS="60",
    )
    phone = "5218112345678"
    first = inbound("original-old", "Mensaje de hace varios días")
    failover.stage_primary_inbound(
        None,
        phone_number=phone,
        primary_client_id=101,
        payload=first,
        config=config,
    )
    failover.mark_failover_hsm_result(
        None,
        phone_number=phone,
        success=True,
    )
    with failover._memory_lock:
        failover._memory_routes[phone]["hsm_sent_at"] = time.time() - 31
        failover._memory_pending[(phone, "original-old")]["created_at"] = (
            time.time() - 120
        )

    decision = failover.stage_primary_inbound(
        None,
        phone_number=phone,
        primary_client_id=101,
        payload=inbound("original-new", "Mensaje nuevo"),
        config=config,
    )

    assert decision == {
        "action": "send_hsm",
        "reason": "confirmation_timeout",
        "expired_pending": 1,
    }
    with failover._memory_lock:
        assert failover._memory_pending[(phone, "original-old")]["status"] == "expired"
        assert failover._memory_pending[(phone, "original-new")]["status"] == "pending"

    failover.mark_failover_hsm_result(None, phone_number=phone, success=True)
    activation = failover.activate_failover_and_list_pending(
        None,
        phone_number=phone,
        failover_client_id=202,
        config=config,
    )
    assert [
        row["original_message_id"] for row in activation["pending_messages"]
    ] == ["original-new"]


def test_late_confirmation_keeps_at_least_latest_pending_message():
    config = enabled_config(
        WHATSAPP_FAILOVER_PENDING_REPLAY_WINDOW_SECONDS="60",
    )
    phone = "5218112345678"
    failover.stage_primary_inbound(
        None,
        phone_number=phone,
        primary_client_id=101,
        payload=inbound("only-pending", "Todavía necesito ayuda"),
        config=config,
    )
    failover.mark_failover_hsm_result(None, phone_number=phone, success=True)
    with failover._memory_lock:
        failover._memory_pending[(phone, "only-pending")]["created_at"] = (
            time.time() - 3600
        )

    activation = failover.activate_failover_and_list_pending(
        None,
        phone_number=phone,
        failover_client_id=202,
        config=config,
    )

    assert activation["activated"] is True
    assert activation["previous_status"] == "awaiting_confirmation"
    assert activation["expired_pending"] == 0
    assert [
        row["original_message_id"] for row in activation["pending_messages"]
    ] == ["only-pending"]


def test_existing_active_route_does_not_consume_ordinary_temporary_messages():
    config = enabled_config()
    phone = "5218112345678"
    failover.stage_primary_inbound(
        None,
        phone_number=phone,
        primary_client_id=101,
        payload=inbound("original-1"),
        config=config,
    )
    first_activation = failover.activate_failover_and_list_pending(
        None,
        phone_number=phone,
        failover_client_id=202,
        config=config,
    )
    failover.mark_pending_replayed(
        None,
        phone_number=phone,
        original_message_id="original-1",
    )

    second_activation = failover.activate_failover_and_list_pending(
        None,
        phone_number=phone,
        failover_client_id=202,
        config=config,
    )

    assert first_activation["activated"] is True
    assert second_activation == {
        "activated": False,
        "previous_status": "active",
        "expired_pending": 0,
        "pending_messages": [],
    }


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
