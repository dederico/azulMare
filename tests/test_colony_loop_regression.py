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
    extract_explicit_report_image_decision,
    extract_pending_report_answers,
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
    assert '"pending_intake_question"\n                            ] = "emergency"' in source
