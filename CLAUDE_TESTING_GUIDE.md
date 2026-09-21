# Parakh / ModelLab — Claude Testing & Verification Runbook
> **Instructions for the User:**
> Copy this entire document and paste it into Claude (or instruct Claude: *"Please read `CLAUDE_TESTING_GUIDE.md` and act as my interactive Testing Lead step by step"*).
> Claude will guide you through testing the entire platform in a safe, interactive, step-by-step manner.

---

## 🤖 System Instructions for Claude

You are acting as the **Senior Verification & QA Lead** for the **Parakh / ModelLab** project.
Your mission is to guide the user through verifying and testing the entire system from a clean terminal.

### 📋 Rules of Engagement for Claude
1. **Interactive, Step-by-Step Flow**:
   - **DO NOT dump all steps at once.** Present **ONE step at a time**.
   - For each step:
     1. State the step title and purpose.
     2. Give the exact shell command to run.
     3. Explain what output/exit code to expect.
     4. Prompt the user: *"Run this command and paste the output (or tell me it passed), and we will proceed to the next step."*
   - Once the user provides the output, verify it against the expected criteria. If valid, confirm the pass and present the next step. If it fails, diagnose the issue using the troubleshooting guide.
2. **Zero-Spend / Safety Boundaries**:
   - Never instruct the user to run paid provider calls or invoke `--allow-paid` with real money. All standard tests and demos must run offline using the built-in deterministic fake provider.
   - Subscription names are **Ananta** (Free), **Yanta** (Entry Paid), **Trika** (Advanced), and **Part** (Premium). Never confuse subscription names with model identifiers.
   - Protected files: Never modify `Memory.md`, `benchmarks/**`, `docs/product_sources/original/**`, or `docs/handoffs/**`.
3. **Tracking Progress**:
   - Keep a concise progress checklist showing which phases are complete.

---

## 🗺️ Verification Roadmap Overview

| Phase | Focus Area | Expected Duration | Risk Level |
|:---|:---|:---|:---|
| **Phase 1** | Environment & Baseline Health Check | 2 mins | Zero (Read-only) |
| **Phase 2** | Benchmark Suite Integrity & Oracle Isolation | 2 mins | Zero (Read-only) |
| **Phase 3** | Synthetic Offline Pipeline & Multi-Format Reports | 3 mins | Zero (Local files) |
| **Phase 4** | Anonymized Blind Human Review Workflow | 3 mins | Zero (Local SQLite) |
| **Phase 5** | Ingestion Engine & Promptfoo Security Adapter | 3 mins | Zero (Local fixtures) |
| **Phase 6** | Routing Evidence & Constraint Map Verification | 2 mins | Zero (Read-only) |
| **Phase 7** | Live-Pilot Safety Preflight & Guardrail Gating | 2 mins | Zero (Fail-closed) |

---

## Phase 1: Environment & Baseline Health Check

### Step 1.1 — Verify Python & Virtual Environment
**Goal**: Ensure Python 3.12+ is active and the virtual environment is healthy.

**Command to run**:
```bash
python3 --version
.venv-audit/bin/python --version
```
*(If `.venv-audit` is not available, run with `.venv/bin/python`)*.

**Expected Result**:
- Python version must be `>= 3.12.0`.

---

### Step 1.2 — Run System Doctor Check
**Goal**: Verify benchmark presence, offline readiness, and environment capability.

**Command to run**:
```bash
.venv-audit/bin/python -m model_lab doctor
```

**Expected Result**:
JSON output confirming 60 benchmark cases and offline readiness:
```json
{
  "benchmark_cases": 60,
  "benchmark_present": true,
  "offline_ready": true,
  "python_3_12_plus": true
}
```

---

### Step 1.3 — Static Compilation Check
**Goal**: Ensure all Python modules and tests compile cleanly with zero syntax errors.

**Command to run**:
```bash
.venv-audit/bin/python -m compileall -q model_lab tests
```

**Expected Result**:
- Exit code `0` with zero error messages.

---

### Step 1.4 — Automated Test Suite Execution
**Goal**: Run all 77 pytest unit and regression tests.

**Command to run**:
```bash
.venv-audit/bin/python -m pytest -q
```

**Expected Result**:
- `77 passed in <1s` (Exit code `0`).

---

### Step 1.5 — Comprehensive Release Gate Check
**Goal**: Execute the full release target which combines `doctor`, unit tests, integration tests, end-to-end tests, and smoke test.

**Command to run**:
```bash
make PYTHON=.venv-audit/bin/python test-release
```

**Expected Result**:
- Passes all five checks sequentially:
  1. `doctor`: 60 cases detected.
  2. `test-unit`: 77 passed.
  3. `test-integration`: 14 passed (`test_storage_execution.py`, `test_ingestion_budget.py`, `test_offline_e2e.py`).
  4. `test-e2e`: 1 passed (`test_offline_e2e.py`).
  5. `test-smoke`: suite validation passes with 60 cases across 15 domains.

