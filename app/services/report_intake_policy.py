import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher

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


def _unique_catalog_typo_match(
    normalized: str,
    catalog: dict[str, str],
    *,
    minimum_words: int,
) -> str | None:
    """Return a canonical value only when a typo has one clear catalog match."""
    if len(normalized.split()) < minimum_words:
        return None
    ranked = sorted(
        (
            SequenceMatcher(None, normalized, catalog_name).ratio(),
            canonical,
        )
        for catalog_name, canonical in catalog.items()
    )
    best_score, best_value = ranked[-1]
    second_score = ranked[-2][0] if len(ranked) > 1 else 0.0
    if best_score >= 0.80 and best_score - second_score >= 0.05:
        return best_value
    return None


def _unique_street_typo_match(normalized: str) -> str | None:
    """Return a canonical street only when a multi-word typo has one clear match."""
    return _unique_catalog_typo_match(
        normalized,
        STREET_INDEX,
        minimum_words=3,
    )


def _unique_colony_typo_match(normalized: str) -> str | None:
    """Resolve a clearly intended colony without comparing it with streets."""
    return _unique_catalog_typo_match(
        normalized,
        COLONY_INDEX,
        minimum_words=2,
    )


def extract_initial_report_bundle(
    message: str | None,
    existing: dict[str, str] | None = None,
) -> tuple[dict[str, str], dict[str, str]]:
    """Extract an explicitly labelled location from an initial report message.

    Citizens commonly provide the problem and the complete address in one
    message, before SAM has asked for any individual field.  This parser is
    intentionally conservative: it only activates when the citizen introduces
    the location explicitly (for example, ``Ubicado en`` or ``Dirección:``),
    and it only accepts a neighborhood when it resolves uniquely against the
    San Pedro catalog.

    The first dictionary contains the values suitable for the report workflow.
    The second preserves the citizen-authored fragments for auditability.
    Existing report values are never overwritten.
    """
    existing = existing or {}
    raw = " ".join(str(message or "").split()).strip()
    if not raw:
        return {}, {}

    location_intro = re.search(
        r"\b(?:"
        r"ubicad[oa]s?\s+(?:en|sobre\s+la\s+calle)|"
        r"ubicaci[oó]n(?:\s+del\s+reporte)?\s*(?::|-)\s*|"
        r"direcci[oó]n\s*(?::|-)\s*|"
        r"se\s+encuentra(?:n)?\s+en"
        r")\s*",
        raw,
        flags=re.IGNORECASE,
    )
    if not location_intro:
        return {}, {}

    original_description = raw[: location_intro.start()].strip(" ,.;:-")
    raw_location = raw[location_intro.end() :].strip(" ,.;:-")
    if not raw_location:
        return {}, {}

    description = re.sub(
        r"^(?:(?:[¡!¿?]\s*)?(?:hola|buen\s+d[ií]a|buenas\s+tardes|"
        r"buenas\s+noches)\b[\s,;:!¡¿?\-]*)+",
        "",
        original_description,
        flags=re.IGNORECASE,
    ).strip(" ,.;:-")
    description = re.sub(
        r"^(?:yo\s+)?(?:quiero|quisiera|necesito|deseo)\s+reportar"
        r"(?:\s+que)?\s*",
        "",
        description,
        flags=re.IGNORECASE,
    ).strip(" ,.;:-")
    description = re.sub(
        r"^(?:yo\s+)?(?:quiero|quisiera|necesito|deseo)\s+"
        r"(?:(?:levantar|hacer|realizar|generar)\s+)?(?:un\s+)?reporte"
        r"(?:\s+(?:de|sobre|por))?\s*",
        "",
        description,
        flags=re.IGNORECASE,
    ).strip(" ,.;:-")

    colony_match = re.search(
        r"(?:^|,\s*|\s+)(?:colonia|col\.?|fraccionamiento|fracc\.?)\s+"
        r"(.+?)\.?$",
        raw_location,
        flags=re.IGNORECASE,
    )
    raw_colony = colony_match.group(1).strip(" ,.;:-") if colony_match else ""
    canonical_colony = ""
    if raw_colony:
        normalized_colony = _normalize(raw_colony)
        canonical_colony = (
            COLONY_INDEX.get(normalized_colony)
            or _unique_colony_typo_match(normalized_colony)
            or ""
        )

    address = (
        raw_location[: colony_match.start()].strip(" ,.;:-")
        if colony_match
        else raw_location
    )
    raw_number = ""
    normalized_number = ""
    number_span = None
    no_number_match = re.search(
        r"(?<!\w)#?\s*(?:sin\s+n[uú]mero|sin\s+numeraci[oó]n|s\s*/\s*n|"
        r"no\s+tiene\s+(?:n[uú]mero|numeraci[oó]n))(?!\w)",
        address,
        flags=re.IGNORECASE,
    )
    if no_number_match:
        raw_number = no_number_match.group(0).strip()
        normalized_number = "0000"
        number_span = no_number_match.span()
    else:
        labelled_number = re.search(
            r"(?<!\w)(?:#\s*|n[uú]m(?:ero)?\.?\s*(?::|#)?\s*|"
            r"n[oº]\.?\s*)(\d{1,8})(?!\w)",
            address,
            flags=re.IGNORECASE,
        )
        if labelled_number:
            raw_number = labelled_number.group(0).strip()
            normalized_number = labelled_number.group(1)
            number_span = labelled_number.span()
        else:
            natural_number = re.search(
                r"\s(\d{1,8})(?=\s*(?:,|cruce\b|entre\b|esquina\b|"
                r"frente\b|$))",
                address,
                flags=re.IGNORECASE,
            )
            if natural_number:
                raw_number = natural_number.group(1)
                normalized_number = natural_number.group(1)
                number_span = natural_number.span(1)

    street_reference = address
    if number_span:
        start, end = number_span
        street_reference = f"{address[:start]} {address[end:]}"
    street_reference = " ".join(street_reference.split()).strip(" ,.;:-#")
    canonical_street = STREET_INDEX.get(_normalize(street_reference))
    report_street = canonical_street or street_reference

    normalized_fields: dict[str, str] = {}
    if description and not str(existing.get("selection4") or "").strip():
        normalized_fields["selection4"] = description
    if report_street and not str(existing.get("selection5") or "").strip():
        normalized_fields["selection5"] = report_street
    if normalized_number and not str(existing.get("selection6") or "").strip():
        normalized_fields["selection6"] = normalized_number
    if canonical_colony and not str(existing.get("selection7") or "").strip():
        normalized_fields["selection7"] = canonical_colony

    original_fields = {
        "message": raw,
        "selection4": original_description,
        "selection5": street_reference,
        "selection6": raw_number,
        "selection7": raw_colony,
    }
    return normalized_fields, original_fields


