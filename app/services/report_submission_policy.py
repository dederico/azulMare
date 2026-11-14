import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from functools import lru_cache

from app.api.colonies_array import SAN_PEDRO_COLONIES
from app.api.streets_array import SAN_PEDRO_STREETS_REAL


INVALID_REQUIRED_VALUES = {
    "",
    "n/a",
    "na",
    "ninguno",
    "sin descripcion",
    "sin especificar",
    "no especificada",
    "no especificado",
    "ubicacion no especificada",
}

REPORT_CONTROL_MESSAGES = {
    "fin",
    "finalizar",
    "terminar",
    "si",
    "no",
    "ok",
    "gracias",
    "no tengo imagen",
    "no tengo imagenes",
    "sin imagen",
    "sin imagenes",
    "no tengo foto",
    "no tengo fotos",
    "sin foto",
    "sin fotos",
}

REPORT_INTENT_PHRASES = (
    "quiero reportar",
    "quisiera reportar",
    "vengo a reportar",
    "para reportar",
    "quiero hacer un reporte",
    "quiero levantar un reporte",
    "hacer un reporte",
    "levantar un reporte",
    "necesito reportar",
    "deseo reportar",
    "quiero levantar reporte",
    "necesito levantar un reporte",
    "reporte normal",
    "necesito una patrulla",
    "requiero una patrulla",
    "manden una patrulla",
    "envien una patrulla",
)


@dataclass(frozen=True)
class ReportCatalogEntry:
    """One official CIAC subject declared in the active runtime prompt."""

    value: str
    label: str


_REPORT_CATALOG_ENTRY_PATTERN = re.compile(
    r"^\s*(?:[*-]\s*)?Valor:\s*(\d+)\s*"
    r"(?:,\s*Tipo:\s*|\s+-\s*)(.+?)\s*$",
    flags=re.MULTILINE | re.IGNORECASE,
)


@lru_cache(maxsize=8)
def parse_report_catalog(prompt: str | None) -> tuple[ReportCatalogEntry, ...]:
    """Parse CIAC IDs from the active prompt without owning classification.

    The model still interprets the citizen's meaning. This parser supplies the
    deterministic source of truth used by the existing catalog reconciliation
    helpers, and supports both catalog formats currently present in the prompt.
    """
    entries: dict[str, ReportCatalogEntry] = {}
    for match in _REPORT_CATALOG_ENTRY_PATTERN.finditer(str(prompt or "")):
        value = match.group(1)
        label = " ".join(match.group(2).split()).strip(" .")
        if label:
            entries[value] = ReportCatalogEntry(value=value, label=label)
    return tuple(entries.values())


def report_catalog_contains(prompt: str | None, category: str | None) -> bool:
    """Return whether a numeric subject is declared by the active prompt."""
    value = " ".join(str(category or "").split()).strip()
    return bool(value and any(entry.value == value for entry in parse_report_catalog(prompt)))


def is_report_intent_only(value: str | None) -> bool:
    """Detect greetings plus a request to report, with no actual problem."""
    normalized = normalize_report_text(value)
    normalized = re.sub(r"[^a-z0-9\s]", " ", normalized)
    normalized = " ".join(normalized.split())
    normalized = re.sub(
        r"^(?:(?:hola|buen dia|buenas tardes|buenas noches|que tal)\s+)+",
        "",
        normalized,
    ).strip()
    normalized = re.sub(r"^(?:solo\s+)?", "", normalized).strip()
    normalized = re.sub(r"\s+(?:por favor|gracias)$", "", normalized).strip()
    canonical_intents = {
        " ".join(re.sub(r"[^a-z0-9\s]", " ", phrase).split())
        for phrase in REPORT_INTENT_PHRASES
    }
    return normalized in canonical_intents

PROBLEM_SIGNAL_WORDS = (
    "hay ",
    "no funciona",
    "no sirve",
    "no prende",
    "esta roto",
    "esta rota",
    "esta danado",
    "esta danada",
    "se cayo",
    "caido",
    "caida",
    "abandonado",
    "abandonada",
    "obstruye",
    "obstruida",
    "obstruido",
    "bloquea",
    "falta ",
    "riesgo",
    "problema",
    "retirar",
    "recoger",
    "reparar",
    "agresion",
    "violencia",
    "esta gritando",
    "crisis psiquiatrica",
)

# Declarative service requests are report evidence even when citizens omit the
# word "reporte". Keep the action list deliberately narrow so informational
# mentions of a municipal service do not activate report mode.
DECLARATIVE_REPORT_REQUEST_PATTERN = re.compile(
    r"^(?:(?:hola|buen\s+d[ií]a|buenas\s+tardes|buenas\s+noches)"
    r"[\s,;:!¡¿?\-]*)?"
    r"(?:se\s+solicita|solicito|solicitamos)\s+"
    r"(?:que\s+)?(?:pintar|retirar|recoger|reparar|atender|limpiar|podar)\b",
    flags=re.IGNORECASE,
)

# Sólo se incluyen términos cuyo asunto es inequívoco. Si un texto contiene
# términos de asuntos distintos, la política no intenta adivinar la categoría.
HIGH_CONFIDENCE_REPORT_CATEGORIES = {
    "luminaria": "982",
    "luminarias": "982",
    "lampara": "982",
    "lamparas": "982",
    "foco": "982",
    "focos": "982",
    "arbotante": "983",
    "arbotantes": "983",
    "poste de luz": "982",
    "postes de luz": "982",
    "alumbrado": "982",
    "bache": "984",
    "baches": "984",
    "hueco": "984",
    "huecos": "984",
    "pavimento": "980",
    "asfalto": "980",
    "recarpeteo": "980",
    "basura": "974",
    "residuos": "974",
    "desperdicios": "974",
    "escombro": "986",
    "escombros": "986",
    "fuga de agua": "726",
    "drenaje": "727",
    "alcantarilla": "727",
    "alcantarillas": "727",
    "coladera": "224",
    "coladeras": "224",
    "semaforo": "523",
    "semaforos": "523",
    "arbol": "979",
    "arboles": "979",
    "poda": "979",
    "rama": "81",
    "ramas": "81",
    "animal muerto": "16",
    "animales muertos": "16",
    "cable caido": "19",
    "cables caidos": "19",
    "cables expuestos": "1064",
    "ruido": "1000",
}

# Bandeja general del catálogo CIAC para solicitudes que no pueden asignarse
# con certeza a un asunto especializado. CIAC conserva la explicación original
# y puede reasignar internamente el reporte.
UNCLASSIFIED_REPORT_CATEGORY_ID = "486"

REPORT_LIFECYCLE_ACTIONS = frozenset(
    {"continue", "confirm_exit", "exit"}
)


@dataclass(frozen=True)
class ReportProgressDecision:
    action: str
    field: str | None = None
    response: str | None = None


def validate_structured_report_lifecycle_action(
    value: str | None,
) -> str | None:
    """Validate the model's closed report-lifecycle decision.

    Natural-language interpretation belongs to the model.  This boundary does
    not inspect the citizen's words and deliberately contains no phrase or
    keyword classifier; it only validates the structured action returned by
    the model before state can be mutated.
    """
    normalized = str(value or "").strip().casefold()
    return normalized if normalized in REPORT_LIFECYCLE_ACTIONS else None


def deduplicate_report_media(
    images: list[str] | None,
    descriptions: list[str] | None,
) -> tuple[list[str], list[str]]:
    """Deduplicate media without breaking image/description alignment."""
    unique_images: list[str] = []
    unique_descriptions: list[str] = []
    seen: set[str] = set()
    description_values = list(descriptions or [])
    for index, raw_image in enumerate(images or []):
        image = str(raw_image or "").strip()
        if not image or image in seen:
            continue
        seen.add(image)
        unique_images.append(image)
        unique_descriptions.append(
            str(description_values[index] or "Imagen adicional").strip()
            if index < len(description_values)
            else "Imagen adicional"
        )
    return unique_images, unique_descriptions


