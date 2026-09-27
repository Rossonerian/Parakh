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
| `application/events.py` | `record_event` → append-only `run_events` (redacted, bounded text) |
| `application/observability.py` | read model: `load_snapshot`, `summarize_run`, `run_results`, `case_views` (no oracle data) |
| `application/lab_actions.py` | offline operator actions (demo, fake run, grade, validate, doctor, import, compare, pilot preflight) |
| `tui/` | Textual console: `app.py` (threads, polling, actions), `views.py` (one widget per tab), `state.py`, `formatting.py` |
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
| `cli/optimization.py` | Offline telemetry/curation/rewards/router/harness/verifier/policy/artifact operator subcommands; argparse extension of the existing CLI |
| `telemetry/` · `datasets.py` | Sanitized batch validation/privacy/quarantine/novelty; frozen core and lineage-aware train/validation/sealed holdout |
| `storage/evidence.py` · `schema_registry.py` | Append-only optimization records and explicit audited state transitions; stable schema versions |
| `rewards/` · `preferences/` | Versioned component rewards; correction classification, human review and gated preference export |
| `optimization/router/` · `optimization/harness/` | Logged-propensity datasets, LinUCB/OPE/replay; immutable prompt candidates and simulated optimizer |
| `verifier.py` · `artifacts/` | Hard-gate decisions, reproducibility, tier budgets; read-only checksummed and Ed25519-signed PolicyBundleV1 |
| `application/optimization_console.py` · `application/optimization_report.py` | Read-only operator projections, audited review, escaped Evidence/Analysis/Decision report |

## Dependency direction

`cli`/`tui` → `application/lab_actions` → `pipeline`/`pilot`/feature modules → `application` → `domain` →
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
| Run events are append-only and credential-redacted before storage | `storage/sqlite.py`, `application/events.py` | `tests/test_observability_events.py` |
| The TUI has no paid/live dispatch path (preflight uses `allow_paid=False`) | `application/lab_actions.py`, `tui/app.py` | `tests/test_tui_console.py` |
| Telemetry remains quarantined until named, reasoned promotion; no core benchmark mutation | `telemetry/`, `datasets.py`, `storage/evidence.py` | `tests/test_telemetry_import.py`, `tests/test_telemetry_curation.py`, `tests/test_flywheel.py` |
| Unsupported OPE, dirty provenance, unknown budgets or unreviewed rubric holdout fail closed | `verifier.py` | `tests/test_ope_gates.py`, `tests/test_flywheel.py` |
| Bundle import never activates a production policy; signing keys stay outside the repository | `artifacts/`, `contracts/karmi_reference/loader.py` | `tests/test_optimization_foundation.py`, `tests/test_flywheel.py` |
| Optimization HTML/Markdown escapes untrusted gate/telemetry text | `application/optimization_report.py` | `tests/test_optimization_report.py` |

## Extending

- New subcommand: parser + branch in `cli/commands.py`, logic in the owning
  module above, a `main([...])` test in `tests/test_cli_surface.py`.
- New provider: implement `providers/base.py`'s protocol; tests use
  `providers/fake.py`, never `live.py`.
- Every CLI subcommand needs at least one `main([...])` test — `model-lab run`
  shipped broken because none existed.