---

## Phase 2: Benchmark Suite Integrity & Oracle Isolation

### Step 2.1 — Validate Benchmark Suite Structure
**Goal**: Verify seed cases, split distribution, complexity levels, and family structures.

**Command to run**:
```bash
.venv-audit/bin/python -m model_lab suite validate benchmarks/seed_cases.jsonl
```

**Expected Result**:
- Exactly **60 cases**, **15 domains**, **15 families**, with **4 complexity levels** (15 cases each).
- Splits: **36 train**, **12 calibration**, **12 holdout**.
- Source hash: `9f82842371ab949a1018c5625875b1830d625d95c7b7380d5e35a172f8df230e`.

---

### Step 2.2 — Inspect Suite Grouped by Domain
**Goal**: Confirm domain grouping works across all 15 workflow domains.

**Command to run**:
```bash
.venv-audit/bin/python -m model_lab suite inspect benchmarks/seed_cases.jsonl --group-by domain
```

**Expected Result**:
- Displays breakdown for all 15 domains (ambiguity, automation, calendar, communication, conversation_memory, document_extraction, expenses, multilingual, privacy, shopping, source_reasoning, support, tabular_analysis, task_planning, travel).

---

### Step 2.3 — Candidate-Only Export (Isolation Barrier)
**Goal**: Export benchmark cases for candidate models with all reference answers, grading rubrics, and split tags stripped.

**Command to run**:
```bash
.venv-audit/bin/python -m model_lab suite export benchmarks/seed_cases.jsonl --candidate-only --out /tmp/parakh-candidate.jsonl
head -n 2 /tmp/parakh-candidate.jsonl
```

**Expected Result**:
- Success JSON: `{"candidate_only": true, "exported": 60, "path": "/tmp/parakh-candidate.jsonl"}`.
- Each exported record must contain **only 4 keys**: `case_id`, `limits`, `messages`, `prompt_hash`.

---

### Step 2.4 — Oracle Leakage Verification Test
**Goal**: Prove mathematically that no secret reference answers, rubrics, split labels, or family IDs leaked into the candidate export.

**Command to run**:
```bash
python3 -c '
import json
with open("/tmp/parakh-candidate.jsonl") as f:
    forbidden = {"reference", "rubric", "evaluation", "split", "family_id", "ground_truth"}
    leaks = []
    for line in f:
        data = json.loads(line)
        found = forbidden.intersection(data.keys())
        if found:
            leaks.append((data.get("case_id"), found))
    if leaks:
        print(f"FAILED: Leaks detected: {leaks}")
        exit(1)
    print("PASSED: 100% Oracle isolation verified. Zero forbidden keys present.")
'
```

**Expected Result**:
- `PASSED: 100% Oracle isolation verified. Zero forbidden keys present.`

---

## Phase 3: Synthetic Offline Workflow & Report Generation

### Step 3.1 — Execute Full Offline Demo Pipeline
**Goal**: Run the complete 60-case synthetic lifecycle (executes two models `synthetic-good` and `synthetic-incorrect`, grades deterministic checks, computes paired comparisons, and generates report assets).

**Command to run**:
```bash
make PYTHON=.venv-audit/bin/python demo
```

**Expected Result**:
- Execution completes with code `0`.
- Summary JSON output printed to stdout displaying runs for `synthetic-good` (score `1.0`) and `synthetic-incorrect` (score `0.0`), promptfoo quarantine check, and draft recommendations.

---

### Step 3.2 — Verify Generated Report Artifacts
**Goal**: Inspect generated report directory and confirm all required formats exist.

**Command to run**:
```bash
ls -la lab-data/demo/reports/synthetic-good/
```

**Expected Result**:
All 7 required artifacts must exist:
1. `report.html` (Standalone interactive HTML report)
2. `report.csv` (Spreadsheet export)
3. `report.md` (Markdown summary)
4. `report.json` (Structured metrics)
5. `charts.json` (Data points for charts)
6. `latency_distribution.svg` (Vector latency chart)
7. `quality_by_model.svg` (Vector quality comparison chart)

---

### Step 3.3 — Verify Security Escaping (XSS & CSV Injection Protection)
**Goal**: Verify that outputs are escaped to prevent formula injection (`=`, `+`, `-`, `@`) and HTML XSS.

**Command to run**:
```bash
head -n 5 lab-data/demo/reports/synthetic-good/report.csv
grep -i "<script" lab-data/demo/reports/synthetic-good/report.html || echo "PASSED: Zero unescaped script tags"
```

**Expected Result**:
- CSV lines properly quote all text fields.
- Zero raw `<script` tags found in HTML.

---

## Phase 4: Blind Human Review Simulation