def canonical_report_image_urls(
    images_list: list[str] | None,
    selection8: str | list[str] | None,
) -> list[str]:
    """Return one canonical image source without duplicating legacy fields.

    ``images_list`` is the current structured contract. ``selection8`` exists
    only for older callers and is consulted exclusively when the structured
    list is empty. This prevents a comma-joined compatibility value from being
    submitted to CIAC as an additional, malformed photo URL.
    """
    candidates: list[str] = []
    if images_list:
        candidates.extend(str(value or "").strip() for value in images_list)
    elif isinstance(selection8, list):
        candidates.extend(str(value or "").strip() for value in selection8)
    elif isinstance(selection8, str):
        candidates.extend(
            part.strip()
            for part in re.split(r"[\s,]+", selection8)
            if part.strip()
        )

    canonical: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        if not candidate or not (
            candidate.startswith(("http://", "https://"))
            or "storage.chat2desk.com" in candidate
        ):
            continue
        if candidate in seen:
            continue
        seen.add(candidate)
        canonical.append(candidate)
    return canonical


def normalize_report_text(value: str | None) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return " ".join(text.casefold().split())


_EXPLICIT_NO_IMAGE_SUFFIXES = (
    "sin imagen",
    "sin imagenes",
    "sin foto",
    "sin fotos",
    "no tengo imagen",
    "no tengo imagenes",
    "no tengo foto",
    "no tengo fotos",
)


def extract_explicit_report_image_decision(value: str | None) -> str | None:
    """Capture an explicit trailing no-image choice in an all-in-one report."""
    normalized = _normalized_location_search_text(value)
    if any(
        normalized == phrase or normalized.endswith(f" {phrase}")
        for phrase in _EXPLICIT_NO_IMAGE_SUFFIXES
    ):
        return "no"
    return None


def strip_explicit_no_image_suffix(value: str | None) -> str:
    """Remove only the terminal operational choice from report evidence."""
    compact = " ".join(str(value or "").split()).strip()
    suffix_pattern = "|".join(
        re.escape(phrase).replace(r"\ ", r"\s+")
        for phrase in _EXPLICIT_NO_IMAGE_SUFFIXES
    )
    return re.sub(
        rf"(?:[,;.-]\s*|\s+)(?:{suffix_pattern})[.!?]*\s*$",
        "",
        compact,
        flags=re.IGNORECASE,
    ).strip()


def _location_catalog(values) -> dict[str, str]:
    return {
        normalize_report_text(value): value
        for value in values
        if normalize_report_text(value)
    }


STREET_CATALOG = _location_catalog(SAN_PEDRO_STREETS_REAL)
COLONY_CATALOG = _location_catalog(SAN_PEDRO_COLONIES)


# Chat2Desk citizens frequently use the public/neighborhood name while CIAC's
# catalog contains a more formal spelling.  Keep this list explicit: accepting
# arbitrary fuzzy colony text here would silently submit the wrong location.
_COLONY_ALIAS_TARGETS = {
    "casco de san pedro": "Casco",
    "casco urbano de san pedro": "Casco Urbano",
    "centro de san pedro": "San Pedro Garza Garcia Centro",
    "centro de san pedro garza garcia": "San Pedro Garza Garcia Centro",
    "industrial": "Zona Industrial",
    "residencial chipinque": "Zona Residencia Chipinque",
    "zona residencial chipinque": "Zona Residencia Chipinque",
}
COLONY_ALIASES = {
    normalize_report_text(alias): COLONY_CATALOG[normalize_report_text(target)]
    for alias, target in _COLONY_ALIAS_TARGETS.items()
    if normalize_report_text(target) in COLONY_CATALOG
}


def _unique_approximate_colony_match(candidate: str) -> str | None:
    """Resolve a close colony spelling only when one canonical target wins.

    Exact official names and explicit public aliases remain preferred.  This
    fallback tolerates ordinary misspellings, but groups aliases by their
    canonical CIAC value so duplicate spellings cannot manufacture confidence.
    Short one-word guesses stay strict because the colony catalog contains many
    similar names.
    """
    if len(candidate) < 5:
        return None

    scores_by_canonical: dict[str, float] = {}
    for catalog_name, canonical in {**COLONY_CATALOG, **COLONY_ALIASES}.items():
        score = SequenceMatcher(None, candidate, catalog_name).ratio()
        scores_by_canonical[canonical] = max(
            score,
            scores_by_canonical.get(canonical, 0.0),
        )

    ranked = sorted(
        ((score, canonical) for canonical, score in scores_by_canonical.items()),
        reverse=True,
    )
    if not ranked:
        return None
    best_score, best_value = ranked[0]
    second_score = ranked[1][0] if len(ranked) > 1 else 0.0
    minimum_score = 0.90 if len(candidate.split()) == 1 else 0.80
    minimum_margin = 0.08 if len(candidate.split()) == 1 else 0.05
    if best_score >= minimum_score and best_score - second_score >= minimum_margin:
        return best_value
    return None


_LOCATION_REJECTION_MARKERS = (
    "cuantas veces",
    "cuantas mas veces",
    "otra vez",
    "por enesima vez",
    "estas en un loop",
    "sigues repitiendo",
    "ya te la puse",
    "ya te lo puse",
    "ya te dije",
    "me haces perder el tiempo",
    "me hiciste perder el tiempo",
)


def _normalized_location_search_text(value: str | None) -> str:
    """Normalize punctuation too, so catalog phrases can be found in prose."""
    return " ".join(
        re.sub(r"[^a-z0-9 ]+", " ", normalize_report_text(value)).split()
    )


def _strip_colony_answer_wrappers(value: str | None) -> str:
    """Remove labels and conversational wrappers, never colony content."""
    candidate = _normalized_location_search_text(value)
    candidate = re.sub(
        r"^(?:colonia|fraccionamiento|fracc|col)\s+",
        "",
        candidate,
    )
    candidate = re.sub(r"^(?:en\s+)+(?:el|la)?\s*", "", candidate)
    return candidate.strip()


def canonical_report_colony_value(value: str | None) -> str | None:
    """Resolve one complete citizen colony answer to the CIAC catalog."""
    candidate = _strip_colony_answer_wrappers(value)
    if not candidate:
        return None
    return (
        COLONY_CATALOG.get(candidate)
        or COLONY_ALIASES.get(candidate)
        or _unique_approximate_colony_match(candidate)
    )


def _unique_location_catalog_mention(
    value: str | None,
    catalog: dict[str, str],
) -> str | None:
    """Return the longest single catalog location mentioned in free prose."""
    normalized = _normalized_location_search_text(value)
    if not normalized:
        return None
    matches = [
        (name, canonical)
        for name, canonical in catalog.items()
        if re.search(rf"(?<!\w){re.escape(name)}(?!\w)", normalized)
        # In a postal address this phrase identifies the municipality, not a
        # street or neighborhood named "San Pedro".
        and not (
            name == "san pedro"
            and "san pedro garza garcia" in normalized
        )
    ]
    if not matches:
        return None
    matches.sort(key=lambda item: len(item[0]), reverse=True)
    best_name, best_value = matches[0]
    if any(
        other_name not in best_name and best_name not in other_name
        for other_name, _ in matches[1:]
    ):
        return None
    return best_value


def find_canonical_report_colony_mention(value: str | None) -> str | None:
    """Find one official colony or explicit alias inside a longer address."""
    alias_or_catalog = {**COLONY_CATALOG, **COLONY_ALIASES}
    return _unique_location_catalog_mention(value, alias_or_catalog)


def find_canonical_report_street_mention(value: str | None) -> str | None:
    """Find one unambiguous official street inside citizen-authored prose."""
    return _unique_location_catalog_mention(value, STREET_CATALOG)


def extract_report_number_after_street(
    value: str | None,
    street: str | None,
) -> str | None:
    """Read only the exterior number adjacent to a recognized street.

    This deliberately ignores later postal codes and other numbers in a full
    address.  It is safer than selecting an arbitrary number from the message.
    """
    if not street:
        return None
    tokens = [re.escape(token) for token in str(street).split()]
    if not tokens:
        return None
    street_pattern = r"\s+".join(tokens)
    match = re.search(
        rf"{street_pattern}\s*(?:#|n[uú]m(?:ero)?\.?|n[oº]\.?)?\s*(\d{{1,8}})(?!\w)",
        str(value or ""),
        flags=re.IGNORECASE,
    )
    return match.group(1) if match else None


