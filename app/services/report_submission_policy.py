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


def normalize_report_number_input(value: str | None) -> str | None:
    raw = " ".join(str(value or "").split()).strip()
    normalized = normalize_report_text(raw)
    if raw.isdigit():
        return raw
    if normalized in {
        "sin numero",
        "no tiene numero",
        "no hay numero",
        "no se el numero",
        "s/n",
        "sn",
    }:
        return "0000"
    return None


def extract_report_field_answer(
    previous_assistant_message: str | None,
    citizen_message: str | None,
) -> tuple[str, str] | None:
    """Capture a field from the question context, independent of issue vocabulary."""
    previous = normalize_report_text(previous_assistant_message)
    answer = " ".join(str(citizen_message or "").split()).strip()
    normalized_answer = normalize_report_text(answer)
    if not previous or normalized_answer in REPORT_CONTROL_MESSAGES:
        return None

    if any(phrase in previous for phrase in ("numero exterior", "cual es el numero", "que numero")):
        number = normalize_report_number_input(answer)
        return ("selection6", number) if number is not None else None
    if any(phrase in previous for phrase in ("en que calle", "cual es la calle", "nombre de la calle")):
        return ("selection5", answer) if is_meaningful_report_description(answer) else None
    if any(phrase in previous for phrase in ("en que colonia", "cual es la colonia", "nombre de la colonia")):
        return ("selection7", answer) if is_meaningful_report_description(answer) else None
    if any(phrase in previous for phrase in ("cual es tu nombre", "me compartes tu nombre", "nombre del ciudadano")):
        return ("selection2", answer) if is_valid_reporter_name(answer) else None
    if any(
        phrase in previous
        for phrase in (
            "que deseas reportar",
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
            "cual es el motivo del reporte",
            "que problema deseas reportar",
            "describe el problema",
            "explicame que deseas reportar",
        )
    )
    return asked_for_problem


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
        "selection2": " ".join(str(selection2 or "").split()).strip(),
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
        return "Necesito confirmar qué problema deseas reportar. ¿Podrías describirlo brevemente?"
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
