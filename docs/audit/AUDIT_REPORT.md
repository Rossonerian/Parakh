# ModelLab / Parakh — Audit Report

## 1. Baseline Environment
- **Audit Date**: 2026-09-21
- **Starting Commit**: `7779ff1f0313756e9ae6c0173a637d994386a8ef`
- **Branch**: `main`
- **Working Tree**: clean
- **Python Version**: `Python 3.14.7`
- **Operating System**: `Linux loq-arch 7.2.6-arch2-1 #1 SMP PREEMPT_DYNAMIC Mon, 14 Sep 2026 22:41:30 +0000 x86_64 GNU/Linux`
- **Pre-audit Documented Command Reproduction**:
  - `python3 -m venv .venv-audit`: EXIT 0
  - `.venv-audit/bin/python -m pip install -e '.[dev]'`: EXIT 0
  - `.venv-audit/bin/python -m model_lab --help`: EXIT 0
  - `.venv-audit/bin/python -m model_lab doctor`: EXIT 0 (60 benchmark cases detected)
  - `.venv-audit/bin/model-lab --help`: EXIT 0
  - `make test-unit`: EXIT 0 (73 passed)
  - `make test-integration`: EXIT 0 (12 passed)
  - `make test-e2e`: EXIT 0 (1 passed)
  - `make test-smoke`: EXIT 0 (60 cases validated)
  - `make test-release`: EXIT 0 (doctor + 73 unit + 1 E2E)
  - `make demo`: EXIT 0 (complete 60-case synthetic offline workflow)
  - `make dev`: EXIT 0 (disposable `lab-data/dev.XXXXXX` execution)

---

## 2. Findings Summary Table

| ID | Severity | Title | Phase | Status |
|---|---|---|---|---|
| **B-01** | S1 | `model_lab/cli.py` shadowed by package `model_lab/cli/` | B1 | OPEN |
| **B-02** | S1 | `model_lab/storage.py` shadowed by package `model_lab/storage/` | B1 | OPEN |
| **B-03** | S2 | Shim vs implementation duplicate logic in `model_lab/*.py` | B3 | OPEN |
| **B-04** | S4 | Directory case collision: `.jules` vs `.Jules` tracked in git | B4 | OPEN |
| **C-01** | S3 | Missing CLI subcommand: `model-lab promptfoo run` | C1 | OPEN |
| **C-02** | S3 | Missing CLI format: `model-lab import --format aggregate-report` | C1 | OPEN |
| **C-03** | S3 | Makefile `test-release` target omits `test-integration` | C2 | OPEN |
| **C-04** | S3 | Dependency declaration vs specification divergence (stdlib vs Typer/Pydantic) | C3 | NEEDS-OWNER-DECISION |
| **D-01** | S2 | Oracle and split isolation invariant | D1 | VERIFIED |
| **D-02** | S2 | Paid-dispatch gating invariant | D2 | VERIFIED |
| **D-03** | S2 | Budget reservation atomicity invariant | D3 | VERIFIED |
| **D-04** | S2 | Raw-evidence immutability invariant | D4 | VERIFIED |
| **D-05** | S2 | Output escaping invariant (CSV formula / HTML XSS) | D5 | VERIFIED |
| **D-06** | S2 | Holdout one-time consumption invariant | D6 | VERIFIED |
| **D-07** | S2 | Draft-only routing invariant | D7 | VERIFIED |
| **E-01** | S2 | Test suite execution and worker handoff tests under pytest | E1 | VERIFIED |
| **E-02** | S3 | Incomplete test coverage: unsupported-modality labeling and tool simulator timeout | E2 | OPEN |
| **E-03** | S2 | Reproducibility and determinism of offline demo | E3 | VERIFIED |
| **E-04** | S3 | Unimplemented CI configuration (`.github/workflows/`) | E4 | OPEN |
| **F-01** | S3 | `Memory.md` state drift and open Supervisor review gate | F1 | OPEN |
| **F-02** | S3 | Root `README.md` drift from byte-preserved imported copy | F2 | OPEN |
| **F-03** | S4 | Superseded pilot artifacts in `docs/live_pilots/` | F3 | OPEN |
| **F-04** | S3 | Documentation discrepancies with CLI arguments/options | F4 | OPEN |