def canonical_report_location_value(
    field: str | None,
    value: str | None,
) -> str | None:
    """Validate location fields without treating frustration as an address."""
    key = str(field or "").strip()
    compact = " ".join(str(value or "").split()).strip()
    normalized = normalize_report_text(compact)
    if key not in {"selection5", "selection7"} or not compact:
        return None
    if (
        normalized in REPORT_CONTROL_MESSAGES
        or any(marker in normalized for marker in _LOCATION_REJECTION_MARKERS)
        or compact.endswith("?")
        or "http://" in compact.casefold()
        or "https://" in compact.casefold()
        or not re.search(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]", compact)
    ):
        return None

    catalog = STREET_CATALOG if key == "selection5" else COLONY_CATALOG
    catalog_candidate = normalized
    if key == "selection5":
        catalog_candidate = re.sub(
            r"^(?:calle|avenida|ave\.?|av\.?)\s+",
            "",
            catalog_candidate,
        )
    else:
        canonical_colony = canonical_report_colony_value(compact)
        if canonical_colony:
            return canonical_colony
        catalog_candidate = _strip_colony_answer_wrappers(compact)
    canonical = catalog.get(catalog_candidate)
    if canonical:
        return canonical
    if key == "selection7":
        return None

    catalog_mention = find_canonical_report_street_mention(compact)
    if catalog_mention:
        return catalog_mention

    # Crossings and landmarks may not be a single street catalog entry. Keep
    # only concise street-like values, never conversational prose.
    if len(compact) > 120 or len(compact.split()) > 14:
        return None
    return compact


def classify_report_correction_field(value: str | None) -> str | None:
    """Resolve the field named after SAM explicitly offers a correction."""
    normalized = normalize_report_text(value)
    if re.search(r"\b(?:calle|direccion)\b", normalized):
        return "selection5"
    if re.search(r"\b(?:numero|numero exterior)\b", normalized):
        return "selection6"
    if re.search(r"\b(?:colonia|fraccionamiento)\b", normalized):
        return "selection7"
    if re.search(r"\b(?:problema|descripcion|asunto)\b", normalized):
        return "selection4"
    return None


def report_correction_question(field: str | None) -> str:
    return {
        "selection4": "¿Cuál es la descripción correcta del problema?",
        "selection5": "¿Cuál es la calle correcta?",
        "selection6": "¿Cuál es el número exterior correcto?",
        "selection7": "¿Cuál es la colonia correcta?",
    }.get(str(field or ""), "¿Qué dato deseas corregir?")


def captured_report_question_field(
    response: str | None,
    selections: dict[str, str] | None,
) -> str | None:
    """Identify an LLM question that asks for an already captured field."""
    normalized = normalize_report_text(response)
    if not normalized or "?" not in str(response or ""):
        return None
    field_markers = {
        "selection4": (
            "que problema", "que deseas reportar", "describe el problema",
        ),
        "selection5": (
            "cual es la calle", "en que calle", "calle exacta",
        ),
        "selection6": (
            "numero exterior", "cual es el numero",
        ),
        "selection7": (
            "cual es la colonia", "en que colonia", "nombre de la colonia",
        ),
    }
    stored = selections or {}
    for field, markers in field_markers.items():
        if str(stored.get(field) or "").strip() and any(
            marker in normalized for marker in markers
        ):
            return field
    return None


def extract_citizen_reply_text(value: str | None) -> str:
    """Remove Chat2Desk's quoted assistant block from a citizen reply.

    Chat2Desk serializes some WhatsApp replies as ``« assistant text » reply``.
    The quoted block is conversation context, not citizen-authored evidence.
    """
    raw = str(value or "").strip()
    if not raw:
        return ""
    quoted_reply = re.fullmatch(
        r"\s*«.*?»\s*(.+?)\s*",
        raw,
        flags=re.DOTALL,
    )
    return quoted_reply.group(1).strip() if quoted_reply else raw


def sanitize_report_description(value: str | None) -> str:
    """Remove known SAM operational prose from a CIAC explanation.

    An older location branch rewrote the inbound ``body`` with an assistant
    acknowledgement before persisting it.  Those records therefore look like
    citizen messages in historical conversations.  Keep the citizen's actual
    problem wording while removing only the exact operational templates that
    SAM generated.
    """
    text = " ".join(extract_citizen_reply_text(value).split()).strip()
    if not text:
        return ""

    operational_patterns = (
        # Remove the complete legacy acknowledgement, including the location
        # copied between its two fixed clauses.
        r"\bubicaci[oó]n registrada:\s*.*?\.\s*para finalizar tu reporte "
        r"con las im[aá]genes que has enviado,?\s*av[ií]same cuando est[eé]s "
        r"listo\.?",
        r"\bpara finalizar tu reporte con las im[aá]genes que has enviado,?\s*"
        r"av[ií]same cuando est[eé]s listo\.?",
        r"\bubicaci[oó]n registrada:\s*[^.]+\.?",
        r"\bubicaci[oó]n del reporte:\s*[^.]+(?:\.|$)",
        r"\bno se han adjuntado im[aá]genes al reporte\.\s*"
        r"(?:por favor,?\s*)?env[ií]a al menos una imagen\.?",
    )
    for pattern in operational_patterns:
        text = re.sub(pattern, " ", text, flags=re.IGNORECASE)

    text = re.sub(r"\s+([,.;:])", r"\1", text)
    text = re.sub(r"(?:\.\s*){2,}", ". ", text)
    return " ".join(text.split()).strip(" .,:;-")


