# ModelLab manual testing

This runbook describes the offline workflow that can be reproduced on Linux with Python 3.12 and no provider credentials.

## Setup

```bash
python3 --version
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python -m model_lab --help
.venv/bin/python -m model_lab doctor
make PYTHON=.venv/bin/python test-release
# `make dev` uses a fresh disposable `lab-data/dev.XXXXXX` directory each time.
```

The implementation has no runtime network dependency. Keep live-provider keys in environment variables only; do not place them in benchmark files, SQLite records, reports, or `Memory.md`.

## Benchmark validation and candidate export

```bash
.venv/bin/python -m model_lab suite validate benchmarks/seed_cases.jsonl
.venv/bin/python -m model_lab suite inspect benchmarks/seed_cases.jsonl
.venv/bin/python -m model_lab suite export benchmarks/seed_cases.jsonl --candidate-only --out /tmp/parakh-candidate.jsonl
```

Expected validation facts are 60 cases, 15 domains, 15 families, four levels with 15 cases each, and train/calibration/holdout counts of 36/12/12. Inspect the exported JSONL: it must contain only candidate messages, limits, case IDs, and prompt hashes. It must not contain reference answers, rubrics, critical failures, family IDs, or split labels.

## Automated checks

```bash
.venv/bin/python -m pytest -q
.venv/bin/python -m compileall -q model_lab tests
```

The tests cover malformed benchmark records, duplicate IDs, candidate immutability, provider failures, budget stopping, duplicate imports, deterministic graders, report escaping, Promptfoo hash reconciliation, and the complete synthetic 60-case pipeline when present.

## Offline synthetic lifecycle

The offline demo uses a deterministic fake provider and labels all results as synthetic. Run the documented CLI `run`/`grade`/`compare`/`report`/`router recommend --draft` commands after installation; each command writes to an explicitly selected local data directory. A complete run must:

1. validate the frozen benchmark;
2. project candidate-only messages;
3. execute all 60 cases with a deterministic fake provider;
4. persist immutable raw attempts and provenance in SQLite;
5. grade deterministic methods and abstain where semantic review is needed;
6. compare by domain, workflow, difficulty, and split;
7. render JSON, CSV, Markdown, escaped HTML, and available chart artifacts;
8. emit a routing-evidence draft linked to measured attempt/grade IDs.

Unknown metrics are displayed as `null`/unknown. Synthetic results are not model-performance claims.

## Failure injection

Exercise fake variants for incorrect, incomplete, malformed, refusal, provider failure, timeout, cancelled, missing metadata, duplicate, and adversarial output. Verify that failures retain their real state, are not converted to zero quality, do not silently retry beyond budget, and remain visible in reports. Import a malicious HTML response and a CSV value beginning with `=`; HTML and spreadsheet exports must escape both safely.

## Human review

Export a blind review set for a selected run, inspect anonymized candidate labels, enter decisions/notes/confidence, then import the review records. Reviewers must not receive model/provider identity, cost, latency, or prior rankings unless the protocol explicitly requires it. Human judgements are stored separately from automated grades.

## Reproducibility and regression

Repeat the same fake run with the same suite hash, provider variant, configuration, and seed. Stable candidate hashes, raw fake responses, grades, and derived summaries should match. Timestamps and run IDs are provenance and may differ. Regression comparisons must report sample sizes and limitations; repeated attempts from one family are not independent tasks.

## Live providers

Live providers are optional and require an explicit approved run plan, bounded case/retry/output counts, timeout, concurrency, and conservative spend ceiling. Start with a small development subset and a dry-run/configuration check. Unknown pricing blocks paid scheduling unless an operator supplies a conservative bound labeled as such. Ollama is supported through `MODELLAB_OLLAMA_ENDPOINT`; OpenRouter is supported through `OPENROUTER_API_KEY` and the optional `MODELLAB_OPENROUTER_ENDPOINT`. Both adapters preserve provider-reported token metadata, never invent cost, and fail closed when configuration is absent. Never run paid calls from CI or the default offline commands.

## Authorized development-only live pilot

The committed operator template is intentionally invalid and contains no
commercial authorization. Copy it to an access-controlled location outside the
repository, then supply three to five supported `ollama:model[:revision]` or
`openrouter:model[:revision]` candidates, a dated same-currency rate card with
the declared units, positive per-model and total ceilings, an explicit
operator identity/date/maximum-spend authorization, and the required
development-only declarations.

```bash
.venv/bin/python -m model_lab pilot validate-input \
  --input /secure/operator-input.yaml --suite benchmarks/seed_cases.jsonl
.venv/bin/python -m model_lab pilot plan \
  --operator-input /secure/operator-input.yaml \
  --constraint-map docs/live_pilots/router-constraint-map-v0.2.0.json \
  --out /secure/pilot-plan.json
.venv/bin/python -m model_lab pilot show /secure/pilot-plan.json
```

The first plan is exactly 36 train cases. With three candidates and two
repeats it has 216 base calls; the plan displays retry-inclusive maximum calls
and conservative spend bounds. `pilot run --allow-paid` displays all frozen
source, constraint, model, pricing, and case-set hashes plus exact cases,
retries, judge/red-team options, and ceilings before it can call a provider.
Do not run it without the owner's explicit authorization. The prepared first
runner requires `concurrency: 1`, disables judge/red-team calls, and retains
the full reservation when provider usage/cost is unknown.

After an actual pilot, run only the prepared evidence gates: reconcile provider
usage against local provider-expense reservations without replacing unknowns,
grade with protected oracles, export calibration-only blind review material,
record explicit calibration policy selection, consume holdout exactly once only
after the policy/config hashes are frozen, and generate router shadow replay.
These gates cannot edit the application router.

## Blind-review and grading CLI

```bash
.venv/bin/python -m model_lab review export --db lab-data/demo/model_lab.sqlite3 --run run-synthetic-good --out /tmp/review.jsonl
# Complete selected rows with decision/reviewer_pseudonym/score/confidence.
.venv/bin/python -m model_lab review import --db lab-data/demo/model_lab.sqlite3 --run run-synthetic-good --in /tmp/review-completed.jsonl
.venv/bin/python -m model_lab grade --db lab-data/demo/model_lab.sqlite3 --suite benchmarks/seed_cases.jsonl --run run-synthetic-good
```

Grade persistence is idempotent: existing grade IDs are reported as already present rather than overwritten.

## Evidence locations

Use a disposable `lab-data/` directory for SQLite and raw artifacts, and a disposable `reports/` directory for generated outputs. Keep raw attempt records alongside their source hashes and run manifests. Record actual commands, exit statuses, observations, and skipped/manual-blocked checks in the release handoff; do not mark external provider/channel checks passed from fake data.
