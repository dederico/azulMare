import re
import unicodedata


EXPLICIT_HANDOFF = "explicit_user_request"
VERIFIED_NO_CONTEXT = "verified_no_context"
TOOL_FAILURE = "tool_failure"


def normalize_policy_text(value: str | None) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = re.sub(r"[^a-zA-Z0-9\s]", " ", text.lower())
    return " ".join(text.split())


def should_activate_human_control(
    *,
    message_type: str | None,
    hook_type: str | None,
    operator_id,
    is_bot_echo: bool,
    recently_returned_to_bot: bool,
    event_is_stale: bool = False,
    authoritative_assignment: bool = False,
) -> bool:
    """Activate control only from Chat2Desk's authoritative assignment event."""
    try:
        has_operator = bool(operator_id) and int(operator_id) > 0
    except (TypeError, ValueError):
        has_operator = False

    return (
        authoritative_assignment
        and hook_type == "dialog_transferred"
        and has_operator
        and not is_bot_echo
        and not recently_returned_to_bot
        and not event_is_stale
    )


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