def build_ciac_report_summary(
    description: str | None,
    street: str | None,
    number: str | None,
    neighborhood: str | None,
    *,
    max_length: int = 400,
) -> str:
    """Build the concise municipal summary sent only in CIAC's report field.

    The model owns the semantic summary stored in ``selection4``. This
    presentation layer only removes legacy conversational boilerplate and adds
    stable municipal wording. Location is deliberately excluded because CIAC
    receives it separately in the ``localizacion`` payload field.
    """
    cleaned = sanitize_report_description(description)
    raw_clauses = re.split(r"(?:[.!?]+|\s+-\s+)", cleaned)
    clauses: list[str] = []
    normalized_clauses: list[str] = []

    greeting_pattern = re.compile(
        r"^(?:hola|buen\s+d[ií]a|buenas\s+tardes|buenas\s+noches)"
        r"(?:\s*[,;:-]\s*|\s+|$)",
        flags=re.IGNORECASE,
    )
    intent_patterns = (
        re.compile(
            r"^(?:yo\s+)?(?:quiero|necesito|deseo)\s+"
            r"(?:(?:levantar|hacer|realizar|generar)\s+)?"
            r"(?:un\s+)?reporte(?:\s+(?:de|sobre|por))?"
            r"(?:\s*[,;:-]\s*|\s+|$)",
            flags=re.IGNORECASE,
        ),
        re.compile(
            r"^(?:para\s+)?reportar(?:\s+que)?(?:\s*[,;:-]\s*|\s+|$)",
            flags=re.IGNORECASE,
        ),
        re.compile(
            r"^(?:quiero|necesito|deseo)\s+reportar"
            r"(?:\s+que)?(?:\s*[,;:-]\s*|\s+|$)",
            flags=re.IGNORECASE,
        ),
    )

    for raw_clause in raw_clauses:
        clause = " ".join(raw_clause.split()).strip(" ,:;-")
        if not clause:
            continue
        clause = greeting_pattern.sub("", clause).strip(" ,:;-")
        for pattern in intent_patterns:
            clause = pattern.sub("", clause).strip(" ,:;-")
        if not clause:
            continue

        normalized = normalize_report_text(clause)
        if normalized in REPORT_INTENT_PHRASES or normalized in normalized_clauses:
            continue
        # Prefer the more informative clause when one only repeats part of it.
        if any(normalized in existing for existing in normalized_clauses):
            continue
        contained_indexes = [
            index
            for index, existing in enumerate(normalized_clauses)
            if existing in normalized
        ]
        for index in reversed(contained_indexes):
            del clauses[index]
            del normalized_clauses[index]
        clauses.append(clause)
        normalized_clauses.append(normalized)

    # ``selection4`` can contain several citizen turns from legacy sessions.
    # CIAC needs a concise explanation, not that accumulated transcript. Keep
    # only the strongest concrete problem statement; the structured address is
    # appended independently below.
    def clause_score(item: tuple[int, str]) -> tuple[int, int]:
        index, clause = item
        normalized = normalize_report_text(clause)
        score = min(len(normalized), 180)
        if any(
            re.search(rf"(?<!\w){re.escape(keyword)}(?!\w)", normalized)
            for keyword in HIGH_CONFIDENCE_REPORT_CATEGORIES
        ):
            score += 140
        if any(signal in normalized for signal in PROBLEM_SIGNAL_WORDS):
            score += 80
        # Answers such as "No, los carros..." explain a workflow question but
        # are weaker than the citizen's direct statement of the problem. Do not
        # penalize concrete negatives such as "no hay" or "no funciona".
        if re.match(r"^(?:si|no)[,;:]\s+", normalized) and not normalized.startswith(
            ("no hay ", "no funciona ", "no sirve ", "no existe ")
        ):
            score -= 160
        # Prefer the earliest equally useful statement; it is normally the
        # citizen's initial, complete description.
        return score, -index

    problem = max(enumerate(clauses), key=clause_score)[1].strip(" .") if clauses else ""
    if not problem:
        problem = cleaned.strip(" .")
    # A generic location tail adds no problem detail and would otherwise yield
    # wording such as "en la calle en Vasconcelos" once the structured address
    # is appended below.
    problem = re.sub(
        r"\s+en\s+(?:la\s+)?(?:calle|ubicaci[oó]n|direcci[oó]n)\s*$",
        "",
        problem,
        flags=re.IGNORECASE,
    ).strip(" .")
    # Natural answers often begin with conversational fillers ("en que hay",
    # "pues que..."). They are not part of the municipal report and otherwise
    # produce awkward summaries such as "Se reporta en que hay...".
    problem = re.sub(
        r"^(?:(?:en|es)\s+que|pues(?:\s+que)?|que)\s+",
        "",
        problem,
        flags=re.IGNORECASE,
    ).strip(" .")

    normalized_problem = normalize_report_text(problem)
    if normalized_problem.startswith("se reporta"):
        summary = problem
    elif normalized_problem.startswith(
        ("hay ", "no hay ", "falta ", "el ", "la ", "los ", "las ")
    ):
        summary = f"Se reporta que {problem[0].lower() + problem[1:]}"
    else:
        summary = f"Se reporta {problem[0].lower() + problem[1:]}" if problem else ""

    summary = " ".join(summary.split()).strip(" .")
    if len(summary) > max_length:
        summary = summary[:max_length].rsplit(" ", 1)[0].rstrip(" ,.;:")
    return f"{summary}." if summary else ""


def infer_high_confidence_report_category(description: str | None) -> str | None:
    normalized = normalize_report_text(description)
    if not normalized:
        return None

    matched_codes = {
        code
        for keyword, code in HIGH_CONFIDENCE_REPORT_CATEGORIES.items()
        if re.search(rf"(?<!\w){re.escape(keyword)}(?!\w)", normalized)
    }
    if len(matched_codes) == 1:
        return matched_codes.pop()
    return None


def merge_citizen_report_description(
    existing: str | None,
    citizen_message: str | None,
    *,
    max_length: int = 1500,
) -> str:
    current = sanitize_report_description(existing)
    incoming = sanitize_report_description(citizen_message)
    normalized_current = normalize_report_text(current)
    normalized_incoming = normalize_report_text(incoming)

    if not incoming:
        return current
    if normalized_current in INVALID_REQUIRED_VALUES or normalized_current.startswith(
        "problema reportado:"
    ):
        return incoming[:max_length]
    if normalized_incoming in normalized_current:
        return current[:max_length]
    if normalized_current and normalized_current in normalized_incoming:
        return incoming[:max_length]
    if not current:
        return incoming[:max_length]
    return f"{current}. {incoming}"[:max_length]


def is_meaningful_report_description(value: str | None) -> bool:
    normalized = normalize_report_text(value)
    return bool(
        normalized not in INVALID_REQUIRED_VALUES
        and not normalized.startswith("problema reportado:")
        and not is_report_intent_only(value)
        # Una descripción breve como "un bache" sigue siendo información real.
        # La protección importante es rechazar vacíos y placeholders, no imponer
        # una longitud que termine negando reportes válidos.
        and len(re.sub(r"\W", "", normalized)) >= 4
    )


def report_description_location_conflict(
    description: str | None,
    street: str | None,
    number: str | None,
    neighborhood: str | None,
) -> str | None:
    """Return the structured field contaminating ``selection4``, if any.

    This deliberately validates field ownership rather than trying to decide
    what the citizen meant.  The model owns the semantic summary; this boundary
    only prevents a street, number or neighborhood from being submitted as the
    problem (or repeated inside it).
    """

    def comparison_text(value: str | None) -> str:
        normalized = normalize_report_text(value)
        return " ".join(re.sub(r"[^a-z0-9]+", " ", normalized).split())

    def contains_phrase(container: str, candidate: str) -> bool:
        return bool(
            candidate
            and re.search(
                rf"(?<!\w){re.escape(candidate)}(?!\w)",
                container,
            )
        )

    def contains_locative_reference(container: str, candidate: str) -> bool:
        if not candidate:
            return False
        locative_prefix = (
            r"(?:en|sobre|por|hacia|desde|frente\s+a|junto\s+a|"
            r"cruce\s+con|ubicad[oa]s?\s+en)"
        )
        optional_kind = r"(?:la|el|las|los|calle|avenida|colonia)"
        if re.search(
            rf"(?<!\w){locative_prefix}\s+(?:{optional_kind}\s+)*"
            rf"{re.escape(candidate)}(?!\w)",
            container,
        ):
            return True

        ignored_location_tokens = {
            "avenida",
            "calle",
            "colonia",
            "boulevard",
            "carretera",
        }
        significant_tokens = [
            token
            for token in candidate.split()
            if token not in ignored_location_tokens and len(token) >= 4
        ]
        return any(
            re.search(
                rf"(?<!\w){locative_prefix}\s+(?:{optional_kind}\s+)*"
                rf"{re.escape(token)}(?!\w)",
                container,
            )
            for token in significant_tokens
        )

    problem = comparison_text(description)
    if not problem:
        return None

    for field, raw_location in (
        ("selection5", street),
        ("selection6", number),
        ("selection7", neighborhood),
    ):
        location = comparison_text(raw_location)
        if not location:
            continue
        if problem == location:
            return field

        # A number can legitimately describe quantity (for example, "tres
        # luminarias"). Only an exact numeric description is a field collision.
        if field == "selection6":
            continue

        if contains_locative_reference(problem, location):
            return field

        problem_size = len(re.sub(r"\W", "", problem))
        location_size = len(re.sub(r"\W", "", location))
        if problem_size >= 6 and contains_phrase(location, problem):
            return field
        if (
            location_size >= 8 or len(location.split()) >= 2
        ) and contains_phrase(problem, location):
            return field

    return None


def choose_report_description_for_submission(
    *,
    model_description: str | None,
    evidence_description: str | None,
    street: str | None,
    number: str | None,
    neighborhood: str | None,
) -> str:
    """Return the model-owned summary for final boundary validation.

    Transcript evidence may help restore other structured report fields, but it
    must never become a second writer for ``selection4``. Invalid model output
    is returned unchanged so validation can block it and the model can retry
    with the same conversation context.
    """
    proposed = sanitize_report_description(model_description)
    return proposed


