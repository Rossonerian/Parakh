# PR-02 — evaluation and recommendation integrity

- Base: `27fa8ac8a9bc4bead43fe3e442d5c5b5c9985dbc`.
- Owner: scoped worker; requested `gpt-5.6-luna` / medium; effective identity unknown absent runtime metadata.
- Requirements: Model_Testing_Spec final outcomes, critical failure gates, matched comparisons, honest coverage and draft-only recommendations.
- Exclusive files: `model_lab/grading.py`, `model_lab/analysis.py`, `model_lab/routing.py`, `tests/test_grading_analysis.py`, `tests/test_review_routing.py` (routing tests only), new `tests/test_evaluation_integrity.py`, `docs/handoffs/PR-02.md`.
- Dependencies: read schemas only. Boss may recursively freeze mappings/sequences; use Mapping and list/tuple-compatible operations. No shared schema, pipeline, storage, reporting, review or benchmark edits. Communicate integration contract needs.
- Deliver: strict JSON numeric/type equality and malformed-output grading; every failure grade retains case/model/attempt conditions; truthful paired score availability, duplicate/repeat handling without silent collapse; recommendations fail closed for insufficient or unknown critical/condition/eligibility evidence, and never promote synthetic data. Unknown semantic judgements remain unknown, not successful or invented.
- Acceptance: adversarial regression tests for bool versus numeric, large integers, NaN, failures, missing paired scores, duplicates/repeats, unsupported context and unassessed critical criteria; existing tests updated only for justified stricter contracts.
- Validation: focused grading/analysis/routing tests, exact commands/environment/results. No external API calls.
- Bound: one focused slice; no recursive spawning. Do not approve own changes. Boss serializes shared index/commits; notify when ready so Boss captures durable patch/commit including new files before releasing you. Handoff records files, behavior, evidence, known limitations and recovery procedure.
