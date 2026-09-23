import re
import unicodedata
from dataclasses import dataclass

from app.api.colonies_array import SAN_PEDRO_COLONIES
from app.api.streets_array import SAN_PEDRO_STREETS_REAL


def _normalize(value: str | None) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(character for character in text if not unicodedata.combining(character))
    return " ".join(re.sub(r"[^a-zA-Z0-9 ]+", " ", text).casefold().split())


def _catalog_index(values) -> dict[str, str]:
    return {_normalize(value): value for value in values if _normalize(value)}


STREET_INDEX = _catalog_index(SAN_PEDRO_STREETS_REAL)
COLONY_INDEX = _catalog_index(SAN_PEDRO_COLONIES)


AFFIRMATIVE_CONFIRMATIONS = {
    "si", "sip", "simon", "correcto", "correcta", "asi es", "exacto",
    "confirmo", "de acuerdo", "afirmativo",
}
NEGATIVE_CONFIRMATIONS = {
    "no", "nel", "nelson", "incorrecto", "incorrecta", "no es correcto",
    "esta mal", "no gracias",
}


@dataclass(frozen=True)
class IntakeDecision:
    action: str
    response: str | None = None


def extract_catalog_location(
    message: str | None,
    existing: dict[str, str] | None = None,
) -> dict[str, str]:
    """Resolve only exact official locations; ambiguous names require context."""
    existing = existing or {}
    raw = " ".join(str(message or "").split()).strip()
    if not raw:
        return {}

    explicit_street = bool(re.match(r"^(?:calle|avenida|av\.?|boulevard)\s+", raw, re.I))
    explicit_colony = bool(re.match(r"^(?:en\s+)?(?:colonia|col\.?|fraccionamiento)\s+", raw, re.I))
    prefixed_en = bool(re.match(r"^en\s+", raw, re.I))
    candidate = re.sub(
        r"^(?:en\s+)?(?:(?:calle|avenida|av\.?|boulevard|colonia|col\.?|fraccionamiento)\s+)?",
        "",
        raw,
        flags=re.I,
    ).strip()
    normalized = _normalize(candidate)
    street = STREET_INDEX.get(normalized)
    colony = COLONY_INDEX.get(normalized)

    if explicit_colony and colony:
        return {"selection7": colony}
    if explicit_street and street:
        return {"selection5": street}
    if street and not colony:
        return {"selection5": street}
    if colony and not street:
        return {"selection7": colony}
    if street and colony:
        if prefixed_en and existing.get("selection5") and not existing.get("selection7"):
            return {"selection7": colony}
        # An official name that is both street and colony is not guessed.
        return {}
    return {}


def build_intake_confirmation(fields: dict[str, str]) -> str | None:
    required = ("selection1", "selection4", "selection5", "selection7")
    if not all(str(fields.get(key) or "").strip() for key in required):
        return None
    return (
        "Entiendo que deseas levantar un reporte porque "
        f"{str(fields['selection4']).strip()}, en la calle "
        f"{str(fields['selection5']).strip()}, colonia "
        f"{str(fields['selection7']).strip()}. ¿Es correcto?"
    )


def should_request_intake_confirmation(
    fields: dict[str, str],
    session: dict | None,
) -> bool:
    """Activate only for fragmented intake, never for the ordinary wizard."""
    session = session or {}
    return bool(
        build_intake_confirmation(fields)
        and int(session.get("unsolicited_location_fragments", 0)) >= 2
        and not session.get("intake_confirmed")
        and not session.get("pending_intake_confirmation")
        and not session.get("image_prompted")
        and not session.get("pending_finalization_field")
    )


def classify_intake_confirmation(message: str | None) -> str:
    normalized = _normalize(message)
    if normalized in AFFIRMATIVE_CONFIRMATIONS:
        return "CONFIRMED"
    if normalized in NEGATIVE_CONFIRMATIONS:
        return "REJECTED"
    return "UNKNOWN"


def next_question_after_intake_confirmation(fields: dict[str, str]) -> str:
    if not str(fields.get("selection6") or "").strip():
        return "Gracias por confirmar. ¿Cuál es el número del domicilio o poste más cercano?"
    return "Gracias por confirmar. ¿Deseas agregar una imagen para complementar tu reporte?"