def is_valid_reporter_name(value: str | None) -> bool:
    normalized = normalize_report_text(value)
    return bool(
        normalized not in INVALID_REQUIRED_VALUES | {"ciudadano", "usuario"}
        and not normalized.startswith("[chat]")
        and len(re.sub(r"\W", "", normalized)) >= 2
    )


def normalize_reporter_name_input(value: str | None) -> str | None:
    """Convert explicit privacy/name refusals into CIAC's anonymous identity."""
    raw = " ".join(str(value or "").split()).strip()
    normalized = normalize_report_text(raw)
    colloquial_refusal = re.fullmatch(
        r"(?:no+|nel(?:\s+pastel)?|nop|nope|paso|mejor\s+no)(?:\s+gracias)?[.!]?",
        normalized,
    )
    refuses_action = re.search(
        r"\b(?:no\s+(?:quiero|deseo|voy\s+a)|prefiero\s+no|me\s+niego)\b",
        normalized,
    )
    refuses_personal_data = (
        re.search(
            r"\b(?:no|nunca)\b.*\b(?:compart\w*|proporcion\w*|dar\w*|decir\w*|revel\w*)\b",
            normalized,
        )
        and re.search(r"\b(?:nombre|datos?|informacion)\b", normalized)
    )
    privacy_language = re.search(
        r"\b(?:anonim\w*|omitir\w*|privad\w*|personal(?:es)?|reserv\w*|sin\s+nombre)\b",
        normalized,
    )
    if (
        colloquial_refusal
        or refuses_action
        or refuses_personal_data
        or privacy_language
    ):
        return "Anónimo"
    return raw if is_valid_reporter_name(raw) else None


def resolve_trusted_reporter_name(sender_name: str | None) -> str:
    """Use Chat2Desk identity metadata, never a conversational field answer."""
    raw = " ".join(str(sender_name or "").split()).strip()
    if normalize_report_text(raw).startswith("[chat]") or raw.casefold().startswith("[chat]"):
        return "Usuario Web"
    trusted = normalize_reporter_name_input(sender_name)
    return trusted or "Anónimo"


def normalize_report_number_input(value: str | None) -> str | None:
    raw = " ".join(str(value or "").split()).strip()
    # WhatsApp preserves punctuation and typographic quotes typed by the
    # citizen.  They do not change the meaning of an otherwise unambiguous
    # number answer, so remove them only at the edges before interpreting it.
    normalized = normalize_report_text(raw).strip(
        " \t\r\n.,;:!?¡¿\"'“”‘’«»()[]{}"
    )
    if normalized.isdigit():
        return normalized
    # Citizens rarely answer with a bare number. Accept the same value when it
    # is wrapped in natural wording such as "Número 136" or "el número es
    # 136". This parser is only used while resolving the exterior-number field,
    # so it does not steal unrelated numbers from the report description.
    labelled_number = re.fullmatch(
        r"(?:el\s+)?n[uú]mero(?:\s+exterior)?\s*(?:es\s+|[:#]\s*)?(\d{1,8})[.!]?",
        raw,
        flags=re.IGNORECASE,
    )
    if labelled_number:
        return labelled_number.group(1)
    hash_number = re.fullmatch(r"#\s*(\d{1,8})[.!]?", raw)
    if hash_number:
        return hash_number.group(1)
    # Una referencia adicional no invalida el número exterior que el ciudadano
    # proporcionó en respuesta directa a la pregunta por la numeración.
    number_with_reference = re.fullmatch(
        r"(\d{1,8})\s*,\s*[^\d].+",
        raw,
    )
    if number_with_reference:
        return number_with_reference.group(1)
    if normalized in {
        "sin numero",
        "son numero",
        "no tiene numero",
        "no tiene numeracion",
        "no hay numero",
        "no se el numero",
        "es esquina",
        "en esquina",
        "s/n",
        "sn",
    }:
        return "0000"
    # Resolve clear natural-language statements while the caller owns the
    # exterior-number field.  This is deliberately structural rather than a
    # growing list of complete citizen phrases; genuinely novel or ambiguous
    # language is delegated to the semantic resolver.
    number_concept = r"(?:n[uú]mero|numeraci[oó]n)"
    unavailable_number = re.search(
        rf"\b(?:sin\s+{number_concept}|"
        rf"no\s+(?:hay|tiene|existe|cuenta\s+con)\s+(?:un\s+)?{number_concept}|"
        rf"carece\s+de\s+{number_concept})\b",
        normalized,
        flags=re.IGNORECASE,
    )
    unknown_number = re.search(
        rf"\b(?:no\s+(?:se|conozco|recuerdo)|desconozco)\b.*\b{number_concept}\b",
        normalized,
        flags=re.IGNORECASE,
    )
    if unavailable_number or unknown_number:
        return "0000"
    return None


def apply_report_field_update(
    answers: dict[str, str],
    field: str,
    value,
    *,
    allow_overwrite: bool = False,
) -> tuple[bool, str | None]:
    """Validate and atomically apply one monotonic report field update."""
    normalized_value = value
    if field in {"selection5", "selection7"}:
        normalized_value = canonical_report_location_value(field, value)
    elif field == "selection6":
        normalized_value = normalize_report_number_input(value)
    if normalized_value is None or (
        field in {"selection5", "selection6", "selection7"}
        and not str(normalized_value).strip()
    ):
        previous = answers.get(field)
        return False, str(previous) if previous is not None else None

    previous = answers.get(field)
    if (
        field in {"selection5", "selection6", "selection7"}
        and str(previous or "").strip()
        and str(previous) != str(normalized_value)
        and not allow_overwrite
    ):
        return False, str(previous)
    answers[field] = normalized_value
    return True, str(normalized_value)


def validate_structured_report_number_decision(value: str | None) -> str | None:
    """Validate the model's closed interpretation of a free-language answer."""
    decision = normalize_report_text(value)
    return decision if decision in {"provided", "unavailable", "unclear"} else None


def should_resolve_report_number_semantically(
    pending_field: str | None,
    citizen_message: str | None,
    parsed_answers: dict[str, str] | None = None,
) -> bool:
    """Delegate an unresolved number turn without constraining citizen wording."""
    if str(pending_field or "").strip() != "selection6" or parsed_answers:
        return False
    compact = " ".join(str(citizen_message or "").split()).strip()
    if not compact:
        return False
    return normalize_report_text(compact) not in REPORT_CONTROL_MESSAGES