---

## 3. Fixes Applied
Per section 0 of the audit plan, Phases A through F are strictly read-only. No fixes were applied in this phase.
All findings are recorded in `docs/audit/FINDINGS.md` and await owner review before entering Phase G (Fix execution).

---

## 4. Findings Deliberately Not Fixed / Needs Owner Decision
- **C-04 (Dependencies)**: `pyproject.toml` uses zero runtime dependencies (stdlib-only). `Model_Testing_Spec.md` recommends Typer, Rich, Pydantic, pandas, Plotly. The owner must decide whether to update the specification to celebrate the lightweight stdlib implementation or adopt the recommended third-party packages.
- **F-01 (Memory.md update)**: Standing rules explicitly prohibit autonomous modification of `Memory.md` during audit/specification phases; Boss/owner will apply the recorded update.
- **F-02 (README drift)**: The drift in `README.md` represents intentional architecture documentation added by the team. Owner needs to acknowledge and record this in `IMPORT_AUDIT.jsonl` and `SOURCE_MANIFEST.json`.

---

## 5. Phase D Invariants Verification

| Invariant | Enforcement Site | Test Site | Bypass Analysis |
|---|---|---|---|
| **D1: Oracle & Split Isolation** | `model_lab/schemas.py:186-193`<br>`model_lab/domain/isolation.py:15-71`<br>`model_lab/promptfoo.py:35-49` | `tests/test_benchmark_and_isolation.py:23-40` | Structural projection constructs a 4-key dict (`case_id`, `messages`, `limits`, `prompt_hash`). Hidden fields (`rubric`, `evaluation`, `family_id`, `split`) cannot cross into candidate payloads. |
| **D2: Paid-Dispatch Gating** | `model_lab/pilot.py:125-218`<br>`model_lab/pilot.py:274-285` | `tests/test_constraints_and_pilot_cli.py:59-108`<br>`tests/test_promptfoo_authorization.py:1-40` | `pilot run --allow-paid` enforces frozen plan hashes, 36 train cases, concurrency == 1, disabled judges/red-team, and explicit named operator authorization. Unbudgeted calls fail closed. |
| **D3: Budget Reservation Atomicity** | `model_lab/storage/sqlite.py:172-209`<br>`model_lab/domain/budget.py:21-42` | `tests/test_settlement_concurrency.py:16-88` | Uses `BEGIN IMMEDIATE` and `threading.RLock`. Unknown provider costs retain their conservative reservation (`state = 'unknown'`). Verified concurrent under 50 threads. |
| **D4: Raw-Evidence Immutability** | `model_lab/storage/sqlite.py:45-52,110-118` | `tests/test_storage_execution.py:25-32` | Attempts table is strictly append-only. Zero `UPDATE` or `DELETE` statements exist in codebase. Unique index `ux_attempt_logical` prevents overwrites. |
| **D5: Output Escaping** | `model_lab/reporting.py:113-117,160-176`<br>`model_lab/application/reporting.py:113-117,160-176` | `tests/test_reporting_promptfoo.py:89-106` | CSV exports neutralize formula characters (`=`, `+`, `-`, `@`) with `'`. HTML exports unconditionally escape values via `html.escape(quote=True)`. |
| **D6: Holdout One-Time Consumption** | `model_lab/post_pilot.py:203-220` | `tests/test_post_pilot.py:73-82` | Uses OS-level exclusive file creation (`open(..., "x")`). Rejects second consumption even with identical hashes; strictly rejects tuning (`tuning=True`). |
| **D7: Draft-Only Routing** | `model_lab/routing.py:34`<br>`model_lab/post_pilot.py:223-242`<br>`model_lab/cli/commands.py:380-386` | `tests/test_post_pilot.py:84-91`<br>`tests/test_constraints_and_pilot_cli.py:55-61` | All recommendation outputs enforce `draft_only: True`. Zero file writes to application config or customer entitlements. |

