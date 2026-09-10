# Task ML-01 — storage, providers, execution, ingestion

Base commit: `00fb5e3`
Requested role/model: Worker / `gpt-5.6-luna` / medium (report effective runtime identity)
Owner: Luna worker 1

## Exclusive ownership

Worker may add/edit only:

- `model_lab/storage.py`
- `model_lab/providers/` (all files)
- `model_lab/execution.py`
- `model_lab/ingestion.py`
- `model_lab/budget.py`
- `tests/test_storage_execution.py`
- `tests/test_ingestion_budget.py`
- `docs/handoffs/ML-01.md`

Do not edit schemas, benchmark, isolation, CLI, Memory.md, pyproject, or shared configuration. If a contract gap is discovered, document it in the handoff and use the existing schemas.

## Required behavior

Implement SQLite persistence with immutable raw attempts and durable run/grade/review/provenance/budget records; indexes and duplicate protection are required. Implement provider protocol, deterministic fake variants (correct, incorrect, incomplete, malformed, failure, missing metadata, adversarial), optional live-provider adapter stubs that fail closed without credentials, execution with full/subset selections, retries/cancellation/partial state, provenance, and safe JSONL/CSV structured imports with duplicate/mismatch quarantine. Budget reservations must be atomic and preserve unknown cost/usage as null.

## Targeted validation

Use `python3 -m compileall -q model_lab tests` plus focused tests or stdlib scripts if pytest is unavailable. Include exact commands/results in handoff. Commit all files on the worker branch before completion.