def extract_pending_report_answers(
    pending_field: str | None,
    citizen_message: str | None,
    *,
    existing_fields: dict[str, str] | None = None,
) -> dict[str, str]:
    """Parse the requested field from durable state, independent of prompt wording."""
    field = str(pending_field or "").strip()
    raw = str(citizen_message or "").strip()
    compact = " ".join(raw.split()).strip()
    normalized = normalize_report_text(compact)
    if not field or not compact:
        return {}
    existing_fields = existing_fields or {}
    if str(existing_fields.get(field) or "").strip():
        # Captured fields are monotonic. A correction must enter through an
        # explicit correction path instead of an ordinary pending answer.
        return {}
    if normalized in REPORT_CONTROL_MESSAGES and field != "selection2":
        return {}

    if field == "selection6":
        number = normalize_report_number_input(compact)
        return {field: number} if number is not None else {}
    if field == "selection2":
        # Reporter identity is supplied by Chat2Desk metadata. Consuming the
        # next citizen message here previously stored arbitrary report text as
        # ``nombreReportante`` in CIAC.
        return {}
    if field == "selection4":
        return {field: compact} if is_meaningful_report_description(compact) else {}
    if field == "selection7":
        colony = (
            canonical_report_location_value(field, compact)
            or find_canonical_report_colony_mention(compact)
        )
        return {field: colony} if colony else {}
    if field != "selection5":
        return {}

    # A citizen may answer with a full sentence or complete postal address.
    # Prefer the recognized catalog fragments over storing that prose as the
    # street (the production Alma incident did exactly that).
    catalog_street = find_canonical_report_street_mention(compact)
    catalog_colony = find_canonical_report_colony_mention(compact)
    if catalog_street:
        answers = {"selection5": catalog_street}
        adjacent_number = extract_report_number_after_street(
            compact,
            catalog_street,
        )
        if adjacent_number:
            answers["selection6"] = adjacent_number
        if catalog_colony:
            answers["selection7"] = catalog_colony
        return {
            key: value for key, value in answers.items()
            if value and not str(existing_fields.get(key) or "").strip()
        }

    # Citizens frequently send street, exterior number and neighborhood in one
    # message. Preserve all three instead of asking for information already sent.
    one_line = re.fullmatch(
        r"(.+?)\s+(\d{1,8})\s+(?:colonia|fraccionamiento|fracc\.?|col\.?)\s+(.+)",
        compact,
        flags=re.IGNORECASE,
    )
    if one_line:
        answers = {
            "selection5": canonical_report_location_value(
                "selection5", one_line.group(1).strip()
            ),
            "selection6": one_line.group(2),
            "selection7": canonical_report_location_value(
                "selection7", one_line.group(3).strip()
            ),
        }
        return {
            key: value for key, value in answers.items()
            if value and not str(existing_fields.get(key) or "").strip()
        }

    # Preserve the structured part of addresses that include a landmark after
    # the number, for example "Río Guadalquivir 136 esquina con Río
    # Tamazunchale". The landmark remains citizen evidence in the transcript;
    # CIAC receives the canonical street and exterior number in their fields.
    street_number_reference = re.fullmatch(
        r"(.+?)\s+(\d{1,8})(?:\s+(?:esquina|entre|frente|a\s+un\s+lado)\b.*)?",
        compact,
        flags=re.IGNORECASE,
    )
    if street_number_reference:
        answers = {
            "selection5": canonical_report_location_value(
                "selection5", street_number_reference.group(1).strip()
            ),
            "selection6": street_number_reference.group(2),
        }
        return {
            key: value for key, value in answers.items()
            if value and not str(existing_fields.get(key) or "").strip()
        }

    lines = [" ".join(line.split()).strip() for line in raw.splitlines() if line.strip()]
    if lines:
        first = re.fullmatch(r"(.+?)\s+(\d{1,8})", lines[0])
        if first:
            answers = {
                "selection5": canonical_report_location_value(
                    "selection5", first.group(1).strip()
                ),
                "selection6": first.group(2),
            }
            if len(lines) > 1:
                neighborhood = re.sub(
                    r"^(?:colonia|fraccionamiento|fracc\.?|col\.?)\s+",
                    "",
                    lines[1],
                    flags=re.IGNORECASE,
                ).strip()
                if neighborhood:
                    answers["selection7"] = canonical_report_location_value(
                        "selection7", neighborhood
                    )
            return {
                key: value for key, value in answers.items()
                if value and not str(existing_fields.get(key) or "").strip()
            }

    street = canonical_report_location_value("selection5", compact)
    return {"selection5": street} if street else {}


def extract_report_field_answer(
    previous_assistant_message: str | None,
    citizen_message: str | None,
) -> tuple[str, str] | None:
    """Capture a field from the question context, independent of issue vocabulary."""
    previous = normalize_report_text(previous_assistant_message)
    answer = " ".join(str(citizen_message or "").split()).strip()
    normalized_answer = normalize_report_text(answer)
    asks_for_name = any(
        phrase in previous
        for phrase in ("cual es tu nombre", "me compartes tu nombre", "nombre del ciudadano")
    )
    if not previous or (
        normalized_answer in REPORT_CONTROL_MESSAGES and not asks_for_name
    ):
        return None

    if any(phrase in previous for phrase in ("numero exterior", "cual es el numero", "que numero")):
        number = normalize_report_number_input(answer)
        return ("selection6", number) if number is not None else None
    if any(phrase in previous for phrase in ("en que calle", "cual es la calle", "nombre de la calle")):
        street = canonical_report_location_value("selection5", answer)
        return ("selection5", street) if street else None
    if any(phrase in previous for phrase in ("en que colonia", "cual es la colonia", "nombre de la colonia")):
        colony = canonical_report_location_value("selection7", answer)
        return ("selection7", colony) if colony else None
    if asks_for_name:
        # Legacy prompts may still be visible in an existing conversation, but
        # their answer must never overwrite the trusted Chat2Desk identity.
        return None
    if any(
        phrase in previous
        for phrase in (
            "que deseas reportar",
            "que problema presenta",
            "cual es el motivo del reporte",
            "que problema deseas reportar",
            "describe el problema",
            "explicame que deseas reportar",
            "que esta ocurriendo",
            "que esta pasando",
            "describe brevemente la situacion",
        )
    ):
        return ("selection4", answer) if is_meaningful_report_description(answer) else None
    return None


def is_explicit_report_intent(value: str | None) -> bool:
    normalized = normalize_report_text(value)
    return any(phrase in normalized for phrase in REPORT_INTENT_PHRASES)


def is_likely_report_description(
    value: str | None,
    *,
    previous_assistant_message: str | None = None,
) -> bool:
    """Return True only when a citizen message can safely describe the issue."""
    normalized = normalize_report_text(value)
    if not is_meaningful_report_description(value):
        return False
    if normalized in REPORT_CONTROL_MESSAGES or normalized.isdigit():
        return False
    if is_report_intent_only(value):
        return False

    # A problem keyword inside an answer to a structured workflow question
    # does not turn that answer into the report description. The requested
    # field owns the turn; selection4 must not become a transcript accumulator.
    previous = normalize_report_text(previous_assistant_message)
    asked_for_structured_non_problem_field = any(
        phrase in previous
        for phrase in (
            "cual es la calle",
            "en que calle",
            "numero exterior",
            "cual es el numero",
            "en que colonia",
            "cual es la colonia",
            "deseas agregar una imagen",
            "quieres agregar una imagen",
            "cual es tu nombre",
        )
    )
    if asked_for_structured_non_problem_field:
        return False
    if infer_high_confidence_report_category(value):
        return True
    if any(signal in normalized for signal in PROBLEM_SIGNAL_WORDS):
        return True

    asked_for_problem = any(
        phrase in previous
        for phrase in (
            "que deseas reportar",
            "que problema presenta",
            "cual es el motivo del reporte",
            "que problema deseas reportar",
            "describe el problema",
            "explicame que deseas reportar",
            "que esta ocurriendo",
            "que esta pasando",
            "describe brevemente la situacion",
        )
    )
    return asked_for_problem


def establishes_report_intent(
    value: str | None,
) -> bool:
    """Require citizen-authored evidence before activating report behavior."""
    raw = " ".join(str(value or "").split()).strip()
    if not raw:
        return False
    # A citizen can state a concrete report and finish with a courtesy
    # question ("quiero levantar un reporte... ¿puedo reportar?"). The explicit
    # request is authoritative; punctuation must not erase that evidence.
    if is_explicit_report_intent(raw):
        return True
    if raw.endswith("?"):
        return False
    if DECLARATIVE_REPORT_REQUEST_PATTERN.search(raw):
        return True
    return is_likely_report_description(raw)


def report_session_has_confirmed_intent(session: dict | None) -> bool:
    """Support new sessions and safely recover grounded legacy sessions."""
    session = session or {}
    if session.get("report_intent_confirmed") is True:
        return True
    return any(
        establishes_report_intent(message)
        for message in session.get("citizen_report_messages", []) or []
    )


