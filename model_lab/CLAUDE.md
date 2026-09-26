# ModelLab package map

Loads when a file under `model_lab/` is read. Root `CLAUDE.md` covers commands
and repo-wide rules; this file is package-local detail only.

## Modules (one import path per symbol — there are no shims or facades)

| Module | Owns |
| --- | --- |
| `cli/commands.py` | argparse surface; every subcommand branch in `main()` |
| `pipeline.py` | end-to-end offline demo (`run_offline_demo`) |
| `application/execution.py` | `ExecutionEngine`: bounded dispatch, retries, attempt persistence, budget settle |
| `application/reporting.py` | `build_report`, `render_*`, `write_report_bundle` (escaped CSV/MD/HTML) |
| `domain/isolation.py` | `CandidateInput`, `candidate_input`, `AuthorizedLiveExecution` capability |
| `domain/budget.py` | `BudgetLedger` reserve/settle over the store |
| `storage/sqlite.py` | `SQLiteStore`: runs, append-only attempts, reviews, atomic reservations |
| `providers/base.py` · `fake.py` · `live.py` | provider protocol · deterministic test provider · gated HTTP adapters |
| `schemas.py` | frozen record types (`Case`, `Attempt`, `Grade`, `Run`, …), hashing helpers |
| `errors.py` | all exceptions (`ModelLabError` family incl. `PilotBlockedError`) |
| `benchmark.py` | suite load/validate/select, candidate-only export |
| `grading.py` · `analysis.py` · `routing.py` | graders · matched-case comparison · draft-only recommendations |
| `review.py` | blind review export/import with bound labels |
| `ingestion.py` · `promptfoo.py` | external result import with quarantine · Promptfoo fixture boundary |
| `pilot.py` · `operator_input.py` · `constraints.py` | live-pilot plan/authorization · operator YAML → immutable plan · constraint map |
| `post_pilot.py` | post-pilot gates: cost reconciliation, holdout, calibration, shadow replay |

## Dependency direction

`cli` → `pipeline`/`pilot`/feature modules → `application` → `domain` →
`storage`/`providers` → `schemas`/`errors`. Lower layers never import upward:
`schemas`, `errors`, `storage`, `providers`, `domain` must not import `cli`,
`pipeline`, `pilot` or `application`. `providers/live.py` is imported only
function-locally in `pilot._provider_for` so offline paths never load it.

## Safety invariants — do not weaken without an explicit task

| Invariant | Enforced in | Covered by |
| --- | --- | --- |
| Candidate provider input structurally cannot see oracle/reference answers | `domain/isolation.py` | `tests/test_benchmark_and_isolation.py` |
| Paid/live dispatch requires a frozen, hash-verified plan + `--allow-paid` | `pilot.py` | `tests/test_constraints_and_pilot_cli.py`, `tests/test_promptfoo_authorization.py` |
| Budget reservations are atomic (thread lock + immediate SQLite transaction) | `storage/sqlite.py`, `domain/budget.py` | `tests/test_settlement_concurrency.py` |
| Raw attempt evidence has no update/delete path | `storage/sqlite.py` | `tests/test_storage_execution.py` |
| CSV (headers and cells)/HTML/Markdown output is escaped against formula/script injection | `application/reporting.py` | `tests/test_report_integrity.py` |
| Costs in different or unknown currencies are never summed | `application/reporting.py`, `post_pilot.py` | `tests/test_report_integrity.py`, `tests/test_post_pilot.py` |
| Blind review import requires exact `expected_labels` bindings | `review.py` | `tests/test_review_integrity.py` |
| Holdout case set is consumed exactly once (`O_CREAT\|O_EXCL`) | `post_pilot.py` | `tests/test_post_pilot.py` |
| Router only ever drafts recommendations, never writes them | `routing.py`, `post_pilot.py` | `tests/test_post_pilot.py` |

## Extending

- New subcommand: parser + branch in `cli/commands.py`, logic in the owning
  module above, a `main([...])` test in `tests/test_cli_surface.py`.
- New provider: implement `providers/base.py`'s protocol; tests use
  `providers/fake.py`, never `live.py`.
- Every CLI subcommand needs at least one `main([...])` test — `model-lab run`
  shipped broken because none existed.
