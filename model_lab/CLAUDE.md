# ModelLab package map

Loads automatically when Claude reads a file under `model_lab/`. Root
`CLAUDE.md` already covers commands and repo-wide rules — this file is
package-local detail only.

## Layering (partially migrated, both forms are current)

```
cli/            → argparse surface, output formatting (model_lab/cli/commands.py)
application/     → orchestration: execution.py (run engine), reporting.py (report views)
domain/          → contracts: budget.py (ledger), isolation.py (candidate-safety), models.py
storage/         → sqlite.py: persistence + atomic budget reservation
providers/       → base.py (protocol), fake.py (tests), live.py (real HTTP, gated)
```

Everything else (`grading.py`, `analysis.py`, `routing.py`, `benchmark.py`,
`ingestion.py`, `pilot.py`, `operator_input.py`, `promptfoo.py`, `post_pilot.py`,
`review.py`, `constraints.py`, `schemas.py`, `errors.py`) is flat at the
package root and **is the real implementation**, not legacy code.

`model_lab/reporting.py`, `isolation.py`, `execution.py`, `budget.py` at the
package root are **intentional compatibility shims** re-exporting the
`application`/`domain` versions (see each file's docstring). They are
actively imported by the CLI and by tests — do not delete them, and do not
"finish" the migration by moving everything into `application`/`domain`
unless a task explicitly asks for that (it's a real but low-value, high-diff
refactor; the current split has not caused a bug in the audit history).

## Safety invariants — do not weaken without an explicit task

These are enforced in code and covered by tests; treat them as contracts,
not suggestions.

| Invariant | Enforced in | Covered by |
| --- | --- | --- |
| Candidate provider input structurally cannot see oracle/reference answers | `domain/isolation.py` | `tests/test_benchmark_and_isolation.py` |
| Paid/live dispatch requires a frozen, hash-verified plan + `--allow-paid` | `pilot.py` | `tests/test_constraints_and_pilot_cli.py`, `tests/test_promptfoo_authorization.py` |
| Budget reservations are atomic (thread lock + immediate SQLite transaction) | `storage/sqlite.py`, `domain/budget.py` | `tests/test_settlement_concurrency.py` |
| Raw attempt evidence has no update/delete path | `storage/sqlite.py` | `tests/test_storage_execution.py` |
| CSV/HTML/Markdown report output is escaped against formula/script injection | `application/reporting.py` | `tests/test_report_integrity.py` |
| Blind review import requires exact `expected_labels` bindings (no unbound trust) | `review.py` | `tests/test_review_integrity.py` |
| Holdout case set is consumed exactly once (`O_CREAT|O_EXCL`) | `post_pilot.py` | `tests/test_post_pilot.py` |
| Router only ever drafts recommendations, never writes them | `routing.py`, `post_pilot.py` | `tests/test_post_pilot.py` |

## Local commands

```
.venv/bin/python -m pytest -q tests/test_<area>.py    # one file, fast loop
.venv/bin/python -m model_lab doctor                   # environment sanity check
.venv/bin/python -m model_lab suite validate benchmarks/seed_cases.jsonl
```

## When extending the CLI

Add subcommands in `cli/commands.py`, orchestration in `application/`, and
new domain rules in `domain/`. Keep provider access behind `providers/base.py`'s
protocol so `fake.py` stays a drop-in for tests — never call `live.py` from
a test.
