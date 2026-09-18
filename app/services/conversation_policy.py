import re
import unicodedata


EXPLICIT_HANDOFF = "explicit_user_request"
VERIFIED_NO_CONTEXT = "verified_no_context"
TOOL_FAILURE = "tool_failure"
VERIFIED_PUBLIC_PHONE_DIGITS = frozenset(
    {
        "8189882000",  # C4
        "8184004400",  # Conmutador / CIAC
        "8112121212",  # Atención Ciudadana
    }
)
WIDGET_EMPTY_RESPONSE_FALLBACK = (
    "No pude obtener una respuesta en este momento. "
    "¿Deseas que te comunique con un agente de Atención Ciudadana?"
)
OUT_OF_SCOPE_REDIRECT = (
    "Este canal está destinado a reportes, denuncias e información municipal "
    "de San Pedro Garza García. ¿Qué asunto municipal deseas consultar o reportar?"
)


def automatic_report_timeouts_enabled(value: str | None) -> bool:
    """Automatic report creation is opt-in; silence must never create a folio."""
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def extract_confirmed_folio(value) -> str | None:
    """Accept only a complete, numeric folio returned by the report backend."""
    match = re.fullmatch(
        r"\s*Folio:\s*\*?(\d{4,12})\*?\s*",
        str(value or ""),
        flags=re.IGNORECASE,
    )
    return match.group(1) if match else None


def canonical_phone_digits(value) -> str:
    digits = "".join(character for character in str(value or "") if character.isdigit())
    if len(digits) == 13 and digits.startswith("521"):
        return digits[-10:]
    if len(digits) == 12 and digits.startswith("52"):
        return digits[-10:]
    return digits


def trusted_phone_digits(reference_texts=None) -> set[str]:
    """Extract official 10-digit phones returned by trusted knowledge tools."""
    trusted = set()
    for text in reference_texts or []:
        for match in re.finditer(r"(?<!\d)(?:\+?\d[\d\s().-]{8,}\d)", str(text or "")):
            digits = canonical_phone_digits(match.group(0))
            if len(digits) == 10:
                trusted.add(digits)
    return trusted


def is_verified_public_phone(value, trusted_reference_texts=None) -> bool:
    digits = canonical_phone_digits(value)
    return (
        digits in VERIFIED_PUBLIC_PHONE_DIGITS
        or digits in trusted_phone_digits(trusted_reference_texts)
    )


def normalize_policy_text(value: str | None) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = re.sub(r"[^a-zA-Z0-9\s]", " ", text.lower())
    return " ".join(text.split())


def resolve_high_confidence_out_of_scope_response(
    message: str | None,
) -> str | None:
    """Redirect unmistakable general-assistant requests before calling the LLM.

    This guard is intentionally narrow. Prompt policy handles ambiguous topics;
    local code only blocks clear programming requests and isolated arithmetic so
    municipal questions involving prices, taxes or calculations remain valid.
    """
    raw = str(message or "").strip()
    normalized = normalize_policy_text(raw)
    if not normalized:
        return None

    municipal_markers = (
        "san pedro",
        "municipio",
        "municipal",
        "reporte",
        "reportar",
        "denuncia",
        "denunciar",
        "tramite",
        "servicio",
        "predial",
        "multa",
        "folio",
        "bache",
        "luminaria",
        "basura",
        "colonia",
        "calle",
        "parque",
        "permiso",
        "licencia",
        "atencion ciudadana",
    )
    if any(marker in normalized for marker in municipal_markers):
        return None

    programming_markers = (
        "hola mundo",
        "hello world",
        "python",
        "javascript",
        "typescript",
        "programacion",
        "codigo fuente",
        "escribe codigo",
        "genera codigo",
        "haz un script",
        "crea un script",
        "consulta sql",
    )
    if any(marker in normalized for marker in programming_markers):
        return OUT_OF_SCOPE_REDIRECT

    ascii_text = unicodedata.normalize("NFKD", raw.lower())
    ascii_text = "".join(char for char in ascii_text if not unicodedata.combining(char))
    arithmetic_request = re.fullmatch(
        r"\s*[¿?]*(?:(?:cuanto es|cuanto da|calcula|resuelve|resultado de|"
        r"suma|resta|multiplica|divide|hazme una suma(?: de)?)\s*)?"
        r"[0-9\s.,()+\-*/xX÷=]+[?\s]*",
        ascii_text,
    )
    number_count = len(re.findall(r"\d+(?:[.,]\d+)?", ascii_text))
    has_operator = bool(re.search(r"[+\-*/xX÷]", ascii_text))
    if arithmetic_request and number_count >= 2 and has_operator:
        return OUT_OF_SCOPE_REDIRECT

    explicit_math_request = any(
        marker in normalized
        for marker in (
            "hazme una suma",
            "ponme una suma",
            "resuelve esta suma",
            "haz esta operacion matematica",
            "resuelve esta operacion matematica",
        )
    )
    if explicit_math_request:
        return OUT_OF_SCOPE_REDIRECT

    return None


