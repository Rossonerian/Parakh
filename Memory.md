# ModelLab implementation memory

Updated UTC: 2026-09-11
Branch: main (no baseline commit existed at intake)

## Verified intake

- Repository contained only specification files, benchmark seed data, and Codex examples; no source, tests, Python configuration, or Git commits existed.
- Present authority read: `AGENTS.md`, `Rules.md`, `Architecture.md`, `Phases.md`, `Model_Testing_Spec.md`, `Testing_Lab_Prompt.md`, `Acceptance_Testing.md`, `benchmarks/README.md`, `benchmarks/seed_cases.jsonl`, `Agent_Team.md`.
- Referenced `README.md`, `PRD.md`, `Design.md`, and `Tier_Entitlements.md` are absent; this is recorded as a documentation limitation, not filled with invented requirements.
- Python 3.12.3 is available as `python3`; `python` is not installed. Runtime dependencies are intentionally standard-library-only; pytest is a development extra.

## Current implementation

- Canonical dataclass contracts and validation are implemented in `model_lab/schemas.py`.
- Seed benchmark JSONL loading, shape validation, selection, hashing, and candidate export are in `model_lab/benchmark.py`.
- Structural candidate isolation is in `model_lab/isolation.py`; candidate payloads exclude evaluation data, split/family metadata, and annotations.
- Dependency-free CLI currently supports `suite validate`, `suite inspect`, and protected candidate-only export.
- Integrated storage, deterministic fake providers, execution/retry/cancellation/budget handling, structured ingestion, deterministic grading, blind review, matched comparison/regression, escaped reports/charts, Promptfoo fixture reconciliation, draft routing evidence, and optional fail-closed Ollama/OpenRouter HTTP adapters.
- CLI now includes `init`, `doctor`, `plan`, `demo`, `run`, `import`, `grade`, `review export/import`, persisted-run `compare`, persisted-run `report`, persisted-run `audit`, `promptfoo export/import`, and `router recommend --draft`; Makefile release/dev targets are documented.
- Controlled live-pilot preparation is in `model_lab/pilot.py` and `docs/live_pilots/`: plans select exactly the 36 `train`/development cases, freeze execution fields, require operator candidates/pricing/spend authorization, and fail closed before paid dispatch.
- Product-source intake is tracked in `docs/product_sources/SOURCE_MANIFEST.json`; actual PRD, Design, and Tier Entitlements files were not found and were not fabricated. Router constraint mapping is explicitly partial in `docs/live_pilots/router-constraint-map-v0.1.0.md`.

## Verified evidence

- Clean editable install: `python3 -m venv .venv` and `.venv/bin/python -m pip install -e '.[dev]'` passed.
- `make PYTHON=.venv/bin/python test-release`: doctor passed; 31 pytest tests passed; offline E2E passed.
- Full offline demo with seed 0.1.0 and seeds 29/37: 60 cases validated, 60 attempts per synthetic candidate, non-null good-vs-incorrect delta 1.0, JSON/CSV/Markdown/HTML/SVG artifacts, accepted Promptfoo fixture, tampered fixture quarantined, router draft left production config unchanged.
- Repeated deterministic demo with the same seed produced identical stable good/bad digests and suite hash.
- Two consecutive `make PYTHON=.venv/bin/python dev` runs passed using distinct disposable `lab-data/dev.XXXXXX` directories.
- `pilot show docs/live_pilots/plan-v0.1.0.json` exited 2 with the expected blockers; `pilot run --allow-paid` exited 2 without dispatching a provider call.
- Final `git diff --check` passed and final `git status --short --branch` was clean on `main` at `48fbf74`.

## Review/blockers

- Three worker handoffs were durably committed and integrated: ML-01 `0e784a2`, ML-03 `126ffe8`, ML-02 `e4b1853` (requested Luna/medium; effective worker model metadata unavailable).
- The first requested Terra/medium read-only Supervisor attempt hit a usage-limit error. A retry on the exact corrected tree returned `APPROVED`; requested model was Terra/medium, but effective runtime model identity remained unknown.
- The repository references `PRD.md`, `Design.md`, and `Tier_Entitlements.md`, but those files were absent at intake. No requirements were invented for them.
- No paid provider calls, live customer data, production deployment, migrations, charges, or outbound messages were performed.

## Agent allocation

- Boss: architecture, shared contracts, integration, canonical `Memory.md`, acceptance.
- Supervisor: read-only independent review after integration; requested model `gpt-5.6-terra`, medium.
- Workers: three disjoint slices; requested model `gpt-5.6-luna`, medium. Effective runtime identity must be reported from tool metadata, not prose.

## Next actions

1. Operator supplies the actual PRD, Design, and Tier Entitlements documents plus revision/hash metadata for import under `docs/product_sources/`.
2. Operator supplies explicit candidate `provider:model[:revision]` values, pricing snapshot, currency, repeats, and approved maximum spend; regenerate and display the pilot plan before authorization.
3. After the pilot, reconcile usage/cost, grade outputs, blind-review a stratified calibration sample, and keep calibration/holdout frozen until policy candidates are locked.