def infer_unsolicited_report_answers(
    existing: dict[str, str],
    citizen_message: str | None,
    *,
    pending_field: str | None = None,
) -> dict[str, str]:
    """Capture useful report fragments even when citizens answer in bursts.

    Chat users often send street, neighborhood and problem as separate messages
    without waiting for SAM.  Prompt-only extraction loses those fragments when
    the visible question still asks for a different field.
    """
    compact = " ".join(str(citizen_message or "").split()).strip()
    normalized = normalize_report_text(compact)
    if not compact or normalized in REPORT_CONTROL_MESSAGES:
        return {}

    # A requested structured field owns the turn. If its deterministic parser
    # could not understand the answer, the semantic resolver must decide it;
    # treating the same text as a new problem corrupts selection4.
    if str(pending_field or "").strip() == "selection6":
        return {}

    updates: dict[str, str] = {}
    if not str(existing.get("selection6") or "").strip():
        number = normalize_report_number_input(compact)
        if number is not None:
            updates["selection6"] = number
            return updates

    inferred_category = infer_high_confidence_report_category(compact)
    if inferred_category or any(signal in normalized for signal in PROBLEM_SIGNAL_WORDS):
        updates["selection4"] = merge_citizen_report_description(
            existing.get("selection4"),
            compact,
        )
        if inferred_category:
            updates["selection1"] = inferred_category
        return updates

    # Once a street is known, short phrases such as "en Palo Blanco" are a
    # natural neighborhood fragment. Avoid interpreting street-like prefixes.
    if (
        str(existing.get("selection5") or "").strip()
        and not str(existing.get("selection7") or "").strip()
        and normalized.startswith("en ")
    ):
        neighborhood = compact[3:].strip()
        street_prefixes = ("calle ", "avenida ", "av. ", "carretera ", "boulevard ")
        if neighborhood and not normalize_report_text(neighborhood).startswith(street_prefixes):
            updates["selection7"] = neighborhood
    return updates


def contains_complete_report_phrase(text: str | None, phrases) -> bool:
    """Match control words as complete words, never inside citizen vocabulary."""
    normalized = normalize_report_text(text)
    return any(
        re.search(rf"(?<!\w){re.escape(normalize_report_text(phrase))}(?!\w)", normalized)
        for phrase in phrases
        if normalize_report_text(phrase)
    )


def resolve_unambiguous_catalog_category(prompt: str | None, description: str | None) -> str | None:
    """Use an exact, unique subject noun from the active CIAC catalog only.

    This is intentionally conservative: if several catalog subjects match,
    classification remains unresolved rather than choosing an arbitrary ID.
    """
    ignored = {
        "avenida", "calle", "ciudadano", "colonia", "donde", "estorba",
        "lugar", "numero", "problema", "reporte", "solicitud", "tiene",
        "ubicado", "visibilidad",
    }

    def subject_words(value: str | None) -> set[str]:
        words = re.findall(r"[a-z]{6,}", normalize_report_text(value))
        return {
            word[:-1] if word.endswith("s") else word
            for word in words
            if word not in ignored
        }

    issue_words = subject_words(description)
    if not issue_words:
        return None
    candidates = {
        entry.value
        for entry in parse_report_catalog(prompt)
        if issue_words & subject_words(entry.label)
    }
    return next(iter(candidates)) if len(candidates) == 1 else None


def fallback_report_category_id(prompt: str | None = None) -> str:
    """Return CIAC's general Atención Ciudadana inbox for unknown subjects."""
    # Keep the ID stable even if a shortened runtime prompt omits the catalog.
    # When present, the label documents that the configured catalog agrees.
    for entry in parse_report_catalog(prompt):
        label = normalize_report_text(entry.label)
        if "gestiones direccion de atencion ciudadana" in label:
            return entry.value
    return UNCLASSIFIED_REPORT_CATEGORY_ID


def sidewalk_sign_category_options(prompt: str | None, description: str | None) -> dict[str, str]:
    """Read the two sidewalk-obstruction IDs from the active CIAC prompt catalog."""
    issue = normalize_report_text(description)
    if not all(word in issue for word in ("banqueta", "letrero")):
        return {}
    if not any(word in issue for word in ("obstruid", "obstruccion", "obstruye")):
        return {}

    options = {}
    for entry in parse_report_catalog(prompt):
        label = normalize_report_text(entry.label)
        if "obstruccion de banqueta" not in label:
            continue
        if "objetos moviles" in label:
            options["movil"] = entry.value
        elif "construccion fija" in label:
            options["fijo"] = entry.value
    return options if len(options) == 2 else {}


def classify_sidewalk_sign_answer(
    answer: str | None,
    *,
    prompt: str | None,
    description: str | None,
) -> str | None:
    options = sidewalk_sign_category_options(prompt, description)
    normalized = normalize_report_text(answer)
    if not options:
        return None
    if contains_complete_report_phrase(normalized, ("fijo", "fija", "anclado", "anclada", "no se puede mover")):
        return options["fijo"]
    if contains_complete_report_phrase(normalized, ("movil", "se puede mover", "lo mueven")):
        return options["movil"]
    return None


def next_missing_report_field(
    selections: dict[str, str],
    *,
    prompt: str | None = None,
    declared_emergency: bool = False,
) -> tuple[str, str] | None:
    """Ask only for an absent fact; never discard facts already supplied."""
    if not is_meaningful_report_description(selections.get("selection4")):
        return "selection4", "¿Qué problema deseas reportar? Descríbelo brevemente."
    if normalize_report_text(selections.get("selection5")) in INVALID_REQUIRED_VALUES:
        question = (
            "¿En qué calle, cruce o referencia se encuentra la emergencia?"
            if declared_emergency
            else "¿En qué calle se encuentra el problema?"
        )
        return "selection5", question
    if not declared_emergency:
        if normalize_report_number_input(selections.get("selection6")) is None:
            return "selection6", "¿Cuál es el número exterior? Si no existe o no lo conoces, indícame “sin número”."
        if normalize_report_text(selections.get("selection7")) in INVALID_REQUIRED_VALUES | {"0000"}:
            return "selection7", "¿En qué colonia se encuentra el problema?"
    category = str(selections.get("selection1") or "").strip()
    if not category.isdigit() or category == "0":
        if sidewalk_sign_category_options(prompt, selections.get("selection4")):
            return "selection1", "Para clasificar el reporte correctamente, ¿el letrero se puede mover o está fijo/anclado a la banqueta?"
        # Para otros asuntos conservamos la validación existente. Sin una
        # clasificación respaldada por el catálogo no hay una respuesta que
        # podamos convertir a ID y repetir la pregunta atraparía al usuario.
        return None
    return None


def next_missing_report_detail_before_image(
    selections: dict[str, str],
    *,
    prompt: str | None = None,
    declared_emergency: bool = False,
) -> tuple[str, str] | None:
    """Return only report facts that must precede the optional-image question."""
    missing = next_missing_report_field(
        selections,
        prompt=prompt,
        declared_emergency=declared_emergency,
    )
    if missing and missing[0] in {
        "selection4", "selection5", "selection6", "selection7",
    }:
        return missing
    return None


def determine_report_progress(
    selections: dict[str, str],
    *,
    declared_emergency: bool | None,
    image_prompted: bool,
    image_decision: str | None,
    has_images: bool,
    prompt: str | None = None,
    incident_snapshot: dict | None = None,
) -> ReportProgressDecision:
    """Choose the next report transition from authoritative stored fields.

    The model may phrase ordinary conversation, but it must not decide whether
    a field already exists.  This keeps a complete one-message report from
    falling back into repeated street/number/neighborhood questions.
    """
    if declared_emergency is None:
        return ReportProgressDecision(
            "await_emergency_answer",
            response="¿Esta situación representa una emergencia?",
        )

    missing = next_missing_report_field(
        selections,
        prompt=prompt,
        declared_emergency=declared_emergency,
    )
    if missing:
        field, response = missing
        return ReportProgressDecision("ask_field", field, response)

    if declared_emergency:
        return ReportProgressDecision("submit_emergency")

    snapshot_has_images = bool(
        (incident_snapshot or {}).get("image_count")
        or (incident_snapshot or {}).get("images")
    )
    if not (has_images or snapshot_has_images) and not image_prompted and image_decision is None:
        return ReportProgressDecision(
            "ask_image",
            response=(
                "No se han adjuntado imágenes al reporte. ¿Deseas agregar una "
                "imagen para complementar tu reporte? La imagen es opcional."
            ),
        )

    return ReportProgressDecision("continue")


