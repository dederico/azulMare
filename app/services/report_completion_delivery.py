"""Durable state for a CIAC folio whose citizen notification is pending."""

from __future__ import annotations

from typing import Any


PENDING_COMPLETION_KEY = "pending_completion_delivery"


def build_report_completion_message(folio: str, image_count: int = 0) -> str:
    image_text = f"con {int(image_count)} imágenes " if image_count else ""
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
