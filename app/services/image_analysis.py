import asyncio
import os
from typing import Any

from app.util.logger import logger
from app.util.rate_limiter import image_processing_queue


DEFAULT_VISION_MODEL = "gpt-4o"


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
    clean_description = str(description or "").strip()
    if clean_description:
        receipt = f"{clean_name} recibí tu imagen; veo {clean_description}. La he guardado para el reporte."
    else:
        receipt = f"{clean_name} recibí tu imagen y la he guardado para el reporte."

    return (
        f"{receipt} Si deseas continuar con tu reporte, responde FIN. "
        "En caso de que tengas otra foto, por favor envíala."
    )
