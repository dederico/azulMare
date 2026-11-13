from pathlib import Path

from app.services.conversation_policy import (
    classify_handoff_signal,
    classify_post_folio_continuity,
    consume_report_prompt_attempt,
    should_suppress_repeated_report_question,
)
from app.services.report_completion import (
    append_report_completion_followup,
    clear_report_completion,
    get_recent_report_completion,
    record_report_completion,
)
from app.services.report_submission_policy import (
    apply_report_field_update,
    captured_report_question_field,
    determine_report_progress,
    extract_pending_report_answers,
)


def test_lety_report_does_not_reopen_or_forget_location_and_images():
    phone = "5218110777248"
    fields = {
        "selection1": "624",
        "selection2": "Lety Maldonado",
        "selection3": "",
        "selection4": (
            "Tres camiones de transporte de personal obstruyen un "
            "exclusivo residencial"
        ),
        "selection5": "Lázaro Cárdenas",
        "selection6": "2",
        "selection7": "Villas de Santa Engracia",
    }
    images = [
        "https://storage.chat2desk.com.mx/reporte-lety-1.jpg",
        "https://storage.chat2desk.com.mx/reporte-lety-2.jpg",
    ]

    # The exact frustration/duplicate turns from the incident cannot replace
    # already captured location fields.
    for pending_field, citizen_message in (
        ("selection6", "2"),
        ("selection5", "Ya te la puse"),
        ("selection7", "¿Cuántas más veces?"),
        ("selection5", "Estás en un loop"),
    ):
        assert extract_pending_report_answers(
            pending_field,
            citizen_message,
            existing_fields=fields,
        ) == {}

    mutable_fields = dict(fields)
    accepted, kept_value = apply_report_field_update(
        mutable_fields,
        "selection6",
        "¿Cuántas más veces?",
    )
    assert not accepted
    assert kept_value == "2"
    assert mutable_fields["selection6"] == "2"

    # A stored value changes only through the explicit correction path.
    accepted, corrected_value = apply_report_field_update(
        mutable_fields,
        "selection6",
        "22",
        allow_overwrite=True,
    )
    assert accepted
    assert corrected_value == "22"
    assert mutable_fields["selection6"] == "22"

    completion = record_report_completion(
        None,
        phone,
        "482932",
        now=100,
        report_snapshot={**fields, "images": images},
    )
    assert completion["report_snapshot"]["selection5"] == "Lázaro Cárdenas"
    assert completion["report_snapshot"]["selection6"] == "2"
    assert completion["report_snapshot"]["image_count"] == 2
    assert "images" not in completion["report_snapshot"]
    assert "selection2" not in completion["report_snapshot"]

    stored = get_recent_report_completion(
        None,
        phone,
        max_age_seconds=300,
        now=120,
    )
    assert classify_post_folio_continuity(
        "Quiero que se los lleve la grúa. El policía está viendo si es multa.",
        stored,
    ) == "same_incident"
    assert append_report_completion_followup(
        None,
        phone,
        "Quiero que se los lleve la grúa.",
        now=121,
    )
    stored = get_recent_report_completion(
        None,
        phone,
        max_age_seconds=300,
        now=122,
    )
    assert stored["report_snapshot"]["followup_count"] == 1
    assert "followups" not in stored["report_snapshot"]
    assert determine_report_progress(
        fields,
        declared_emergency=False,
        image_prompted=False,
        image_decision=None,
        has_images=False,
        incident_snapshot=stored["report_snapshot"],
    ).action == "continue"
    for repeated_question in (
        "¿Cuál es la calle exacta donde se encuentran?",
        "¿Cuál es el número exterior?",
        "¿En qué colonia se encuentra el problema?",
    ):
        assert captured_report_question_field(
            repeated_question,
            fields,
        ) is not None

    question = "¿Cuál es el número exterior?"
    prompt_session = {}
    assert consume_report_prompt_attempt(prompt_session, "ask_field:selection6")
    assert consume_report_prompt_attempt(prompt_session, "ask_field:selection6")
    assert not consume_report_prompt_attempt(prompt_session, "ask_field:selection6")
    assert not should_suppress_repeated_report_question(
        question,
        question,
        report_progress_made=False,
        repeated_count=0,
    )
    assert should_suppress_repeated_report_question(
        question,
        question,
        report_progress_made=False,
        repeated_count=1,
    )
    assert classify_handoff_signal("Quiero reportarte a ti", question) == "yes"
    assert classify_handoff_signal("Estás en un loop", question) == "yes"

    clear_report_completion(None, phone)


def test_original_route_wires_all_lety_loop_guards():
    """Keep the service-level guards connected to the production webhook."""
    source = Path("app/api/original_routes.py").read_text(encoding="utf-8")

    for production_call in (
        "apply_report_field_update(",
        "allow_overwrite=True",
        "consume_report_prompt_attempt(",
        "classify_post_folio_continuity(",
        "append_report_completion_followup(",
        'progress.action == "continue"',
        "captured_report_question_field(",
    ):
        assert production_call in source

    webhook_source = source[source.index("async def _process_whatsapp_request") :]
    assert webhook_source.index("last_outbound_message = next(") < (
        webhook_source.index("classify_post_folio_continuity(")
    )