def select_citizen_report_description(
    conversation_turns: list[tuple[str, str]],
) -> str:
    """Select the best citizen-authored problem statement from recent turns.

    This deliberately has a generic fallback: vocabulary lists only improve the
    ranking and never decide whether an unfamiliar citizen phrase is accepted.
    """
    candidates: list[tuple[int, int, str]] = []
    previous_assistant = ""

    for role, raw_content in conversation_turns:
        content = sanitize_report_description(raw_content)
        normalized = normalize_report_text(content)
        normalized_role = str(role or "").strip().lower()
        if normalized_role == "assistant":
            previous_assistant = content
            continue
        if normalized_role != "user" or not is_meaningful_report_description(content):
            continue
        if normalized in REPORT_CONTROL_MESSAGES or normalized.isdigit():
            continue
        if is_report_intent_only(content):
            continue
        if normalized in {"hola", "buen dia", "buenas tardes", "buenas noches"}:
            continue

        previous = normalize_report_text(previous_assistant)
        asked_for_non_problem_field = any(
            phrase in previous
            for phrase in (
                "cual es la calle",
                "en que calle",
                "numero exterior",
                "cual es el numero",
                "en que colonia",
                "cual es la colonia",
                "deseas agregar una imagen",
                "quieres agregar una imagen",
                "es una emergencia",
                "cual es tu nombre",
            )
        )
        if asked_for_non_problem_field:
            continue

        score = min(len(normalized), 80)
        if is_likely_report_description(
            content,
            previous_assistant_message=previous_assistant,
        ):
            score += 100
        elif is_explicit_report_intent(content):
            score += 60

        candidates.append((score, -len(candidates), content))

    if not candidates:
        return ""
    return max(candidates)[2]


def reconcile_with_citizen_evidence(
    model_category: str | None,
    model_description: str | None,
    citizen_description: str | None,
) -> tuple[str, str, bool]:
    """Preserve the model-owned summary and repair only its category."""
    category = " ".join(str(model_category or "").split()).strip()
    description = " ".join(str(model_description or "").split()).strip()

    inferred_category = infer_high_confidence_report_category(description)
    if inferred_category:
        category = inferred_category

    changed = (
        category != " ".join(str(model_category or "").split()).strip()
        or description != " ".join(str(model_description or "").split()).strip()
    )
    return category, description, changed


def validate_and_normalize_report_submission(
    *,
    selection1: str | None,
    selection2: str | None,
    selection4: str | None,
    selection5: str | None,
    selection6: str | None,
    selection7: str | None,
    declared_emergency: bool = False,
    allowed_category_ids: tuple[str, ...] | list[str] | set[str] | None = None,
) -> tuple[dict[str, str] | None, str | None]:
    values = {
        "selection1": " ".join(str(selection1 or "").split()).strip(),
        "selection2": normalize_reporter_name_input(selection2) or "",
        "selection3": "",
        "selection4": sanitize_report_description(selection4),
        "selection5": " ".join(str(selection5 or "").split()).strip(),
        "selection6": " ".join(str(selection6 or "").split()).strip(),
        "selection7": " ".join(str(selection7 or "").split()).strip(),
    }

    emergency_submission = bool(
        declared_emergency or values["selection1"] == "964"
    )
    if declared_emergency:
        values["selection1"] = "964"

    if not values["selection1"].isdigit() or values["selection1"] == "0":
        return None, "debes identificar un ID de asunto numérico y válido"

    if not is_valid_reporter_name(values["selection2"]):
        return None, "debes obtener el nombre real del ciudadano"

    normalized_description = normalize_report_text(values["selection4"])
    if not is_meaningful_report_description(values["selection4"]):
        return None, (
            "debes obtener una explicación concreta del problema, basada únicamente "
            "en lo dicho por el ciudadano"
        )
    if normalized_description in REPORT_CONTROL_MESSAGES:
        return None, (
            "selection4 contiene una respuesta operativa de la conversación. "
            "Reconstruye únicamente selection4 como una sola oración breve con "
            "el problema clave dicho por el ciudadano"
        )
    if "?" in values["selection4"] or "¿" in values["selection4"]:
        return None, (
            "selection4 contiene una pregunta. Reconstruye únicamente selection4 "
            "como una oración afirmativa breve con el problema clave dicho por el "
            "ciudadano"
        )

    normalized_reporter_name = normalize_report_text(values["selection2"])
    contains_reporter_name = bool(
        normalized_reporter_name
        and normalized_reporter_name != "anonimo"
        and re.search(
            rf"(?<!\w){re.escape(normalized_reporter_name)}(?!\w)",
            normalized_description,
        )
    )
    contains_email = bool(
        re.search(
            r"(?<![\w.+-])[\w.+-]+@[\w.-]+\.[a-z]{2,}(?!\w)",
            values["selection4"],
            flags=re.IGNORECASE,
        )
    )
    contains_phone = bool(
        re.search(
            r"(?<!\d)(?:\+?\d[\s().-]*){7,15}(?!\d)",
            values["selection4"],
        )
    )
    if contains_reporter_name or contains_email or contains_phone:
        return None, (
            "selection4 contiene datos personales del ciudadano. Reconstruye "
            "únicamente selection4 con el problema municipal, sin nombre ni "
            "información de contacto"
        )

    conflicting_location_field = report_description_location_conflict(
        values["selection4"],
        values["selection5"],
        values["selection6"],
        values["selection7"],
    )
    if conflicting_location_field:
        return None, (
            "selection4 contiene información de ubicación que pertenece a "
            f"{conflicting_location_field}. Reconstruye únicamente selection4 como "
            "una sola oración breve con el problema clave dicho por el ciudadano; "
            "conserva los demás campos y no vuelvas a preguntar datos ya proporcionados"
        )

    if normalize_report_text(values["selection5"]) in INVALID_REQUIRED_VALUES:
        return None, "debes obtener una calle válida"

    normalized_number = normalize_report_number_input(values["selection6"])
    if normalized_number is None and emergency_submission:
        normalized_number = "0000"
    elif normalized_number is None:
        return None, (
            "debes obtener un número exterior numérico; usa 0000 únicamente cuando "
            "el ciudadano confirme que no existe o no lo conoce"
        )
    values["selection6"] = normalized_number

    if (
        not emergency_submission
        and normalize_report_text(values["selection7"])
        in INVALID_REQUIRED_VALUES | {"0000"}
    ):
        return None, "debes obtener una colonia válida"

    # Si la explicación sólo puede corresponder a un asunto conocido, reparar el
    # ID es más útil y seguro que negar el reporte. Los textos ambiguos no se
    # autoclasifican y conservan la selección realizada por el modelo.
    inferred_category = infer_high_confidence_report_category(values["selection4"])
    if inferred_category and not emergency_submission:
        values["selection1"] = inferred_category

    allowed_ids = {str(value).strip() for value in (allowed_category_ids or ())}
    if allowed_ids and values["selection1"] not in allowed_ids:
        return None, (
            "debes identificar un ID de asunto que exista en el catálogo CIAC activo"
        )

    return values, None


def validation_error_to_user_message(validation_error: str | None) -> str:
    error = normalize_report_text(validation_error)
    if "id de asunto" in error:
        return (
            "Ya tengo la descripción y los datos del reporte, pero no pude "
            "identificar con certeza el asunto en el catálogo. No se creó "
            "ningún folio; puedes pedir atención de un agente para revisarlo."
        )
    if "nombre real" in error:
        return "Antes de crear el reporte, ¿me compartes tu nombre? También puedes indicar “Anónimo”."
    if "explicacion concreta" in error:
        return "Antes de crear el reporte, ¿podrías describir brevemente el problema?"
    if "calle valida" in error:
        return "Antes de crear el reporte, ¿en qué calle se encuentra el problema?"
    if "numero exterior" in error:
        return "¿Cuál es el número exterior? Si no existe o no lo conoces, indícame “sin número”."
    if "colonia valida" in error:
        return "Antes de crear el reporte, ¿en qué colonia se encuentra el problema?"
    return "Necesito confirmar un dato antes de crear el reporte. ¿Puedes darme más información?"
