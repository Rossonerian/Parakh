# ModelLab / Parakh — Audit Findings

Record of findings identified during Phase A through Phase F of the audit plan.
All findings use the standardized block format:

```markdown
### [ID] <one-line title>
- Severity: S1|S2|S3|S4
- Phase/Step: <PhaseStep>
- Evidence: <exact file path(s) and line numbers, or the pasted command + output>
- Reproduction: <exact command a human can re-run>
- Impact: <what breaks, in one sentence>
- Proposed fix: <smallest change that resolves it>
- Fix risk: <what the fix could break>
- Status: OPEN | FIXED (commit <sha>) | WONTFIX (<reason>) | NEEDS-OWNER-DECISION
```

---

## Findings Log

### [B-01] Module shadowing: model_lab/cli.py shadowed by package model_lab/cli/
- Severity: S1
- Phase/Step: B1
- Evidence: `model_lab/cli.py` (426 lines) contains a duplicate CLI implementation of `model_lab/cli/commands.py`. When `import model_lab.cli` is executed, Python resolves `model_lab/cli/__init__.py`. Running `.venv-audit/bin/python -c "import model_lab.cli as m; print(m.__file__)"` prints `/home/rosso/Projects/Parakh/model_lab/cli/__init__.py`.
- Reproduction: `.venv-audit/bin/python -c "import model_lab.cli as m; print(m.__file__)"`
- Impact: `model_lab/cli.py` is completely unreachable dead code that can drift from `model_lab/cli/commands.py`.
- Proposed fix: Remove unreachable `model_lab/cli.py` since `model_lab/cli/` is the canonical package.
- Fix risk: Low; any file importing `model_lab.cli` already resolves the package.
- Status: FIXED (commit 90e24ec)

### [B-02] Module shadowing: model_lab/storage.py shadowed by package model_lab/storage/
- Severity: S1
- Phase/Step: B1
- Evidence: `model_lab/storage.py` (212 lines) contains a duplicate implementation of `model_lab/storage/sqlite.py`. When `import model_lab.storage` is executed, Python resolves `model_lab/storage/__init__.py`. Running `.venv-audit/bin/python -c "import model_lab.storage as m; print(m.__file__)"` prints `/home/rosso/Projects/Parakh/model_lab/storage/__init__.py`.
- Reproduction: `.venv-audit/bin/python -c "import model_lab.storage as m; print(m.__file__)"`
- Impact: `model_lab/storage.py` is completely unreachable dead code that can drift from `model_lab/storage/sqlite.py`.
- Proposed fix: Remove unreachable `model_lab/storage.py` since `model_lab/storage/` is the canonical package.
- Fix risk: Low; any file importing `model_lab.storage` already resolves the package.
- Status: FIXED (commit a29bafa)

### [B-03] Shim vs implementation duplicate logic in root model_lab/*.py
- Severity: S2
- Phase/Step: B3
- Evidence: `README.md` lines 22-23 claim that `model_lab/*.py` files are compatibility shims. In reality, `model_lab/budget.py` (41 lines), `model_lab/execution.py` (128 lines), `model_lab/isolation.py` (90 lines), and `model_lab/reporting.py` (242 lines) duplicate implementation logic from `model_lab/domain/` and `model_lab/application/` rather than being pure re-export shims.
- Reproduction: `diff -u model_lab/budget.py model_lab/domain/budget.py`
- Impact: Code duplication creates a high risk of divergence where bugfixes applied to one file are not reflected in the duplicate file.
- Proposed fix: Convert `model_lab/{budget,execution,isolation,reporting}.py` to pure re-export compatibility shims importing from their canonical layered modules.
- Fix risk: Low, provided all public symbols and `__all__` remain exported.
- Status: FIXED (commit 849fc64)

### [B-04] Directory case collision: .jules and .Jules tracked in git
- Severity: S4
- Phase/Step: B4
- Evidence: `git ls-files --stage .jules .Jules` reveals `100644 ... .Jules/palette.md` and `100644 ... .jules/bolt.md`.
- Reproduction: `git ls-files | grep -i '^\.jules/'`
- Impact: On case-insensitive filesystems (macOS, Windows), checking out the repository causes directory collision and potential checkout corruption or file loss.
- Proposed fix: Consolidate `.Jules/palette.md` into `.jules/` and remove `.Jules/`.
- Fix risk: Low.
- Status: FIXED (commit b55a4bf)

