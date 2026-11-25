from pathlib import Path

from app.services.conversation_policy import (
    should_enter_legacy_report_finalization,
)
from app.services.report_intake_policy import (
    extract_catalog_location,
    extract_initial_report_bundle,
)
from app.services.report_submission_policy import (
    canonical_report_location_value,
    captured_report_question_field,
    extract_explicit_report_image_decision,
    extract_pending_report_answers,
    next_missing_report_field,
)


def test_lucero_colony_answers_resolve_without_reprompting():
    expected = {
        "En el casco de San Pedro": "Casco",
        "En el centro de San Pedro": "San Pedro Garza Garcia Centro",
        "En en CASCO": "Casco",
    }

    for answer, canonical in expected.items():
        assert canonical_report_location_value("selection7", answer) == canonical
        assert extract_pending_report_answers("selection7", answer) == {
            "selection7": canonical,
        }


def test_chipinque_public_name_maps_to_official_ciac_catalog_value():
    for answer in (
        "Residencial Chipinque",
        "Fraccionamiento Residencial Chipinque",
        "Colonia Residencial Chipinque",
        "Zona Residencial Chipinque",
    ):
        assert extract_catalog_location(
            answer,
            {},
            expected_field="selection7",
        ) == {"selection7": "Zona Residencia Chipinque"}


def test_industrial_public_name_maps_to_official_ciac_catalog_value():
    expected = {"selection7": "Zona Industrial"}

    for answer in (
        "Industrial",
        "Colonia Industrial",
        "Zona Industrial",
        "Zona Indusrial",
    ):
        assert extract_catalog_location(
            answer,
            {},
            expected_field="selection7",
        ) == expected
        assert extract_pending_report_answers("selection7", answer) == expected


def test_industrial_full_report_captures_colony_without_reprompting():
    message = (
        "Hola! Quiero reportar multiples señalamientos viales vandalizados "
        "con grafiti y solicitar su reparación y limpieza. Ubicados en "
        "banqueta pegada a rieles de tren en Avenida Diaz Ordaz #sin numero "
        "entre Dattile y calle Zinc, Colonia Industrial. No es una emergencia."
    )

    fields, _ = extract_initial_report_bundle(message, {})

    assert fields["selection6"] == "0000"
    assert fields["selection7"] == "Zona Industrial"


def test_quoted_number_and_colony_complete_multiturn_location_without_reprompting():
    selections = {
        "selection1": "984",
        "selection4": "Hay un bache que obstruye la circulación",
        "selection5": "Vasconcelos",
    }

    assert next_missing_report_field(selections)[0] == "selection6"

    number_reply = (
        "« ¿Cuál es el número exterior? Si no existe o no lo conoces, "
        "indícame ‘sin número’. »\n"
        "Te estoy diciendo que es el cruce con"
    )
    selections.update(
        extract_pending_report_answers(
            "selection6",
            number_reply,
            existing_fields=selections,
        )
    )

    assert selections["selection6"] == "0000"
    assert next_missing_report_field(selections)[0] == "selection7"

    colony_reply = (
        "« ¿En qué colonia se encuentra el problema? »\n"
        "En la colonia Centro"
    )
    selections.update(
        extract_pending_report_answers(
            "selection7",
            colony_reply,
            existing_fields=selections,
        )
    )

    assert selections["selection7"] == "Centro"
    assert next_missing_report_field(selections) is None
    assert captured_report_question_field(
        "¿Cuál es el número exterior?",
        selections,
    ) == "selection6"
    assert captured_report_question_field(
        "¿En qué colonia se encuentra el problema?",
        selections,
    ) == "selection7"


def test_approximate_colony_guard_still_rejects_unrelated_text():
    for answer in (
        "Springfield",
        "Zona comercial inventada",
        "Industrialización del país",
    ):
        assert canonical_report_location_value("selection7", answer) is None
        assert extract_pending_report_answers("selection7", answer) == {}


def test_loujay_full_address_ignores_postal_code_and_captures_all_fields():
    message = (
        "El número exterior más cercano y su calle es: Av. Roberto Garza "
        "Sada 900, Zona Residencial Chipinque, 66254 San Pedro Garza "
        "García, N.L. (Torres Planetario)"
    )

    assert extract_catalog_location(
        message,
        {},
        expected_field="selection7",
    ) == {
        "selection5": "Roberto Garza Sada",
        "selection6": "900",
        "selection7": "Zona Residencia Chipinque",
    }


def test_alma_problem_sentence_cannot_pollute_street_field():
    assert extract_pending_report_answers(
        "selection5",
        "Reportar un tope que nos quitaron. Se encontraba en Roberto Garza "
        "Sada, Residencial Chipinque",
    ) == {
        "selection5": "Roberto Garza Sada",
        "selection7": "Zona Residencia Chipinque",
    }


def test_all_in_one_report_captures_every_fact_and_no_image_choice():
    message = (
        "Quiero reportar un bache, en Vasconcelos 333 Colonia Centro "
        "sin imagen"
    )

    fields, _ = extract_initial_report_bundle(message, {})
    assert fields == {
        "selection4": "un bache",
        "selection5": "Vasconcelos",
        "selection6": "333",
        "selection7": "Centro",
    }
    assert extract_explicit_report_image_decision(message) == "no"


def test_pending_field_never_bypasses_loop_guards_via_legacy_finalization():
    assert not should_enter_legacy_report_finalization(
        explicit_finalization=False,
        pending_field="selection7",
        image_decision=None,
    )

    source = Path("app/api/original_routes.py").read_text(encoding="utf-8")
    assert "[REPORT FINALIZATION QUEUE COALESCED]" in source
    normalized_body_start = source.rindex(
        "# Extraer información del payload de Chat2Desk"
    )
    normalized_body_stage = source[
        normalized_body_start:
        source.index(
            "# Get recent AI messages for this number",
            normalized_body_start,
        )
    ]
    assert "body = effective_inbound_text" in normalized_body_stage
    assert "payload.get('text'" not in normalized_body_stage
    assert '"pending_intake_question"\n                            ] = "emergency"' in source
