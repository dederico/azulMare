import asyncio
import os
from typing import Any

from app.util.logger import logger
from app.util.rate_limiter import image_processing_queue


DEFAULT_VISION_MODEL = "gpt-4o"
IMAGE_CONTEXT_DECISIONS = {"report", "consultation", "unclear"}


def _response_output_text(response: Any) -> str:
    text = getattr(response, "output_text", "") or ""
    if text:
        return str(text).strip()

    fragments: list[str] = []
    for item in getattr(response, "output", None) or []:
        if getattr(item, "type", None) != "message":
            continue
        for content in getattr(item, "content", None) or []:
            if getattr(content, "type", None) == "output_text":
                value = getattr(content, "text", "") or ""
                if value:
                    fragments.append(str(value))
    return "".join(fragments).strip()


async def analyze_image_url(client, photo_url: str, *, queue=None) -> str | None:
    """Describe a public image URL without downloading it through the webhook.

    Chat2Desk storage occasionally takes longer than the old ten-second local
    download timeout.  Passing the URL directly to Responses removes that
    failure point and keeps the synchronous SDK call off the event loop.
    """
    if not isinstance(photo_url, str) or not photo_url.startswith(("http://", "https://")):
        logger.error("Image analysis rejected an invalid URL: %r", photo_url)
        return None

    selected_queue = queue or image_processing_queue
    model = os.getenv("OPENAI_VISION_MODEL", DEFAULT_VISION_MODEL)

    async def _analyze_with_openai() -> str:
        def _request():
            return client.responses.create(
                model=model,
                input=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "input_text",
                                "text": "Describe esta imagen en una frase breve de máximo 15 palabras.",
                            },
                            {
                                "type": "input_image",
                                "image_url": photo_url,
                                "detail": "low",
                            },
                        ],
                    }
                ],
                max_output_tokens=100,
                store=False,
            )

        response = await asyncio.to_thread(_request)
        description = _response_output_text(response)
        if not description:
            raise RuntimeError("Responses no devolvió una descripción visible")
        return description

    try:
        return await selected_queue.add_task(_analyze_with_openai)
    except Exception as error:
        logger.exception(
            "Image analysis failed model=%s url=%s error_type=%s error=%r",
            model,
            photo_url,
            type(error).__name__,
            error,
        )
        return None


def _normalize_image_context_decision(value: str | None) -> str:
    normalized = str(value or "").strip().casefold()
    aliases = {
        "report": "report",
        "reporte": "report",
        "consultation": "consultation",
        "consulta": "consultation",
        "unclear": "unclear",
        "incierto": "unclear",
    }
    return aliases.get(normalized, "unclear")


async def classify_image_conversation_intent(
    client,
    conversation,
    *,
    queue=None,
) -> str:
    """Resolve an inbound image's purpose from recent conversational context.

    The image itself is intentionally not used to infer report intent. A photo
    of a street can be either a question or evidence for a report; only the
    citizen's conversation can distinguish those cases.
    """
    turns: list[str] = []
    for item in list(conversation or [])[-12:]:
        if isinstance(item, dict):
            role = str(item.get("role") or "user").strip().casefold()
            content = str(item.get("content") or "").strip()
        else:
            role = str(getattr(item, "role", "user") or "user").strip().casefold()
            content = str(getattr(item, "content", "") or "").strip()
        if not content:
            continue
        visible_role = "CIUDADANO" if role in {"user", "inbound"} else "SAM"
        turns.append(f"{visible_role}: {' '.join(content.split())[:600]}")

    if not turns:
        return "unclear"

    prompt = (
        "Clasifica para qué envió el ciudadano la imagen usando exclusivamente "
        "la conversación reciente. Responde con una sola palabra: REPORT si la "
        "imagen complementa un reporte municipal en curso; CONSULTATION si sólo "
        "quiere consultar algo sobre la imagen; UNCLEAR si no hay evidencia "
        "suficiente. Si SAM acaba de pedir una imagen para complementar el reporte "
        "actual y el ciudadano la envía, responde REPORT. No deduzcas la intención "
        "por el contenido visual.\n\nConversación:\n"
        + "\n".join(turns)
        + "\n\nSalida permitida: REPORT, CONSULTATION o UNCLEAR."
    )
    selected_queue = queue or image_processing_queue
    model = os.getenv(
        "OPENAI_IMAGE_CONTEXT_MODEL",
        os.getenv("OPENAI_VISION_MODEL", DEFAULT_VISION_MODEL),
    )

    async def _classify_with_openai() -> str:
        def _request():
            return client.responses.create(
                model=model,
                input=[
                    {
                        "role": "user",
                        "content": [{"type": "input_text", "text": prompt}],
                    }
                ],
                max_output_tokens=20,
                store=False,
            )

        response = await asyncio.to_thread(_request)
        return _normalize_image_context_decision(_response_output_text(response))

    try:
        decision = await selected_queue.add_task(_classify_with_openai)
        return decision if decision in IMAGE_CONTEXT_DECISIONS else "unclear"
    except Exception as error:
        logger.exception(
            "Image conversation intent classification failed model=%s "
            "error_type=%s error=%r",
            model,
            type(error).__name__,
            error,
        )
        return "unclear"