def extract_catalog_location(
    message: str | None,
    existing: dict[str, str] | None = None,
    expected_field: str | None = None,
) -> dict[str, str]:
    """Resolve an official location without changing the citizen's field intent.

    An explicit prefix (``calle``/``colonia``) or the field requested by SAM
    decides which catalog is consulted. Catalog similarity may normalize a typo,
    but it must never turn a colony into a street or vice versa.
    """
    existing = existing or {}
    raw = " ".join(str(message or "").split()).strip()
    if not raw:
        return {}

    explicit_street = bool(re.match(r"^(?:calle|avenida|av\.?|boulevard)\s+", raw, re.I))
    explicit_colony = bool(re.match(r"^(?:en\s+)?(?:colonia|col\.?|fraccionamiento)\s+", raw, re.I))
    prefixed_en = bool(re.match(r"^en\s+", raw, re.I))

    # A citizen may answer the street question with the entire reference and
    # append the neighborhood, e.g. "Francisco Siller ... Col. General Lázaro
    # Garza Ayala". Split the explicit neighborhood before the street resolver
    # sees the whole sentence and stores it as one field.
    inline_colony = None if explicit_colony else re.search(
        r"(?:^|\s)(?:colonia|col\.?|fraccionamiento)\s+(.+?)\.?$",
        raw,
        flags=re.I,
    )
    if inline_colony:
        colony_candidate = inline_colony.group(1).strip()
        colony_normalized = _normalize(colony_candidate)
        colony = (
            COLONY_INDEX.get(colony_normalized)
            or _unique_colony_typo_match(colony_normalized)
        )
        if colony:
            result = {"selection7": colony}
            street_reference = raw[: inline_colony.start()].strip(" ,.-")
            if street_reference and (
                expected_field == "selection5" or not existing.get("selection5")
            ):
                # Keep the citizen's own street/reference wording; the catalog
                # match is used to establish municipal scope, not to discard
                # useful landmarks.
                result = {
                    "selection5": street_reference,
                    "selection7": colony,
                }
            return result

    candidate = re.sub(
        r"^(?:en\s+)?(?:(?:calle|avenida|av\.?|boulevard|colonia|col\.?|fraccionamiento)\s+)?",
        "",
        raw,
        flags=re.I,
    ).strip()
    normalized = _normalize(candidate)

    # The citizen's explicit wording has priority over conversational context.
    # When a field is explicit/requested, never fall through to the other
    # catalog: e.g. "Col. General Lázaro Garza Ayala" must not become a street.
    if explicit_colony or (expected_field == "selection7" and not explicit_street):
        colony = COLONY_INDEX.get(normalized) or _unique_colony_typo_match(normalized)
        return {"selection7": colony} if colony else {}
    if explicit_street or (expected_field == "selection5" and not explicit_colony):
        street = STREET_INDEX.get(normalized) or _unique_street_typo_match(normalized)
        return {"selection5": street} if street else {}

    street = STREET_INDEX.get(normalized) or _unique_street_typo_match(normalized)
    colony = COLONY_INDEX.get(normalized)

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
