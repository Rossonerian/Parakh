# Task ML-03 — reporting, charts, Promptfoo adapter

Base commit: `00fb5e3`
Requested role/model: Worker / `gpt-5.6-luna` / medium (report effective runtime identity)
Owner: Luna worker 3

## Exclusive ownership

Worker may add/edit only:

- `model_lab/reporting.py`
- `model_lab/promptfoo.py`
- `tests/test_reporting_promptfoo.py`
- `docs/handoffs/ML-03.md`

Do not edit schemas, benchmark, isolation, CLI, storage, providers, execution, grading, analysis, routing, pyproject, or Memory.md. Integrate around existing contracts; list any contract gap instead of editing shared files.

## Required behavior

Implement deterministic JSON/CSV/Markdown/escaped standalone HTML reports, static SVG/PNG charts without optional hard dependencies (or clearly labeled skipped chart artifacts), unknown-metric/coverage/provenance sections, CSV/formula injection protection, candidate-only Promptfoo manifest export with prompt hashes and protected-field exclusion, versioned fixture artifact import/quarantine, tamper detection, and a fail-closed live invocation boundary.

## Targeted validation

Use `python3 -m compileall -q model_lab tests` plus focused tests or stdlib scripts if pytest is unavailable. Include exact commands/results in handoff. Commit all files on the worker branch before completion.

