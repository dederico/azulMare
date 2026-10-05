# Report description field ownership — TDD evidence

## Source and journey

This fix was derived from CIAC folio `475686`, where the initial explanation
was built with `selection4="Enrique H"` while the structured street was
`Enrique H. Herrera, frente a la Estancia del DIF`.

As a citizen, I want SAM to keep the problem summary separate from the
structured address, so CIAC never receives a street fragment as the report
explanation.

## RED / GREEN evidence

| Guarantee | Test | Type | Result |
|---|---|---|---|
| A street fragment cannot satisfy the `selection4` contract | `test_street_fragment_cannot_be_accepted_as_report_description` | Unit | PASS |
| A description that repeats the structured street is rejected for model repair | `test_description_containing_the_structured_street_is_blocked` | Unit | PASS |
| The final CIAC boundary blocks the contaminated payload before opening HTTP | `test_final_api_boundary_never_posts_location_as_description` | Integration boundary | PASS |
| A clean model summary remains authoritative over raw conversation evidence containing an address | `test_clean_model_summary_wins_over_raw_location_bearing_evidence` | Unit | PASS |
| A contaminated model summary falls back to citizen evidence before final validation | `test_contaminated_model_summary_falls_back_to_citizen_evidence` | Unit | PASS |
| An image/workflow answer cannot become the CIAC explanation | `test_operational_image_reply_cannot_be_report_description` | Unit | PASS |
| A citizen question must be rewritten as a concise problem statement | `test_citizen_question_must_be_rewritten_as_a_problem_statement` | Unit | PASS |

RED command: `PYTHONPATH=. pytest -q tests/test_report_submission_policy.py -k 'street_fragment or structured_street or never_posts_location'`

RED result: `3 failed, 74 deselected`; the boundary attempted to create the
exact malformed explanation observed in folio `475686`.

GREEN focused command: `PYTHONPATH=. pytest -q tests/test_report_submission_policy.py`

GREEN focused result: `81 passed in 0.19s`.

GREEN full-suite command: `PYTHONPATH=. pytest -q`

GREEN full-suite result: `339 passed in 1.49s`.

## Coverage and known gaps

The repository does not have the Python `coverage` package installed, so a
coverage percentage could not be produced. The production Chat2Desk prompt
must still be updated in pgAdmin from the matching rules in `prompty.py` before
the model can perform the instructed one-field retry in production.
