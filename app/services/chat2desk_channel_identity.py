"""Canonical identities for Chat2Desk conversations across messengers.

WhatsApp normally identifies a citizen by phone number.  Telegram API and
Facebook Messenger do not: Chat2Desk exposes a messenger-specific identifier
instead (for example ``[tg] 123456``).  Treating that identifier as a phone can
both collide across transports and leak a false phone into CIAC.

This module keeps the transport concern outside SAM's conversational engine.
The engine receives one stable conversation key while the real contact phone,
when the citizen has explicitly shared it, remains separate.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any


_API_IDENTITY_MARKERS = ("telegram", "facebook", "messenger")
_PHONE_TRANSPORT_MARKERS = ("whatsapp", "wa_direct", "wa_business")


def normalize_transport(value: Any) -> str:
    normalized = re.sub(
        r"[^a-z0-9_]+",
        "_",
        str(value or "unknown").strip().casefold(),
    ).strip("_")
    return normalized or "unknown"


def normalize_contact_phone(value: Any) -> str | None:
    """Return an E.164-like phone only when the value is genuinely phone-shaped."""

    raw = str(value or "").strip()
    if not raw or re.search(r"\[[a-z]+\]", raw, flags=re.IGNORECASE):
        return None
    digits = re.sub(r"\D", "", raw)
    if 10 <= len(digits) <= 15:
        return digits
    return None


def is_platform_identity_transport(transport: Any) -> bool:
    normalized = normalize_transport(transport)
    return any(marker in normalized for marker in _API_IDENTITY_MARKERS)


def is_phone_transport(transport: Any) -> bool:
    normalized = normalize_transport(transport)
    return any(marker in normalized for marker in _PHONE_TRANSPORT_MARKERS)


@dataclass(frozen=True)
class Chat2DeskChannelIdentity:
    conversation_key: str
    contact_phone: str | None
    transport: str
    client_id: str | None
    channel_id: str | None
    uses_platform_identity: bool

    @property
    def prompt_phone(self) -> str:
        return self.contact_phone or "No disponible en este canal"


def _first_value(*values: Any) -> Any:
    for value in values:
        if value not in (None, ""):
            return value
    return None


def _scoped_key(
    *,
    transport: str,
    channel_id: Any,
    client_id: Any,
    provider_identifier: Any,
    dialog_id: Any,
) -> str:
    identity = _first_value(client_id, provider_identifier, dialog_id, "unknown")
    channel = _first_value(channel_id, "unknown")
    return f"chat2desk:{transport}:channel:{channel}:client:{identity}"


def extract_chat2desk_channel_identity(payload: dict[str, Any]) -> Chat2DeskChannelIdentity:
    """Separate SAM's conversation key from a citizen's optional real phone."""

    client = payload.get("client") or {}
    transport = normalize_transport(payload.get("transport"))
    client_id = _first_value(payload.get("client_id"), client.get("id"))
    channel_id = payload.get("channel_id")
    raw_identifier = _first_value(client.get("phone"), client.get("external_id"))

    platform_identity = is_platform_identity_transport(transport)
    explicit_client_phone = normalize_contact_phone(client.get("client_phone"))

    if platform_identity:
        # Chat2Desk documents that API messengers use identifiers such as
        # "[tg] 249695626" until a citizen explicitly shares a phone number.
        contact_phone = explicit_client_phone
        conversation_key = _scoped_key(
            transport=transport,
            channel_id=channel_id,
            client_id=client_id,
            provider_identifier=raw_identifier,
            dialog_id=payload.get("dialog_id"),
        )
    else:
        inferred_phone = normalize_contact_phone(raw_identifier)
        contact_phone = explicit_client_phone or inferred_phone
        conversation_key = contact_phone or _scoped_key(
            transport=transport,
            channel_id=channel_id,
            client_id=client_id,
            provider_identifier=raw_identifier,
            dialog_id=payload.get("dialog_id"),
        )

    return Chat2DeskChannelIdentity(
        conversation_key=conversation_key,
        contact_phone=contact_phone,
        transport=transport,
        client_id=str(client_id) if client_id not in (None, "") else None,
        channel_id=str(channel_id) if channel_id not in (None, "") else None,
        uses_platform_identity=platform_identity,
    )


def webhook_conversation_key(payload: dict[str, Any]) -> str:
    """Return the same serialization key used by SAM's channel adapter."""

    return extract_chat2desk_channel_identity(payload).conversation_key


def resolve_report_contact_phone(
    conversation_key: str,
    report_session: dict[str, Any] | None,
) -> str | None:
    """Return only a genuine phone number suitable for the CIAC payload.

    A platform identifier can contain digits and still not be a telephone.
    The transport marker captured in the report session is therefore the
    authoritative distinction between a WhatsApp phone and a Facebook or
    Telegram identity.
    """

    session = report_session or {}
    explicit_phone = normalize_contact_phone(session.get("contact_phone"))
    if explicit_phone:
        return explicit_phone
    if session.get("uses_platform_identity"):
        return None
    return normalize_contact_phone(conversation_key)
