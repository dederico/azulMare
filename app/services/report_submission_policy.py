import re
import unicodedata


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
    "quiero hacer un reporte",
    "quiero levantar un reporte",
    "hacer un reporte",
    "levantar un reporte",
    "necesito reportar",
    "deseo reportar",
    "quiero levantar reporte",
    "necesito levantar un reporte",
)

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


def normalize_report_text(value: str | None) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return " ".join(text.casefold().split())


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
    current = " ".join(str(existing or "").split()).strip()
    incoming = " ".join(str(citizen_message or "").split()).strip()
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
        # Una descripción breve como "un bache" sigue siendo información real.
        # La protección importante es rechazar vacíos y placeholders, no imponer
        # una longitud que termine negando reportes válidos.
        and len(re.sub(r"\W", "", normalized)) >= 4
    )


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


def normalize_report_number_input(value: str | None) -> str | None:
    raw = " ".join(str(value or "").split()).strip()
    normalized = normalize_report_text(raw)
    if raw.isdigit():
        return raw
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
    return None


def extract_pending_report_answers(
    pending_field: str | None,
    citizen_message: str | None,
) -> dict[str, str]:
    """Parse the requested field from durable state, independent of prompt wording."""
    field = str(pending_field or "").strip()
    raw = str(citizen_message or "").strip()
    compact = " ".join(raw.split()).strip()
    normalized = normalize_report_text(compact)
    if not field or not compact:
        return {}
    if normalized in REPORT_CONTROL_MESSAGES and field != "selection2":
        return {}

    if field == "selection6":
        number = normalize_report_number_input(compact)
        return {field: number} if number is not None else {}
    if field == "selection2":
        name = normalize_reporter_name_input(compact)
        return {field: name} if name else {}
    if field == "selection4":
        return {field: compact} if is_meaningful_report_description(compact) else {}
    if field == "selection7":
        return {field: compact} if is_meaningful_report_description(compact) else {}
    if field != "selection5":
        return {}

    # Citizens frequently send street, exterior number and neighborhood in one
    # message. Preserve all three instead of asking for information already sent.
    one_line = re.fullmatch(
        r"(.+?)\s+(\d{1,8})\s+(?:colonia|fraccionamiento|fracc\.?|col\.?)\s+(.+)",
        compact,
        flags=re.IGNORECASE,
    )
    if one_line:
        return {
            "selection5": one_line.group(1).strip(),
            "selection6": one_line.group(2),
            "selection7": one_line.group(3).strip(),
        }

    lines = [" ".join(line.split()).strip() for line in raw.splitlines() if line.strip()]
    if lines:
        first = re.fullmatch(r"(.+?)\s+(\d{1,8})", lines[0])
        if first:
            answers = {"selection5": first.group(1).strip(), "selection6": first.group(2)}
            if len(lines) > 1:
                neighborhood = re.sub(
                    r"^(?:colonia|fraccionamiento|fracc\.?|col\.?)\s+",
                    "",
                    lines[1],
                    flags=re.IGNORECASE,
                ).strip()
                if neighborhood:
                    answers["selection7"] = neighborhood
            return answers

    return {"selection5": compact} if is_meaningful_report_description(compact) else {}


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
        return ("selection5", answer) if is_meaningful_report_description(answer) else None
    if any(phrase in previous for phrase in ("en que colonia", "cual es la colonia", "nombre de la colonia")):
        return ("selection7", answer) if is_meaningful_report_description(answer) else None
    if asks_for_name:
        name = normalize_reporter_name_input(answer)
        return ("selection2", name) if name else None
    if any(
        phrase in previous
        for phrase in (
            "que deseas reportar",
            "que problema presenta",
            "cual es el motivo del reporte",
            "que problema deseas reportar",
            "describe el problema",
            "explicame que deseas reportar",
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
    if normalized in REPORT_INTENT_PHRASES:
        return False
    if infer_high_confidence_report_category(value):
        return True
    if any(signal in normalized for signal in PROBLEM_SIGNAL_WORDS):
        return True

    previous = normalize_report_text(previous_assistant_message)
    asked_for_problem = any(
        phrase in previous
        for phrase in (
            "que deseas reportar",
            "que problema presenta",
            "cual es el motivo del reporte",
            "que problema deseas reportar",
            "describe el problema",
            "explicame que deseas reportar",
        )
    )
    return asked_for_problem


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
        match.group(1)
        for match in re.finditer(
            r"^\s*Valor:\s*(\d+)\s*,\s*Tipo:\s*(.+)$",
            str(prompt or ""),
            flags=re.MULTILINE | re.IGNORECASE,
        )
        if issue_words & subject_words(match.group(2))
    }
    return next(iter(candidates)) if len(candidates) == 1 else None


def fallback_report_category_id(prompt: str | None = None) -> str:
    """Return CIAC's general Atención Ciudadana inbox for unknown subjects."""
    # Keep the ID stable even if a shortened runtime prompt omits the catalog.
    # When present, the label documents that the configured catalog agrees.
    for match in re.finditer(
        r"^\s*Valor:\s*(\d+)\s*,\s*Tipo:\s*(.+)$",
        str(prompt or ""),
        flags=re.MULTILINE | re.IGNORECASE,
    ):
        label = normalize_report_text(match.group(2))
        if "gestiones direccion de atencion ciudadana" in label:
            return match.group(1)
    return UNCLASSIFIED_REPORT_CATEGORY_ID


def sidewalk_sign_category_options(prompt: str | None, description: str | None) -> dict[str, str]:
    """Read the two sidewalk-obstruction IDs from the active CIAC prompt catalog."""
    issue = normalize_report_text(description)
    if not all(word in issue for word in ("banqueta", "letrero")):
        return {}
    if not any(word in issue for word in ("obstruid", "obstruccion", "obstruye")):
        return {}

    options = {}
    for match in re.finditer(
        r"^\s*Valor:\s*(\d+)\s*,\s*Tipo:\s*(.+)$",
        str(prompt or ""),
        flags=re.MULTILINE | re.IGNORECASE,
    ):
        label = normalize_report_text(match.group(2))
        if "obstruccion de banqueta" not in label:
            continue
        if "objetos moviles" in label:
            options["movil"] = match.group(1)
        elif "construccion fija" in label:
            options["fijo"] = match.group(1)
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


def next_missing_report_field(selections: dict[str, str], *, prompt: str | None = None) -> tuple[str, str] | None:
    """Ask only for an absent fact; never discard facts already supplied."""
    if not is_meaningful_report_description(selections.get("selection4")):
        return "selection4", "¿Qué problema deseas reportar? Descríbelo brevemente."
    if normalize_report_text(selections.get("selection5")) in INVALID_REQUIRED_VALUES:
        return "selection5", "¿En qué calle se encuentra el problema?"
    if normalize_report_number_input(selections.get("selection6")) is None:
        return "selection6", "¿Cuál es el número exterior? Si no existe o no lo conoces, indícame “sin número”."
    if normalize_report_text(selections.get("selection7")) in INVALID_REQUIRED_VALUES | {"0000"}:
        return "selection7", "¿En qué colonia se encuentra el problema?"
    if not is_valid_reporter_name(selections.get("selection2")):
        return "selection2", "Antes de crear el reporte, ¿me compartes tu nombre? También puedes indicar “Anónimo”."
    category = str(selections.get("selection1") or "").strip()
    if not category.isdigit() or category == "0":
        if sidewalk_sign_category_options(prompt, selections.get("selection4")):
            return "selection1", "Para clasificar el reporte correctamente, ¿el letrero se puede mover o está fijo/anclado a la banqueta?"
        # Para otros asuntos conservamos la validación existente. Sin una
        # clasificación respaldada por el catálogo no hay una respuesta que
        # podamos convertir a ID y repetir la pregunta atraparía al usuario.
        return None
    return None


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
        content = " ".join(str(raw_content or "").split()).strip()
        normalized = normalize_report_text(content)
        normalized_role = str(role or "").strip().lower()
        if normalized_role == "assistant":
            previous_assistant = content
            continue
        if normalized_role != "user" or not is_meaningful_report_description(content):
            continue
        if normalized in REPORT_CONTROL_MESSAGES or normalized.isdigit():
            continue
        if normalized in REPORT_INTENT_PHRASES:
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
    """Prefer grounded citizen wording and repair an unambiguous category."""
    category = " ".join(str(model_category or "").split()).strip()
    description = " ".join(str(model_description or "").split()).strip()
    citizen = " ".join(str(citizen_description or "").split()).strip()

    if is_meaningful_report_description(citizen):
        description = citizen

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
) -> tuple[dict[str, str] | None, str | None]:
    values = {
        "selection1": " ".join(str(selection1 or "").split()).strip(),
        "selection2": normalize_reporter_name_input(selection2) or "",
        "selection3": "",
        "selection4": " ".join(str(selection4 or "").split()).strip(),
        "selection5": " ".join(str(selection5 or "").split()).strip(),
        "selection6": " ".join(str(selection6 or "").split()).strip(),
        "selection7": " ".join(str(selection7 or "").split()).strip(),
    }

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

    if normalize_report_text(values["selection5"]) in INVALID_REQUIRED_VALUES:
        return None, "debes obtener una calle válida"

    normalized_number = normalize_report_number_input(values["selection6"])
    if normalized_number is None:
        return None, (
            "debes obtener un número exterior numérico; usa 0000 únicamente cuando "
            "el ciudadano confirme que no existe o no lo conoce"
        )
    values["selection6"] = normalized_number

    if normalize_report_text(values["selection7"]) in INVALID_REQUIRED_VALUES | {"0000"}:
        return None, "debes obtener una colonia válida"

    # Si la explicación sólo puede corresponder a un asunto conocido, reparar el
    # ID es más útil y seguro que negar el reporte. Los textos ambiguos no se
    # autoclasifican y conservan la selección realizada por el modelo.
    inferred_category = infer_high_confidence_report_category(values["selection4"])
    if inferred_category:
        values["selection1"] = inferred_category

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
