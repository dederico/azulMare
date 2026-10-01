# TDD evidence: semantic human handoff

## Source and user journey

No plan file was supplied. The journey was derived from the production audit:
a citizen can request a person using a standalone control word or natural
language, without repeating a prescribed sentence, and SAM transfers exactly
once before becoming silent.

## RED / GREEN report

| Stage | Command | Result | Evidence |
|---|---|---|---|
| RED | `python -m pytest -q tests/test_conversation_policy.py` | Expected failure | Collection failed because `classify_handoff_signal` did not exist; checkpoint `069a39b`. |
| GREEN (policy) | `python -m pytest -q tests/test_conversation_policy.py` | PASS | 115 tests passed. |
| GREEN (focused integration) | `python -m pytest -q tests/test_conversation_policy.py tests/test_transfer_message_event.py tests/test_circuito_cetis_and_clouthier_routing.py tests/test_catalogo_servicios_municipales.py` | PASS | 127 tests passed. |
| GREEN (regression) | `python -m pytest -q` | PASS | 329 tests passed. |

## Test specification

| # | What is guaranteed | Test target | Type | Result |
|---|---|---|---|---|
| 1 | `AGENTE`, `HUMANO`, `REPRESENTANTE` and `TRANSFERENCIA` are complete handoff requests | `test_standalone_human_control_words_are_complete_requests` | Unit | PASS |
| 2 | Structurally clear requests do not depend on one exact sentence | `test_structural_human_request_does_not_depend_on_an_exact_phrase` | Unit | PASS |
| 3 | A contextual rejection such as `No gracias` is not transferred | `test_contextual_rejection_is_a_deterministic_no` | Unit | PASS |
| 4 | Ambiguous free language is delegated to a closed model decision | `test_free_language_is_delegated_to_semantic_decision` | Unit | PASS |
| 5 | Natural replies to a previous handoff offer are semantically reviewed | `test_contextual_free_language_is_delegated_without_exact_confirmation` | Unit | PASS |
| 6 | A narrative mentioning an unrelated person is not a direct handoff | `test_unrelated_person_narrative_is_not_a_direct_handoff` | Unit | PASS |
| 7 | The model output is restricted to `yes`, `no`, or `unclear` | `test_structured_handoff_decision_has_a_closed_vocabulary` | Unit | PASS |
| 8 | Existing transfer timeout behavior remains pending and terminal | `tests/test_transfer_message_event.py` | Integration | PASS |

## Implementation guarantee

The deterministic policy now owns only high-confidence controls. Ambiguous
language is resolved by the model through `record_handoff_decision`. Both the
direct path and the model tool invoke `execute_human_handoff`, which owns the
`pending_provider -> human_active` provider transition and rollback. A confirmed
or pending transfer is terminal for the SAM turn.

## Coverage and known gaps

The repository does not include `pytest-cov`; the attempted coverage command
was rejected as an unknown argument. Functional evidence is therefore the 329
passing regression tests. A live Chat2Desk canary remains necessary after
deployment to verify provider-side assignment events.
