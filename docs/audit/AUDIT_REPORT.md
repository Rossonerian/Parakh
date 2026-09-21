# ModelLab / Parakh — Final Audit and Verification Report

## 1. Baseline vs Final Environment
- **Audit Date**: 2026-09-21
- **Starting Baseline Commit**: `7779ff1f0313756e9ae6c0173a637d994386a8ef`
- **Final Tree Commit**: `740b365` (pre-report update)
- **Branch**: `main`
- **Working Tree**: clean
- **Python Version**: `Python 3.14.7`
- **Operating System**: `Linux loq-arch 7.2.6-arch2-1 #1 SMP PREEMPT_DYNAMIC Mon, 14 Sep 2026 22:41:30 +0000 x86_64 GNU/Linux`
- **Verification Metric Progression**:
  - Test Suite: 73 passed (baseline) → **77 passed** (final)
  - Release Gate (`make test-release`): doctor + 73 passed + 1 E2E → **doctor + 77 passed + 14 integration + 1 E2E + smoke**
  - Codebase Net Change: **649 insertions(+), 1143 deletions(-)** (net -494 lines of eliminated dead code and duplication)
  - Zero unbudgeted / live provider calls; 100% offline, reproducible, and fixture-backed.

---

## 2. Complete Findings & Resolution Matrix

| ID | Severity | Title | Phase | Final Status | Commit SHA |
|---|---|---|---|---|---|
| **B-01** | S1 | `model_lab/cli.py` shadowed by package `model_lab/cli/` | B1 | FIXED | `90e24ec` |
| **B-02** | S1 | `model_lab/storage.py` shadowed by package `model_lab/storage/` | B1 | FIXED | `a29bafa` |
| **B-03** | S2 | Duplicate logic in root compatibility shims vs domain/application | B3 | FIXED | `849fc64` |
| **B-04** | S4 | Directory case collision: `.jules` vs `.Jules` tracked in git | B4 | FIXED | `b55a4bf` |
| **C-01** | S3 | Missing CLI subcommand: `model-lab promptfoo run` | C1 | FIXED | `2109dfc` |
| **C-02** | S3 | Missing CLI format: `model-lab import --format aggregate-report` | C1 | FIXED | `bc477ce` |
| **C-03** | S3 | Makefile `test-release` target omits `test-integration` and `test-smoke` | C2 | FIXED | `d571617` |
| **C-04** | S3 | Dependency declaration vs specification divergence (stdlib vs Typer/Pydantic) | C3 | NEEDS-OWNER-DECISION | — |
| **D-01** | S2 | Oracle and split isolation invariant | D1 | VERIFIED | — |
| **D-02** | S2 | Paid-dispatch gating invariant | D2 | VERIFIED | — |
| **D-03** | S2 | Budget reservation atomicity invariant | D3 | VERIFIED | — |
| **D-04** | S2 | Raw-evidence immutability invariant | D4 | VERIFIED | — |
| **D-05** | S2 | Output escaping invariant (CSV formula / HTML XSS) | D5 | VERIFIED | — |
| **D-06** | S2 | Holdout one-time consumption invariant | D6 | VERIFIED | — |
| **D-07** | S2 | Draft-only routing invariant | D7 | VERIFIED | — |
| **E-01** | S2 | Test suite execution and worker handoff tests under pytest | E1 | VERIFIED | — |
| **E-02** | S3 | Missing test coverage for unsupported modalities and tool timeout recovery | E2 | FIXED | `a6dbbbf` |
| **E-03** | S2 | Reproducibility and determinism of offline demo | E3 | VERIFIED | — |
| **E-04** | S3 | Unimplemented CI configuration (`.github/workflows/ci.yml`) | E4 | FIXED | `a399f07` |
| **F-01** | S3 | `Memory.md` state drift and open Supervisor review gate | F1 | NEEDS-OWNER-ACTION | Proposed diff in Sec. 8 |
| **F-02** | S3 | Root `README.md` drift from byte-preserved imported copy | F2 | NEEDS-OWNER-ACTION | Protected file audit update |
| **F-03** | S4 | Superseded pilot artifacts in `docs/live_pilots/` | F3 | FIXED | `0fe65ea` |
| **F-04** | S3 | Documentation discrepancies with CLI arguments/options | F4 | FIXED | `9f4ac6c` |

---

## 3. Phase G Fix Waves Executed

### Wave G1: Critical Unreachable Code (Severity S1)
- **B-01** (`90e24ec`): Removed dead file `model_lab/cli.py` (426 lines) which was completely shadowed by directory package `model_lab/cli/`.
- **B-02** (`a29bafa`): Removed dead file `model_lab/storage.py` (212 lines) which was completely shadowed by directory package `model_lab/storage/`.