def route_inbound_image(
    *,
    report_intent_confirmed: bool,
    awaiting_report_image: bool,
    semantic_decision: str | None,
) -> str:
    """Choose whether media belongs to a report without discarding ambiguity."""
    if report_intent_confirmed or awaiting_report_image:
        return "report"
    decision = _normalize_image_context_decision(semantic_decision)
    if decision in {"report", "consultation"}:
        return decision
    return "pending"


def stage_pending_report_image(
    session: dict,
    photo_url: str,
    description: str | None,
) -> None:
    """Store media before intent resolution so the citizen never resends it."""
    if not photo_url:
        return
    pending_images = session.setdefault("pending_images", [])
    pending_descriptions = session.setdefault("pending_image_descriptions", [])
    clean_description = str(description or "").strip() or None
    if photo_url in pending_images:
        index = pending_images.index(photo_url)
        while len(pending_descriptions) <= index:
            pending_descriptions.append(None)
        if clean_description:
            pending_descriptions[index] = clean_description
        return
    pending_images.append(photo_url)
    pending_descriptions.append(clean_description)


def promote_pending_report_images(session: dict) -> int:
    """Move retained media into the active report exactly once."""
    pending_images = list(session.get("pending_images") or [])
    pending_descriptions = list(session.get("pending_image_descriptions") or [])
    images = session.setdefault("images", [])
    descriptions = session.setdefault("image_descriptions", [])
    promoted = 0

    for index, photo_url in enumerate(pending_images):
        description = pending_descriptions[index] if index < len(pending_descriptions) else None
        if photo_url in images:
            existing_index = images.index(photo_url)
            while len(descriptions) <= existing_index:
                descriptions.append(None)
            if description and not descriptions[existing_index]:
                descriptions[existing_index] = description
            continue
        images.append(photo_url)
        descriptions.append(description)
        promoted += 1

    session["pending_images"] = []
    session["pending_image_descriptions"] = []
    session["awaiting_report_image"] = False
    return promoted


def should_preserve_unconfirmed_image_context(session: dict | None) -> bool:
    """Keep harmless pending media state across workers without opening a report."""
    session = session or {}
    return bool(
        session.get("awaiting_report_image")
        or session.get("pending_images")
    )


def build_image_acknowledgement(
    sender_name: str,
    description: str | None,
    image_count: int,
) -> str:
    """Build a citizen-safe acknowledgement without exposing internal errors."""
    if image_count > 1:
        return (
            f"He recibido otra imagen (tienes {image_count} en total). "
            "Puedes seguir enviando imágenes o responde FIN cuando estés listo."
        )

    clean_name = str(sender_name or "").strip() or "Gracias"
    clean_description = str(description or "").strip().rstrip(" .")
    if clean_description:
        receipt = f"{clean_name} recibí tu imagen; veo {clean_description}. La he guardado para el reporte."
    else:
        receipt = f"{clean_name} recibí tu imagen y la he guardado para el reporte."

    return (
        f"{receipt} Si deseas continuar con tu reporte, responde FIN. "
        "En caso de que tengas otra foto, por favor envíala."
    )


def build_conversational_image_acknowledgement(
    sender_name: str,
    description: str | None,
) -> str:
    """Acknowledge media without inventing a municipal report workflow."""
    clean_name = str(sender_name or "").strip()
    clean_description = str(description or "").strip().rstrip(" .")
    prefix = f"{clean_name}, recibí tu imagen" if clean_name else "Recibí tu imagen"
    if clean_description:
        prefix = f"{prefix}; veo {clean_description}."
    else:
        prefix = f"{prefix}."
    return (
        f"{prefix} Conservaré esta imagen mientras aclaramos su propósito. "
        "¿Deseas hacer una consulta sobre ella o usarla para levantar un reporte "
        "municipal? No necesitas volver a enviarla."
    )