### [C-01] Missing CLI subcommand: model-lab promptfoo run
- Severity: S3
- Phase/Step: C1
- Evidence: `Model_Testing_Spec.md` line 105 specifies `model-lab promptfoo run --manifest ./promptfoo/manifest.json --allow-paid`. `model_lab/cli/commands.py:98-107` defines only `promptfoo {export,import}` subparsers.
- Reproduction: `.venv-audit/bin/python -m model_lab promptfoo run --help` (fails with unrecognised arguments).
- Impact: Stated command from the test specification cannot be invoked via the CLI.
- Proposed fix: Implement `promptfoo run` subparser in `model_lab/cli/commands.py` wired to `model_lab.promptfoo.invoke_promptfoo`.
- Fix risk: Low.
- Status: FIXED (commit 2109dfc)

### [C-02] Missing CLI format: model-lab import --format aggregate-report
- Severity: S3
- Phase/Step: C1
- Evidence: `Model_Testing_Spec.md` line 93 specifies `model-lab import report.json --format aggregate-report --source-label vendor-report`. In `model_lab/cli/commands.py:79`, `--format` is restricted to `choices=["jsonl", "json", "csv"]`.
- Reproduction: `.venv-audit/bin/python -m model_lab import --db test.db --run r1 --format aggregate-report dummy.json` (rejected by argparse choices).
- Impact: Importing external aggregate reports via CLI format flag fails.
- Proposed fix: Add `aggregate-report` format parsing or clarify format support in documentation/CLI.
- Fix risk: Low.
- Status: FIXED (commit bc477ce)

### [C-03] Makefile test-release target omits integration test suite
- Severity: S3
- Phase/Step: C2
- Evidence: `Acceptance_Testing.md` line 7 specifies that `test-release` must run actual gates and fail if a required test is skipped. `Makefile` line 24 specifies `test-release: doctor test-unit test-e2e`, omitting `test-integration`.
- Reproduction: Inspect `Makefile` line 24.
- Impact: Release target does not verify the integration target as required by the acceptance contract.
- Proposed fix: Update `Makefile` to include `test-integration` and `test-smoke` in `test-release`.
- Fix risk: None; all test suites currently pass.
- Status: FIXED (commit d571617)

### [C-04] Dependency declaration vs specification divergence
- Severity: S3
- Phase/Step: C3
- Evidence: `pyproject.toml` declares `dependencies = []` and the codebase is completely stdlib-only (with optional matplotlib fallback in `model_lab/reporting.py`). `Model_Testing_Spec.md` recommends third-party packages (Typer, Rich, Pydantic, pandas, Plotly).
- Reproduction: Inspect `pyproject.toml` line 8 and compare with `Model_Testing_Spec.md` dependencies section.
- Impact: Discrepancy between aspirational specification and current stdlib implementation.
- Proposed fix: Owner decision required: update specification to affirm stdlib design, or approve adding third-party dependencies.
- Fix risk: N/A.
- Status: NEEDS-OWNER-DECISION

### [D-01] Oracle and split isolation invariant verification
- Severity: S2
- Phase/Step: D1
- Evidence: Verified. Structural projection enforced by `Case.candidate_payload` (`model_lab/schemas.py:186-193`), `CandidateInput` and `assert_candidate_safe` (`model_lab/domain/isolation.py:15-71`), `_candidate` (`model_lab/promptfoo.py:35-49`).
- Reproduction: `.venv-audit/bin/python -m pytest -q tests/test_benchmark_and_isolation.py -k test_candidate_projection`
- Impact: Invariant verified: candidate payloads cannot leak reference answers, rubrics, critical failures, family IDs, or split labels.
- Proposed fix: None needed.
- Fix risk: None.
- Status: VERIFIED (Enforcement: `model_lab/schemas.py:186-193`, `model_lab/domain/isolation.py:15-71`; Test: `tests/test_benchmark_and_isolation.py:23-40`; Bypass check: `ProviderRequest` accepts `CandidateInput` which structurally guarantees only 4 public fields).

