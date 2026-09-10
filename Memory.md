# ModelLab implementation memory

Updated UTC: 2026-09-10
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

## Agent allocation

- Boss: architecture, shared contracts, integration, canonical `Memory.md`, acceptance.
- Supervisor: read-only independent review after integration; requested model `gpt-5.6-terra`, medium.
- Workers: three disjoint slices; requested model `gpt-5.6-luna`, medium. Effective runtime identity must be reported from tool metadata, not prose.

## Next actions

1. Create a local baseline commit for the specification plus foundation so worker worktrees are recoverable.
2. Release disjoint storage/execution, grading/analysis, and reporting/Promptfoo task cards.
3. Integrate, expand CLI, run the complete offline 60-case workflow, and obtain Supervisor review.

