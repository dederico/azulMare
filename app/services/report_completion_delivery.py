"""Durable state for a CIAC folio whose citizen notification is pending."""

from __future__ import annotations

from typing import Any


PENDING_COMPLETION_KEY = "pending_completion_delivery"
COMPLETION_CONTEXT_KEY = "completion_delivery_context"


def bind_report_completion_context(
    session: dict[str, Any],
    *,
    request_id: str,
    origin_uid: str,
    origin_message_id: str,
    client_id: str | int,
    channel_id: str | int,
    transport: str,
) -> dict[str, Any]:
    """Bind a future CIAC result to the inbound turn that requested it.

    Model tool calls can create the folio before the route regains control.  The
    origin therefore has to be present in the report session *before* model
    generation starts; otherwise a later citizen message can be mistaken for
    the report-completion retry.
    """

    context = {
        "request_id": str(request_id),
        "origin_uid": str(origin_uid),
        "origin_message_id": str(origin_message_id),
        "client_id": client_id,
        "channel_id": channel_id,
        "transport": str(transport),
    }
    session[COMPLETION_CONTEXT_KEY] = context
    return context


def resolve_report_completion_origin(
    completion: dict[str, Any] | None,
) -> tuple[str, str]:
    """Return an origin that can never impersonate a later inbound message.

    Older completion rows predate origin metadata.  Using the current inbound
    UID as their fallback makes that unrelated citizen turn look like the turn
    that created the old folio and causes it to be consumed.  A stable outbox
    identity keeps delivery idempotent while allowing the new turn to continue.
    """

    completion = completion or {}
    anchor = str(
        completion.get("request_id")
        or completion.get("folio")
        or "unknown"
    ).strip()
    legacy_identity = f"completion-outbox:{anchor}"
    origin_uid = str(completion.get("origin_uid") or legacy_identity)
    origin_message_id = str(
        completion.get("origin_message_id") or legacy_identity
    )
    return origin_uid, origin_message_id


def report_completion_belongs_to_inbound(
    completion: dict[str, Any] | None,
    inbound_uid: str | int | None,
) -> bool:
    """Confirm that a pending completion was created by this exact turn."""

    if (
        not completion
        or completion.get("notified_at")
        or not str(completion.get("folio") or "").strip()
        or not str(completion.get("notification_message") or "").strip()
    ):
        return False
    origin_uid, _ = resolve_report_completion_origin(completion)
    return bool(inbound_uid not in (None, "") and origin_uid == str(inbound_uid))


def build_report_completion_message(folio: str, image_count: int = 0) -> str:
    count = int(image_count)
    if count == 1:
        image_text = "con 1 imagen "
    elif count > 1:
        image_text = f"con {count} imágenes "
    else:
        image_text = ""
    return (
        "Tu reporte ha sido generado con éxito. El número de folio para tu "
        f"reporte es {folio}. Tu reporte {image_text}ha sido enviado al sistema. "
        "Agradecemos mucho tu colaboración. Estamos para servirte"
    )


def stage_report_completion_delivery(
    session: dict[str, Any],
    *,
    folio: str,
    message: str,
    request_id: str,
    location: str,
    image_count: int,
    origin_uid: str,
    origin_message_id: str,
    client_id: str | int,
    channel_id: str | int,
    transport: str,
) -> dict[str, Any]:
    """Keep the confirmed folio until its WhatsApp message is delivered."""

    pending = {
        "folio": str(folio),
        "message": str(message),
        "request_id": str(request_id),
        "location": str(location),
        "image_count": int(image_count),
        "origin_uid": str(origin_uid),
        "origin_message_id": str(origin_message_id),
        "client_id": client_id,
        "channel_id": channel_id,
        "transport": str(transport),
    }
    session[PENDING_COMPLETION_KEY] = pending
    return pending


def get_pending_report_completion(session: dict[str, Any] | None) -> dict[str, Any] | None:
    pending = (session or {}).get(PENDING_COMPLETION_KEY)
    if not isinstance(pending, dict):
        return None
    if not str(pending.get("folio") or "").strip():
        return None
    if not str(pending.get("message") or "").strip():
        return None
    return pending