### [D-02] Paid-dispatch gating invariant verification
- Severity: S2
- Phase/Step: D2
- Evidence: Verified. `pilot run --allow-paid` enforced in `model_lab/pilot.py:125-218`, `274-285` (`validate_pilot_plan`, `require_dispatch_authorization`, `verify_immutable_plan`, `run_authorized_immutable_pilot`). Refuses to dispatch without `--allow-paid`, matching hashes, train-only split, concurrency == 1, disabled judges/red-team, and explicit operator authorization.
- Reproduction: `.venv-audit/bin/python -m pytest -q tests/test_constraints_and_pilot_cli.py -k pilot`
- Impact: Invariant verified: live or unmetered dispatch is strictly blocked.
- Proposed fix: None needed.
- Fix risk: None.
- Status: VERIFIED (Enforcement: `model_lab/pilot.py:125-218,274-285`; Test: `tests/test_constraints_and_pilot_cli.py:59-108`, `tests/test_promptfoo_authorization.py:1-40`; Bypass check: `run_authorized_immutable_pilot` strictly validates capability and frozen plan).

### [D-03] Budget reservation atomicity invariant verification
- Severity: S2
- Phase/Step: D3
- Evidence: Verified. Enforced by SQLite `BEGIN IMMEDIATE`, `threading.RLock`, and atomic ledger state transitions in `model_lab/storage/sqlite.py:172-209` and `model_lab/domain/budget.py:21-42`. Unknown provider costs retain their conservative reservation (`state = 'unknown'`).
- Reproduction: `.venv-audit/bin/python -m pytest -q tests/test_settlement_concurrency.py`
- Impact: Invariant verified: concurrent workers cannot double-spend or release reservations on unknown costs.
- Proposed fix: None needed.
- Fix risk: None.
- Status: VERIFIED (Enforcement: `model_lab/storage/sqlite.py:172-209`, `model_lab/domain/budget.py:21-42`; Test: `tests/test_settlement_concurrency.py:16-88`; Bypass check: Direct SQLiteStore operations enforce thread locks and immediate transactions).

### [D-04] Raw-evidence immutability invariant verification
- Severity: S2
- Phase/Step: D4
- Evidence: Verified. Attempts table in SQLite is strictly append-only (`model_lab/storage/sqlite.py:45-52`, `110-118`). There is zero `UPDATE` or `DELETE` statement on attempts anywhere in the codebase. Unique index `ux_attempt_logical` prevents overwrites and raises `IntegrityError`.
- Reproduction: `.venv-audit/bin/python -m pytest -q tests/test_storage_execution.py -k test_attempts_are_append_only`
- Impact: Invariant verified: attempt records and raw responses cannot be mutated or overwritten.
- Proposed fix: None needed.
- Fix risk: None.
- Status: VERIFIED (Enforcement: `model_lab/storage/sqlite.py:45-52,110-118`; Test: `tests/test_storage_execution.py:25-32`; Bypass check: `SQLiteStore` exposes no update/delete methods for attempts).

### [D-05] Output escaping invariant verification
- Severity: S2
- Phase/Step: D5
- Evidence: Verified. CSV exports neutralize formula prefixes (`=`, `+`, `-`, `@`) with leading `'` via `_csv_safe` (`model_lab/reporting.py:113-117`). HTML exports escape all values via `html.escape(..., quote=True)` (`model_lab/reporting.py:160-176`).
- Reproduction: `.venv-audit/bin/python -m pytest -q tests/test_reporting_promptfoo.py -k test_csv_formula_cells_are_escaped_and_html_is_safe`
- Impact: Invariant verified: spreadsheet formula injection and HTML/XSS injection are safely neutralized.
- Proposed fix: None needed.
- Fix risk: None.
- Status: VERIFIED (Enforcement: `model_lab/reporting.py:113-117,160-176`; Test: `tests/test_reporting_promptfoo.py:89-106`; Bypass check: `render_csv` and `render_html` unconditionally apply sanitization to all row values).

