# PR-01 — provider boundary hardening

- Base: `27fa8ac8a9bc4bead43fe3e442d5c5b5c9985dbc` (ModelLab release).
- Owner: scoped worker; requested `gpt-5.6-luna` / medium. Effective identity must come from runtime metadata, otherwise unknown.
- Requirements: Model_Testing_Spec provider provenance, bounded execution, no unauthorized outbound activity; Rules security/financial gates.
- Exclusive files: `model_lab/providers/live.py`, `model_lab/providers/base.py`, `tests/test_live_providers.py`, new `tests/test_provider_safety.py`, `docs/handoffs/PR-01.md`.
- Dependencies: read other modules only. Coordinate any public provider contract changes with Boss. No schema, lockfile, CLI, budget, execution or benchmark edits.
- Deliver: endpoint/redirect credential safety, bounded response/timeouts, protected payload identity and parameters, accurate usage/request/model provenance, classified retryable failures, rigorous malformed numeric response checks. Keep explicitly configured local Ollama supported. No live network/API calls.
- Acceptance: targeted mocked tests prove rejected unsafe endpoints/redirects/overrides and preserve correct provider configuration/output; no fabricated costs or observations. Report unresolved context/model revision constraints to Boss.
- Validation: existing provider tests plus adversarial mocked transport tests; record commands/results and environment.
- Bound: one focused implementation slice; no recursive spawning. Preserve code in a durable Git commit or patch including new files before release. Boss serializes shared index/commits; request Boss to capture patch when ready. Handoff includes exact candidate evidence, known limitations and recovery procedure. Worker cannot approve own changes.