def is_explicit_report_finalization_token(value: str | None) -> bool:
    """Recognize the exact token citizens are instructed to send after photos."""
    return normalize_policy_text(value) == "fin"


def is_likely_bot_echo(
    citizen_text: str | None,
    recent_assistant_texts=None,
) -> bool:
    """Match real echoed bot messages without swallowing short citizen replies."""
    candidate = str(citizen_text or "").strip()
    if not candidate or is_explicit_report_finalization_token(candidate):
        return False

    for assistant_text in recent_assistant_texts or []:
        assistant = str(assistant_text or "").strip()
        if not assistant:
            continue
        if candidate == assistant:
            return True
        if len(candidate) > 20 and len(assistant) > 20:
            if candidate in assistant or assistant in candidate:
                return True
    return False


def dialog_transfer_confirms_pending_control(
    control: dict | None,
    event_timestamp: float | None,
    *,
    tolerance_seconds: float = 2.0,
) -> bool:
    """Trust dialog_transferred only as confirmation of our own pending handoff."""
    if not control or event_timestamp is None:
        return False
    source = str(control.get("source") or "")
    if not source.startswith("pending_transfer:"):
        return False
    try:
        pending_since = float(control.get("updated_at") or 0)
        event_time = float(event_timestamp)
    except (TypeError, ValueError):
        return False
    return pending_since > 0 and event_time + tolerance_seconds >= pending_since


def is_contextual_handoff_request(
    current_message: str | None,
    previous_assistant_message: str | None,
) -> bool:
    """Recognize a citizen accepting/retrying a just-mentioned human handoff.

    Short replies such as "sí", "porfa" or "comunícame con uno" are only
    authoritative when SAM's immediately preceding message mentioned human
    attention or a transfer. This avoids treating an unrelated "sí" as a
    handoff request.
    """
    current = normalize_policy_text(current_message)
    previous = normalize_policy_text(previous_assistant_message)
    if not current or not previous:
        return False

    previous_mentions_human = any(
        marker in previous
        for marker in (
            "agente humano",
            "agente ciudadano",
            "atencion humana",
            "una persona",
            "un asesor",
            "un ejecutivo",
            "transferencia",
            "transferirte",
            "canalizarte",
            "comunicarte con",
        )
    )
    if not previous_mentions_human:
        return False

    affirmative_replies = {
        "si",
        "si sam",
        "si por favor",
        "si porfa",
        "si gracias",
        "si adelante",
        "porfa",
        "por favor",
        "claro",
        "claro que si",
        "adelante",
        "de acuerdo",
        "ok",
        "okay",
        "hazlo",
        "please",
    }
    if current in affirmative_replies:
        return True

    # Accept natural, short confirmations only in the context of SAM's
    # immediately preceding handoff offer. The contextual requirement above
    # keeps phrases such as "sí, por favor" from authorizing a transfer after
    # an unrelated question.
    current_words = current.split()
    if len(current_words) <= 6 and (
        current.startswith("si ")
        or current.startswith("claro ")
        or current.startswith("de acuerdo ")
        or current.startswith("me gustaria")
        or current.startswith("quisiera")
    ):
        return True

    asks_to_connect = any(
        marker in current
        for marker in (
            "me puedes comunicar",
            "puedes comunicarme",
            "comunicar con uno",
            "comunicarme con uno",
            "pasame con uno",
            "pasa con uno",
            "intenta de nuevo",
            "vuelve a intentar",
        )
    )
    return asks_to_connect


def greeting_display_name(sender_name: str | None, transport: str | None) -> str:
    """Hide Chat2Desk's synthetic client label only in widget conversations."""
    clean_name = str(sender_name or "").strip()
    if str(transport or "").strip().lower() == "widget" and re.match(
        r"^\[chat\](?:\s|$)", clean_name, flags=re.IGNORECASE
    ):
        return ""
    return clean_name or "ciudadano"


def apply_widget_empty_response_fallback(
    response: str | None,
    transport: str | None,
) -> str:
    """Prevent empty user-facing messages only for the web widget transport."""
    text = str(response or "")
    if str(transport or "").strip().lower() == "widget" and not text.strip():
        return WIDGET_EMPTY_RESPONSE_FALLBACK
    return text


