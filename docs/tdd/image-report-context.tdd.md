# Image report context — TDD evidence

## Source and journey

This fix was derived from the production conversation in which SAM asked for
an image for an active municipal report, then treated the received image as an
unrelated consultation and asked the citizen to resend it.

As a citizen, I want an image sent for my current report to be retained and
attached exactly once, even when another worker has not restored report intent,
so I never have to resend it or restart the report.

## RED / GREEN evidence

| Guarantee | Test | Type | Result |
|---|---|---|---|
| The model can classify image purpose from recent conversation | `test_model_resolves_image_as_part_of_current_report` | Unit | PASS |
| A model failure leaves the image safely pending | `test_model_failure_keeps_image_context_unresolved` | Unit | PASS |
| A delivered report-image prompt routes the next image to that report | `test_report_image_prompt_is_authoritative_for_next_image` | Unit | PASS |
| Semantic context can recover missing replica-local state | `test_semantic_report_decision_can_recover_missing_local_state` | Unit | PASS |
| Pending images are deduplicated and promoted without resend | `test_pending_image_is_deduplicated_and_promoted_without_resend` | Unit | PASS |
| Pending media state survives a worker hop without opening a CIAC report | `test_unconfirmed_pending_image_context_survives_worker_hop` | Unit | PASS |

RED command: `python -m pytest -q tests/test_image_analysis.py`

RED result: collection failed because the new image-context functions did not
exist yet.

GREEN command: `python -m pytest -q`

GREEN result: `322 passed in 1.28s`.

## Coverage and known gaps

The repository does not have the Python `coverage` package installed, so a
coverage percentage could not be produced. The focused module suite contains
11 passing tests. The full existing suite also passes. A live Chat2Desk test
must be run after deployment because provider delivery and worker switching are
external integrations.