### [D-06] Holdout one-time consumption invariant verification
- Severity: S2
- Phase/Step: D6
- Evidence: Verified. Enforced by `consume_holdout_evaluation` (`model_lab/post_pilot.py:203-220`) using atomic exclusive file creation (`open(..., "x")`). Refuses second consumption even with identical hashes; requires policy/config hashes; rejects tuning (`tuning=True`).
- Reproduction: `.venv-audit/bin/python -m pytest -q tests/test_post_pilot.py -k test_holdout_guard`
- Impact: Invariant verified: holdout evaluation cannot be re-consumed or used for model tuning.
- Proposed fix: None needed.
- Fix risk: None.
- Status: VERIFIED (Enforcement: `model_lab/post_pilot.py:203-220`; Test: `tests/test_post_pilot.py:73-82`; Bypass check: Kernel exclusive file creation `O_CREAT|O_EXCL` prevents file re-creation).

### [D-07] Draft-only routing invariant verification
- Severity: S2
- Phase/Step: D7
- Evidence: Verified. `model_lab/routing.py:34` forces `draft_only: True` on all recommendations. `router_replay_shadow` in `model_lab/post_pilot.py:223-242` asserts `application_config_changed: False` and `activation_performed: False`. Zero file writes to application configuration.
- Reproduction: `.venv-audit/bin/python -m pytest -q tests/test_post_pilot.py -k test_router_shadow_replay`
- Impact: Invariant verified: routing recommendations and shadow evaluations cannot modify production application routing or customer subscriptions.
- Proposed fix: None needed.
- Fix risk: None.
- Status: VERIFIED (Enforcement: `model_lab/routing.py:34`, `model_lab/post_pilot.py:223-242`, `model_lab/cli/commands.py:380-386`; Test: `tests/test_post_pilot.py:84-91`, `tests/test_constraints_and_pilot_cli.py:55-61`; Bypass check: No application router write routines exist in the package).

### [E-01] Test execution verification and handoff consistency
- Severity: S2
- Phase/Step: E1
- Evidence: Verified. Running `.venv-audit/bin/python -m pytest -q` reports `73 passed in 0.55s`. All 25 tests from worker handoffs ML-01, ML-02, and ML-03 run and pass under real pytest.
- Reproduction: `.venv-audit/bin/python -m pytest -q`
- Impact: All automated test suites are fully functional and pass under real pytest.
- Proposed fix: None needed.
- Fix risk: None.
- Status: VERIFIED

### [E-02] Incomplete test gate coverage: unsupported-modality labeling and tool-timeout recovery
- Severity: S3
- Phase/Step: E2
- Evidence: `Model_Testing_Spec.md` line 160 requires automatic tests for "unsupported modality labeling" and "tool timeout recovery". A search in `tests/` and `model_lab/` shows no references or tests for modality labeling. Tool timeout recovery is only partially covered by provider timeout tests (`test_storage_execution.py`), lacking specific tool simulation timeout recovery tests.
- Reproduction: `grep -rn "modality" tests/ model_lab/`
- Impact: Specification gates for unsupported modality labeling and tool timeout simulator recovery are not covered by automated tests.
- Proposed fix: Add unit tests covering modality validation/labeling and tool-timeout simulation.
- Fix risk: Low.
- Status: FIXED (commit a6dbbbf)

### [E-03] Reproducibility verification
- Severity: S2
- Phase/Step: E3
- Evidence: Verified. Ran `model_lab demo` into two separate directories (`/tmp/demo-run-1` and `/tmp/demo-run-2`). Comparison deltas, routing recommendations, and report summary quality scores were 100% deterministic and identical between both runs.
- Reproduction: Execute demo twice with `--out` directed to two separate directories and compare `report.json` and CLI summary outputs.
- Impact: Deterministic grading and reproducible offline workflow verified.
- Proposed fix: None needed.
- Fix risk: None.
- Status: VERIFIED