def is_trusted_human_control(control: dict | None) -> bool:
    """Return True only for takeover sources created by an explicit local action."""
    if not control or control.get("mode") != "human":
        return False

    source = str(control.get("source") or "")
    return (
        source == EXPLICIT_HANDOFF
        or source == "chat2desk_takeover_message"
        or source.startswith("confirmed_operator_outbox:")
        or source.startswith("confirmed_dialog_transferred_after_pending:")
        or source.startswith("tool:")
    )


def is_non_authoritative_control_source(source: str | None) -> bool:
    """Identify takeover rows created by the withdrawn dialog assignment heuristic."""
    return str(source or "").startswith("dialog_transferred:")


def is_human_takeover_message(text: str | None) -> bool:
    """Recognize the official operator greeting that confirms manual control."""
    normalized = normalize_policy_text(text)
    return (
        "buen dia" in normalized
        and "atencion ciudadana" in normalized
        and "le atiende" in normalized
    )


def is_bot_return_message(text: str | None) -> bool:
    """Recognize the official operator macro that explicitly returns control."""
    normalized = normalize_policy_text(text)
    return (
        "gracias por comunicarse" in normalized
        and "atencion ciudadana" in normalized
        and "reiniciar el chatbot" in normalized
        and "sam" in normalized
    )


def should_accept_bot_return_event(
    *,
    message_type: str | None,
    text: str | None,
    stale: bool,
) -> bool:
    """Only a fresh outbound return macro may release current human control."""
    return bool(
        message_type == "to_client"
        and not stale
        and is_bot_return_message(text)
    )


def should_replace_unconfirmed_transfer_response(
    *,
    transfer_attempted: bool,
    transfer_succeeded: bool,
    response: str | None,
) -> bool:
    """Prevent SAM from claiming a transfer that the backend did not complete."""
    if not transfer_attempted or transfer_succeeded:
        return False

    normalized = normalize_policy_text(response)
    transfer_claims = (
        "te transfiero",
        "te transferire",
        "voy a transferirte",
        "te canalizare",
        "voy a canalizarte",
        "hablar con una persona",
        "hablar con un humano",
        "atencion humana",
    )
    return any(claim in normalized for claim in transfer_claims)


def history_after_latest_context_reset(messages, *, uid_prefix: str = "conversation-reset-"):
    """Return only messages belonging to the session after the latest reset marker."""
    items = list(messages or [])
    for index in range(len(items) - 1, -1, -1):
        item = items[index]
        uid = str(
            item.get("uid", "") if isinstance(item, dict) else getattr(item, "uid", "")
        )
        if uid.startswith(uid_prefix):
            return items[index + 1 :], uid
    return items, None


def is_known_automated_outbound(text: str | None) -> bool:
    """Recognize deterministic SAM/system templates even without a provider marker."""
    normalized = normalize_policy_text(text)
    if not normalized:
        return False

    known_templates = (
        (
            "soy sam",
            "asistente virtual de atencion ciudadana",
        ),
        (
            "parece que te ausentaste",
            "conversacion se cerro por inactividad",
        ),
        (
            "reporte",
            "concluido",
            "comentario de conclusion",
            "ubicacion atendida",
        ),
        (
            "le atendio",
            "que tenga un buen dia",
        ),
        (
            "reporte con folio",
            "fue asignado exitosamente",
            "area correspondiente",
        ),
    )
    return any(all(fragment in normalized for fragment in template) for template in known_templates)


def should_confirm_operator_outbox_takeover(
    *,
    message_type: str | None,
    hook_type: str | None,
    operator_id,
    is_bot_echo: bool,
    stale: bool,
    in_return_grace: bool,
) -> bool:
    """Confirm human control only from a fresh, non-bot operator message."""
    return bool(
        message_type == "to_client"
        and hook_type == "outbox"
        and operator_id not in (None, "")
        and not is_bot_echo
        and not stale
        and not in_return_grace
    )


def event_precedes_context_boundary(
    *,
    event_timestamp: float | None,
    boundary_timestamp: float | None,
    tolerance_seconds: float = 1.0,
) -> bool:
    """Reject a delayed webhook whose original event predates a durable reset."""
    if event_timestamp is None or boundary_timestamp is None:
        return False
    try:
        return float(event_timestamp) <= (
            float(boundary_timestamp) + float(tolerance_seconds)
        )
    except (TypeError, ValueError):
        return False