### Step 4.1 — Export Anonymized Blind Review Manifest
**Goal**: Export review records where candidate identity, provider, latency, and cost are completely hidden from human evaluators.

**Command to run**:
```bash
.venv-audit/bin/python -m model_lab review export \
  --db lab-data/demo/model_lab.sqlite3 \
  --run run-synthetic-good \
  --out /tmp/review-batch.jsonl
head -n 2 /tmp/review-batch.jsonl
```

**Expected Result**:
- JSON confirmation: `{"blind": true, "exported": 60, "path": "/tmp/review-batch.jsonl"}`.
- Records show `blind_label` (e.g. `candidate-6a198c37db8d`), `candidate_output`, `case_id`, `review_id`, `run_id`, `status`.
- **Zero** mentions of `provider`, `model`, `latency`, or `cost`.

---

### Step 4.2 — Record & Import Human Review Decisions
**Goal**: Simulate a human evaluator reviewing a case and submitting a judgment (`accept`, `reject`, `tie`, or `abstain`).

**Command to run**:
```bash
python3 -c '
import json
with open("/tmp/review-batch.jsonl") as f:
    lines = [json.loads(l) for l in f]
# Select the third case to avoid duplicate key conflict with demo seed
target = lines[2]
target["decision"] = "accept"
target["reviewer_pseudonym"] = "evaluator-claude"
target["score"] = 1.0
target["confidence"] = 0.95
target["notes"] = "Verified compliance with prompt constraints."
with open("/tmp/review-submission.jsonl", "w") as out:
    out.write(json.dumps(target) + "\n")
'
.venv-audit/bin/python -m model_lab review import \
  --db lab-data/demo/model_lab.sqlite3 \
  --run run-synthetic-good \
  --in /tmp/review-submission.jsonl
```

**Expected Result**:
- JSON output:
  ```json
  {
    "blind": true,
    "imported": 1,
    "run_id": "run-synthetic-good"
  }
  ```

---

### Step 4.3 — Verify Review Storage Separation & Anti-Tamper
**Goal**: Prove human review records are stored in the `reviews` table and cannot alter immutable automated `grades`.

**Command to run**:
```bash
python3 -c '
import sqlite3
con = sqlite3.connect("lab-data/demo/model_lab.sqlite3")
reviews = con.execute("SELECT count(*) FROM reviews WHERE json_extract(record_json, \"$.reviewer_pseudonym\") = \"evaluator-claude\"").fetchone()[0]
grades = con.execute("SELECT count(*) FROM grades").fetchone()[0]
print(f"Human reviews stored: {reviews} | Automated grades intact: {grades}")
assert reviews >= 1, "Review was not recorded!"
assert grades == 120, f"Automated grades altered: expected 120, got {grades}"
print("PASSED: Human reviews isolated and automated grades intact.")
'
```

**Expected Result**:
- `PASSED: Human reviews isolated and automated grades intact.`

---

## Phase 5: Ingestion Engine & Promptfoo Security Adapter

### Step 5.1 — Export Promptfoo Candidate Manifest
**Goal**: Export a Promptfoo manifest from the test suite, guaranteeing that hidden fields never reach Promptfoo config.

**Command to run**:
```bash
.venv-audit/bin/python -m model_lab promptfoo export \
  --suite benchmarks/seed_cases.jsonl \
  --out /tmp/promptfoo-manifest.json
head -n 12 /tmp/promptfoo-manifest.json
```

**Expected Result**:
- Output confirms: `{"candidate_only": true, "exported": 60, "manifest_hash": "..."}`.
- Manifest contains test inputs without rubrics, splits, or answers.

---

### Step 5.2 — Verify Paid-Dispatch Gating on Promptfoo
**Goal**: Verify that live promptfoo execution is hard-blocked without explicit `--allow-paid` authorization.

**Command to run**:
```bash
.venv-audit/bin/python -m model_lab promptfoo run --manifest /tmp/promptfoo-manifest.json || echo "EXIT CODE: $?"
```

**Expected Result**:
- Fails closed with exit code `2`:
  `model-lab: error: live Promptfoo invocation blocked: explicit --allow-paid acknowledgement required`

---

### Step 5.3 — Test Aggregate-Report Format Ingestion
**Goal**: Verify that high-level summary reports can be ingested with `--format aggregate-report` without fabricating synthetic individual attempts.

**Command to run**:
```bash
python3 -c '
import json, tempfile
data = {
    "provider": "vendor-x",
    "model": "test-v1",
    "overall_score": 0.88,
    "metrics": {"latency_p50": 340, "cost_usd": 0.012}
}
with open("/tmp/sample-aggregate.json", "w") as f:
    json.dump(data, f)
'
.venv-audit/bin/python -m model_lab import /tmp/sample-aggregate.json \
  --db lab-data/demo/model_lab.sqlite3 \
  --run run-synthetic-good \
  --format aggregate-report \
  --source-label vendor-benchmark
```