### [E-04] Unimplemented CI configuration
- Severity: S3
- Phase/Step: E4
- Evidence: Multiple documents (`Model_Testing_Spec.md`, `Testing_Lab_Prompt.md`, `Architecture.md`) mandate fixture-only CI passing without internet or credentials. However, no `.github/workflows/` or other CI configuration exists in the repository.
- Reproduction: `ls -la .github .gitlab-ci.yml`
- Impact: Pull requests and commits are not automatically validated against regression in CI.
- Proposed fix: Create `.github/workflows/ci.yml` running `make test-release` and `make test-smoke`.
- Fix risk: Low.
- Status: FIXED (commit a399f07)

### [F-01] Memory.md state drift and open Supervisor gate
- Severity: S3
- Phase/Step: F1
- Evidence: `Memory.md` line 4 records integrated tree `3004c37491b90af8b88807d321b06b829cdde76a`, but body describes later commits `4004808` and `20ebc9b`, while current git HEAD is `7779ff1`. Test count claims in `Memory.md` ("57 tests passed", "60 tests passed") differ from current 73 tests. Line 76 notes that the final Supervisor review on `20ebc9b` was blocked by runtime limits and left unobtained.
- Reproduction: Inspect `Memory.md` lines 4, 62-83 and run `git rev-parse HEAD`.
- Impact: Project memory is outdated relative to git history and current test counts, and records an open review gate.
- Proposed fix: Update `Memory.md` (by Boss/owner role) to reflect current HEAD, 73 passing tests, and updated audit status.
- Fix risk: Low; documentation only.
- Status: OPEN

### [F-02] Root README.md drift from byte-preserved imported copy
- Severity: S3
- Phase/Step: F2
- Evidence: Re-computation of SHA-256 hashes shows `docs/product_sources/original/README.md` (`db00d2ae...`) matches `docs/product_sources/SOURCE_MANIFEST.json`, but root `README.md` (`79a00843...`) has drifted due to the addition of the "## Current architecture" section (lines 13-25).
- Reproduction: `diff -u docs/product_sources/original/README.md README.md`
- Impact: Manifest records root files as identical to byte-preserved imported originals, but root `README.md` has drifted.
- Proposed fix: Update `docs/product_sources/SOURCE_MANIFEST.json` and `IMPORT_AUDIT.jsonl` to record the architecture documentation update to root `README.md`.
- Fix risk: Low.
- Status: OPEN

### [F-03] Superseded artifacts in live pilots directory
- Severity: S4
- Phase/Step: F3
- Evidence: `docs/live_pilots/router-constraint-map-v0.1.0.md` (superseded by `router-constraint-map-v0.2.0.json`) and `docs/live_pilots/plan-v0.1.0.json` (historical example superseded by dynamic `pilot plan`) are not referenced by live code or active docs.
- Reproduction: `grep -rn "router-constraint-map-v0.1.0" .`
- Impact: Cluttered directory with potential confusion over active vs historical pilot artifacts.
- Proposed fix: Move superseded files into `docs/live_pilots/superseded/` or add deprecation banners.
- Fix risk: Low.
- Status: OPEN

### [F-04] Documentation discrepancies with CLI commands and options
- Severity: S3
- Phase/Step: F4
- Evidence:
  1. `Model_Testing_Spec.md` specifies `suite inspect --group-by domain,complexity_level`, but `model_lab/cli/commands.py` accepts only `suite inspect path` with no `--group-by` option.
  2. `Model_Testing_Spec.md` specifies `review export --blind --out review.html`, but `model_lab/cli/commands.py` only exports JSONL and requires `--db` and `--run`.
  3. `MANUAL_TESTING.md` specifies completing review rows for import without documenting the strictly required decision values (`accept`, `reject`, `tie`, `abstain`), leading to `ValidationError` if arbitrary strings like `pass` are used.
- Reproduction: Run `model-lab suite inspect --group-by domain` or inspect `model_lab/schemas.py:375`.
- Impact: Users following documented spec examples encounter CLI argument errors.
- Proposed fix: Harmonize documentation with CLI options or extend CLI options to match the spec.
- Fix risk: Low.
- Status: FIXED (commit 9f4ac6c)