---

## 6. Exact Automated Results

| Command | Exit Code | Observed Output / Counts |
|---|---|---|
| `python3 -m venv .venv-audit` | 0 | Virtualenv created |
| `.venv-audit/bin/python -m pip install -e '.[dev]'` | 0 | Installed `parakh-model-lab-0.1.0` and `pytest-8.4.2` |
| `.venv-audit/bin/python -m model_lab --help` | 0 | Displayed 15 subcommands |
| `.venv-audit/bin/python -m model_lab doctor` | 0 | `{"benchmark_cases": 60, "offline_ready": true, "python_3_12_plus": true}` |
| `.venv-audit/bin/model-lab --help` | 0 | Console script entry point working |
| `make PYTHON=.venv-audit/bin/python doctor` | 0 | Prerequisite checks passed |
| `make PYTHON=.venv-audit/bin/python test-unit` | 0 | 73 passed in 0.70s |
| `make PYTHON=.venv-audit/bin/python test-integration` | 0 | 12 passed in 0.24s |
| `make PYTHON=.venv-audit/bin/python test-e2e` | 0 | 1 passed in 0.28s |
| `make PYTHON=.venv-audit/bin/python test-smoke` | 0 | 60 cases validated across 15 domains / 15 families |
| `make PYTHON=.venv-audit/bin/python test-release` | 0 | doctor + 73 tests + 1 test passed |
| `make PYTHON=.venv-audit/bin/python demo` | 0 | Complete 60-case offline pipeline executed with fake provider |
| `make PYTHON=.venv-audit/bin/python dev` | 0 | Disposable `lab-data/dev.UsiO2k` run succeeded |
| `python -m pytest -q (all tests)` | 0 | 73 passed in 0.55s |
| `python -m compileall -q model_lab tests` | 0 | Byte-compilation succeeded with zero errors |

---

## 7. Scope Boundaries and Blocked Actions
The following areas were **not** executed during this audit and remain strictly `BLOCKED`:
- **Live Provider Calls**: No calls to Ollama, OpenRouter, or external LLM APIs were made (`BLOCKED`).
- **Paid Dispatch**: No `--allow-paid` commands were executed (`BLOCKED`).
- **Production Routing / Application Changes**: No application configuration or customer subscription tables were modified (`BLOCKED`).
- **Live Channels & External Platforms**: WhatsApp, payment webhooks, and live user communication remain unverified and blocked (`BLOCKED`).

---

## 8. Recommended Next Actions
1. **Approve Phase G Fix Waves**: Review and approve findings in `docs/audit/FINDINGS.md` for fix execution:
   - Wave G1 (S1): Remove unreachable shadowed modules `model_lab/cli.py` and `model_lab/storage.py`.
   - Wave G2 (S2): Collapse duplicate logic in `model_lab/{budget,execution,isolation,reporting}.py` into pure re-export shims.
   - Wave G3 (S3): Add `promptfoo run` CLI subcommand, update Makefile `test-release` target to include `test-integration`, add `.github/workflows/ci.yml`, and align test coverage.
   - Wave G4 (S4): Consolidate case collision `.Jules/palette.md` into `.jules/`.
2. **Owner Decision on Dependencies (C-04)**: Decide whether to update `Model_Testing_Spec.md` to reflect the lightweight standard-library implementation or introduce external packages (Typer, Pydantic).
3. **Owner Review of Memory.md (F-01)**: Update `Memory.md` to record audit completion, current HEAD `7779ff1`, and current 73-test baseline.