**Expected Result**:
- Output confirms successful ingestion of aggregate data into provenance records:
  ```json
  {
    "imported": 1,
    "records": 1,
    "run_id": "run-synthetic-good",
    "source_label": "vendor-benchmark"
  }
  ```

---

## Phase 6: Routing Evidence & Constraint Map Verification

### Step 6.1 — Generate Draft Routing Recommendations
**Goal**: Evaluate candidate evidence against product constraints and produce a draft recommendation without altering production systems.

**Command to run**:
```bash
.venv-audit/bin/python -m model_lab router recommend \
  --draft \
  --summary lab-data/demo/summary.json
```

**Expected Result**:
- Output contains `draft: true`, `production_config_changed: false`.
- Lists evaluated constraints (11 evaluated, satisfied product criteria, and noted blocking criteria like launch channel eligibility).
- Returns exit code `2` indicating activation is blocked by required unmetered live constraints (by design: draft only).

---

### Step 6.2 — Verify Invariant: Zero Production Config Writes
**Goal**: Prove that running routing evaluation never alters production routing or subscription entitlement tables.

**Command to run**:
```bash
git status --short
```

**Expected Result**:
- Working tree clean. Zero modified production config files.

---

## Phase 7: Live-Pilot Safety Preflight & Guardrail Gating

### Step 7.1 — Operator Input Validation Gate (Fail-Closed Check)
**Goal**: Verify that the committed operator template cannot be used for live dispatch without explicit, validated commercial authorization.

**Command to run**:
```bash
.venv-audit/bin/python -m model_lab pilot validate-input \
  --input docs/live_pilots/operator-input.template.yaml \
  --suite benchmarks/seed_cases.jsonl || echo "EXIT CODE: $?"
```

**Expected Result**:
- Fails closed with exit code `2`:
  `model-lab: error: candidate.identifier must be non-empty text`
- Proves unconfigured or default templates cannot trigger accidental execution.

---

### Step 7.2 — Holdout Split Immutability & Consumption Lock
**Goal**: Verify that holdout cases are locked and cannot be consumed more than once or used for prompt tuning.

**Command to run**:
```bash
.venv-audit/bin/python -m pytest tests/test_post_pilot.py -k "test_holdout"
```

**Expected Result**:
- Passed tests confirming holdout one-time consumption lock and anti-tuning gates.

---

## 🧹 Post-Test Cleanup

When all phases are verified, clean up temporary test files:
```bash
rm -f /tmp/parakh-candidate.jsonl /tmp/review-batch.jsonl /tmp/review-submission.jsonl /tmp/promptfoo-manifest.json /tmp/sample-aggregate.json
```

---

## 🛠️ Claude Troubleshooting Guide

If the user encounters an unexpected error during any step, consult this guide:

| Symptom | Cause | Resolution |
|:---|:---|:---|
| `python: command not found` | Virtual environment not activated or wrong path | Use `.venv-audit/bin/python` or run `source .venv-audit/bin/activate`. |
| `doctor fails: benchmark not present` | Current working directory is not project root | Ensure cwd is `/home/rosso/Projects/Parakh`. |
| `IntegrityError: duplicate review` | Attempted to insert a review with an existing `review_id` | Use a different row from `/tmp/review-batch.jsonl` or generate a fresh review ID. |
| `ModelLabError: live Promptfoo invocation blocked` | `--allow-paid` was omitted | Expected behavior for safety; Promptfoo requires explicit operator authorization. |
| `router recommend exits with code 2` | `activation_ready: false` | Expected behavior; recommendations are draft-only until owner clears live constraints. |
| `pilot validate-input fails on template` | Default template has dummy placeholder fields | Expected behavior; protects against accidental dispatch of unverified candidates. |

---

## 🏁 Final Sign-Off Checklist for Claude

When all 7 phases are completed, summarize the verification state:
- [x] **Phase 1**: Environment, Doctor, and 77 Unit/Integration/E2E tests passing.
- [x] **Phase 2**: Benchmark suite validated (60 cases, 15 domains, 15 families, 36/12/12 split); candidate-only export verified with 0% oracle leakage.
- [x] **Phase 3**: Offline demo pipeline executed; reports generated in HTML, CSV, MD, JSON, and SVG with XSS/CSV escaping verified.
- [x] **Phase 4**: Blind review export and import verified; human judgments stored separately from automated grades.
- [x] **Phase 5**: Promptfoo candidate manifest exported; aggregate-report ingestion verified; paid execution gated.
- [x] **Phase 6**: Draft router recommendations generated with `draft: true` and `production_config_changed: false`.
- [x] **Phase 7**: Live pilot safety controls verified; default template fails closed; holdout consumption locks confirmed.