def return_greeting_covers_current_inbound(
    context_reset_marker: str | None,
    messages_after_boundary,
) -> bool:
    """A human-return boundary owns the greeting until a new inbound is stored."""
    if not str(context_reset_marker or "").startswith(
        "conversation-reset-human-return-"
    ):
        return False

    return not any(
        (
            item.get("direction")
            if isinstance(item, dict)
            else getattr(item, "direction", None)
        )
        == "inbound"
        for item in (messages_after_boundary or [])
    )


def inactivity_snapshot_is_still_stale(
    *,
    observed_last_active,
    current_last_active,
    now,
    threshold_seconds: float,
    human_control_active: bool,
) -> bool:
    """Confirm inactivity using the same activity snapshot seen before async work."""
    if human_control_active:
        return False
    if observed_last_active is None or current_last_active is None or now is None:
        return False
    if current_last_active != observed_last_active:
        return False

    try:
        return (now - current_last_active).total_seconds() > float(threshold_seconds)
    except (TypeError, ValueError, AttributeError):
        return False


def should_send_initial_greeting(
    *,
    is_new_request: bool,
    history_available: bool,
    has_prior_conversation_history: bool,
    resetting_after_human: bool,
) -> bool:
    """Send the institutional greeting exactly once at a conversation boundary."""
    if resetting_after_human:
        # The return-to-SAM webhook already sends the institutional greeting.
        return False
    if is_new_request:
        return True
    return history_available and not has_prior_conversation_history


def classify_emergency_answer(body: str | None) -> bool | None:
    """Classify natural Spanish answers to the bot's emergency question."""
    normalized = normalize_policy_text(body)
    if not normalized:
        return None

    negative_patterns = (
        r"^no$",
        r"^negativo$",
        r"\bno\s+es\b.*\bemergencia\b",
        r"\bno\b.*\bemergencia\b",
        r"\bno\b.*\briesgo\s+inmediato\b",
        r"\bno\s+representa\b.*\briesgo\b",
        r"\bno\s+hay\b.*\briesgo\b",
    )
    if any(re.search(pattern, normalized) for pattern in negative_patterns):
        return False

    positive_exact = {
        "si",
        "si es",
        "claro",
        "asi es",
        "correcto",
    }
    if normalized in positive_exact:
        return True

    positive_markers = (
        "es una emergencia",
        "si es emergencia",
        "emergencia porque",
        "emergencia ya que",
        "riesgo inmediato",
        "puede inundar",
        "puede inundarse",
        "puede ocasionar un socavon",
        "puede provocar un socavon",
        "hay riesgo",
    )
    if any(marker in normalized for marker in positive_markers):
        return True

    return None


def is_emergency_related(body: str | None) -> bool:
    normalized = normalize_policy_text(body)
    emergency_markers = (
        "emergencia",
        "riesgo inmediato",
        "fuga de agua",
        "socavon",
        "inundacion",
        "incendio",
        "accidente",
        "persona herida",
        "peligro",
    )
    return any(marker in normalized for marker in emergency_markers)


def reason_claims_missing_context(reason: str | None, reason_code: str | None) -> bool:
    normalized_code = normalize_policy_text(reason_code).replace(" ", "_")
    normalized_reason = normalize_policy_text(reason)
    if not normalized_reason:
        return False

    if normalized_code in {VERIFIED_NO_CONTEXT, TOOL_FAILURE}:
        return True

    missing_context_markers = (
        "sin contexto",
        "no tengo contexto",
        "no cuento con contexto",
        "no tengo informacion",
        "no cuento con informacion",
        "informacion no disponible",
        "fuera de mi conocimiento",
        "fuera de contexto",
        "herramienta fallo",
        "error de herramienta",
        "tool failure",
        "no context",
    )
    return any(marker in normalized_reason for marker in missing_context_markers)


def authorize_transfer(
    *,
    explicit_handoff: bool,
    reason: str | None,
    reason_code: str | None,
    report_intent: bool,
    has_report_session: bool,
    greeting_only: bool,
    emergency_related: bool,
    already_transferred: bool,
) -> tuple[bool, str]:
    """Authorize only explicit handoffs or verified missing-context escalation."""
    if already_transferred:
        return False, "already_transferred"

    if explicit_handoff:
        return True, EXPLICIT_HANDOFF

    normalized_code = normalize_policy_text(reason_code).replace(" ", "_")
    if not reason_claims_missing_context(reason, reason_code):
        return False, "missing_authorized_reason"

    if report_intent or has_report_session:
        return False, "known_report_flow"

    if greeting_only:
        return False, "simple_greeting"

    if emergency_related:
        return False, "known_emergency_flow"

    if normalized_code == TOOL_FAILURE:
        return True, TOOL_FAILURE
    return True, VERIFIED_NO_CONTEXT