### Wave G2: Shim Logic Duplication (Severity S2)
- **B-03** (`849fc64`): Replaced redundant duplicated logic in root compatibility files (`model_lab/budget.py`, `model_lab/execution.py`, `model_lab/isolation.py`, `model_lab/reporting.py`) with pure re-export shims referencing `model_lab.domain.*` and `model_lab.application.*`. Eliminates risk of silent divergence.

### Wave G3: Specification Alignment & Test Coverage (Severity S3)
- **C-03** (`d571617`): Updated `Makefile` so `test-release` depends on `doctor test-unit test-integration test-e2e test-smoke`, preventing unintegrated test suites during release checks.
- **E-04** (`a399f07`): Added `.github/workflows/ci.yml` running fixture-only tests across Python 3.12, 3.13, and 3.14 without network access or live provider requirements.
- **C-01** (`2109dfc`): Implemented `promptfoo run` subparser in `model_lab/cli/commands.py` wired to `model_lab.promptfoo.invoke_promptfoo`, requiring `--manifest` and `--allow-paid`. Added unit test in `tests/test_cli_surface.py`.
- **C-02** (`bc477ce`): Added `aggregate-report` format parsing in `model_lab/ingestion.py` and `--format` choice in `model_lab/cli/commands.py`. Added unit test in `tests/test_ingestion_budget.py`.
- **E-02** (`a6dbbbf`): Added `supported_modalities` attribute to `ProviderCapabilities`, implemented `check_candidate_eligibility` in `model_lab/routing.py`, and added regression tests for unsupported modalities and tool execution timeout recovery.
- **F-04** (`9f4ac6c`): Added `--group-by` and default suite path handling to `suite inspect`, and clarified valid human review decision values (`accept`, `reject`, `tie`, `abstain`) in `MANUAL_TESTING.md`.

### Wave G4: Repository Hygiene & Dead Artifacts (Severity S4)
- **B-04** (`b55a4bf`): Consolidated `.Jules/palette.md` into `.jules/palette.md` and deleted directory `.Jules/`, eliminating Git filesystem case collision on macOS/Windows.
- **F-03** (`0fe65ea`): Archived unreferenced historical files `docs/live_pilots/router-constraint-map-v0.1.0.md` and `docs/live_pilots/plan-v0.1.0.json` into `docs/live_pilots/superseded/` with an explanatory provenance README.

---

## 4. Findings Deliberately Not Fixed / Needs Owner Decision
- **C-04 (Dependencies)**: `pyproject.toml` intentionally uses zero runtime dependencies (stdlib-only). `Model_Testing_Spec.md` mentions Typer, Rich, Pydantic, pandas, Plotly. Recommendation: Retain the clean, zero-dependency standard-library implementation and amend `Model_Testing_Spec.md` to document stdlib architecture.
- **F-01 (Memory.md state drift)**: Rule #6 strictly reserves `Memory.md` to the Boss role. A turnkey diff is provided in Section 8 below for Boss application.
- **F-02 (README.md drift from imported snapshot)**: Root `README.md` was intentionally enhanced with the "## Current architecture" section. The imported copy in `docs/product_sources/original/README.md` and `IMPORT_AUDIT.jsonl` are protected files; Boss/owner should append an entry to `IMPORT_AUDIT.jsonl` acknowledging the root README documentation update.

---

## 5. Phase D Invariants Verification Matrix

| Invariant | Enforcement Site | Test Site | Bypass Analysis |
|---|---|---|---|
| **D1: Oracle & Split Isolation** | `model_lab/schemas.py:186-193`<br>`model_lab/domain/isolation.py:15-71`<br>`model_lab/promptfoo.py:35-49` | `tests/test_benchmark_and_isolation.py:23-40` | Candidate input projection constructs a 4-key dict (`case_id`, `messages`, `limits`, `prompt_hash`). Hidden fields (`rubric`, `evaluation`, `family_id`, `split`) cannot cross into candidate payloads. |
| **D2: Paid-Dispatch Gating** | `model_lab/pilot.py:125-218`<br>`model_lab/pilot.py:274-285` | `tests/test_constraints_and_pilot_cli.py:59-108`<br>`tests/test_promptfoo_authorization.py:1-40` | `pilot run --allow-paid` strictly validates frozen plan hashes, 36 train cases, concurrency == 1, disabled judges/red-team, and explicit named operator authorization. Unbudgeted calls fail closed. |
| **D3: Budget Reservation Atomicity** | `model_lab/storage/sqlite.py:172-209`<br>`model_lab/domain/budget.py:21-42` | `tests/test_settlement_concurrency.py:16-88` | Uses `BEGIN IMMEDIATE` and `threading.RLock`. Unknown provider costs retain their conservative reservation (`state = 'unknown'`). Verified concurrent under 50 threads. |
| **D4: Raw-Evidence Immutability** | `model_lab/storage/sqlite.py:45-52,110-118` | `tests/test_storage_execution.py:25-32` | Attempts table is strictly append-only. Zero `UPDATE` or `DELETE` statements exist in codebase. Unique index `ux_attempt_logical` prevents overwrites. |
| **D5: Output Escaping** | `model_lab/reporting.py:113-117,160-176`<br>`model_lab/application/reporting.py:113-117,160-176` | `tests/test_reporting_promptfoo.py:89-106` | CSV exports neutralize formula injection characters (`=`, `+`, `-`, `@`) with prepended `'`. HTML exports unconditionally escape values via `html.escape(quote=True)`. |
| **D6: Holdout One-Time Consumption** | `model_lab/post_pilot.py:203-220` | `tests/test_post_pilot.py:73-82` | Uses OS-level exclusive file creation (`open(..., "x")`). Rejects second consumption even with identical hashes; strictly rejects tuning (`tuning=True`). |
| **D7: Draft-Only Routing** | `model_lab/routing.py:34`<br>`model_lab/post_pilot.py:223-242`<br>`model_lab/cli/commands.py:380-386` | `tests/test_post_pilot.py:84-91`<br>`tests/test_constraints_and_pilot_cli.py:55-61` | All recommendation outputs enforce `draft_only: True`. Zero file writes to application config or customer entitlements. |

---

## 6. Exact Automated Verification Results

### Final Local Gate
```bash
.venv-audit/bin/python -m compileall -q model_lab tests  # EXIT 0
.venv-audit/bin/python -m pytest -q                     # 77 passed in 0.49s (EXIT 0)
make PYTHON=.venv-audit/bin/python test-release         # EXIT 0 (doctor + 77 unit + 14 integration + 1 e2e + smoke)
make PYTHON=.venv-audit/bin/python test-smoke           # EXIT 0 (60 cases validated across 15 domains / 15 families)
```

### Clean-Room Verification (`/tmp/parakh-verify`)
- Cloned clean repository into `/tmp/parakh-verify`.
- Built fresh virtual environment and installed editable package: `EXIT 0`.
- Ran `make test-release`: **All 77 unit tests, 14 integration tests, 1 E2E test, and smoke test PASSED**.
- Ran `make demo`: **Full 60-case synthetic offline pipeline PASSED**, generated complete reports (`report.html`, `report.csv`, `charts.json`, `latency_distribution.svg`, `quality_by_model.svg`), promptfoo quarantine verification, and draft recommendations.
- Clean-room environment deleted cleanly after verification.

---

## 7. Scope Boundaries and Blocked Actions
The following areas were **not** executed during this audit and remain strictly `BLOCKED`:
- **Live Provider Calls**: No calls to Ollama, OpenRouter, or external LLM APIs were made (`BLOCKED`).
- **Paid Dispatch**: No `--allow-paid` commands were executed (`BLOCKED`).
- **Production Routing / Application Changes**: No application configuration or customer subscription tables were modified (`BLOCKED`).
- **Live Channels & External Platforms**: WhatsApp, payment webhooks, and live user communication remain unverified and blocked (`BLOCKED`).

---

## 8. Boss / Owner Action Items & Proposed Memory.md Diff

To resolve **F-01**, apply the following update to `Memory.md`:

```markdown
--- Memory.md
+++ Memory.md
@@ -1,9 +1,9 @@
 # ModelLab implementation memory
 
-Updated UTC: 2026-09-11
-Branch: `main`; integrated pilot-preparation tree: `3004c37491b90af8b88807d321b06b829cdde76a`.
+Updated UTC: 2026-09-21
+Branch: `main`; integrated audit-and-fix tree: `HEAD`.
 
 ## Verified product-source intake
@@ -62,17 +62,17 @@
-On the integrated tree: `make PYTHON=.venv/bin/python test-release` passed
-(`doctor`, 57 pytest tests, 60-case offline E2E); direct full pytest passed
-57 tests; compileall passed; suite validation reported 60 cases, 15 families,
-36/12/12 train/calibration/holdout; two distinct disposable `make dev` runs
-completed using fake providers only.
+On the baseline audit tree: comprehensive audit completed across Phases A-F.
+All 7 Phase D invariants verified with exact code and test citations.
+Phase G executed 4 fix waves resolving all actionable S1-S4 findings:
+shadowed modules removed (B-01, B-02), shims consolidated (B-03), .jules case
+collision resolved (B-04), promptfoo run and aggregate-report CLI implemented
+(C-01, C-02), test-release gate expanded (C-03), CI workflow added (E-04),
+modality labeling/tool timeout tests added (E-02), superseded pilots archived
+(F-03), and CLI/doc options aligned (F-04).
+Clean-room verification in isolated directory passed `test-release` (77 unit,
+14 integration, 1 E2E, smoke) and `demo` with zero errors.
```
