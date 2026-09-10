# Copy-Paste Prompt — Build the Linux Model Testing Lab

You are the Boss implementing a model comparison and routing evidence laboratory in the existing project repository. Read `Model_Testing_Spec.md`, `benchmarks/README.md`, `benchmarks/seed_cases.jsonl`, repository instructions and the current application architecture. Treat this as an implementation task: complete working code, automatic tests, a manual walkthrough, sample reports and a documented handoff. Do not claim any real provider benchmark ran unless it did.

## Goal

Build a Linux shell application that imports model outputs and aggregate reports, runs controlled experiments when explicitly authorized, grades observable outcomes, supports blind human review, and produces clear comparisons and draft router recommendations. The user needs at least 50 genuinely different prompts; start with the supplied 60 actual cases, 4 complexity levels and 15 daily workflow domains. Preserve Ananta, Yanta, Trika and Part as subscription names; they are not model identifiers.

## Team

Use a Boss for scope, decisions and final acceptance, one read-only Supervisor for independent review, and 2–3 bounded workers. Where the host actually supports per-agent model selection, request Sol High for Boss, Terra Medium for Supervisor and Luna Medium for workers. Resolve real available identifiers; never invent a supported option. If the runtime only supports one model or manual threads, report that limitation and still preserve the roles through the available mechanism. A role label does not change the underlying model.

Delegate useful independent scopes: ingestion/storage; grading/analysis; CLI/reports. Boss owns integration files and final verification. Each worker owns explicit files and runs targeted checks. Supervisor identifies failures with evidence and sends them to Boss; Boss rejects or accepts each change against acceptance criteria and sends rejected work back for repair. Never accept a worker's unsupported claim of success.

Before worker termination, ensure work is durably handed off by an allowed local commit or a patch outside disposable worktree storage, or by confirmed integration into the main checkout. Preserve all pre-existing changes. Use one canonical `Memory.md` only after coding begins, with Boss as sole writer; record baseline commit, work-in-progress, decisions, evidence, blockers and next action. Read it for continuity, but verify current Git state rather than treating it as proof.

## Baseline and boundaries

Inspect branch/HEAD, working-tree changes, existing Python tooling, runtime instructions and available tests. Reuse appropriate established libraries. Prefer Python, Typer, Rich, Pydantic, SQLite, pandas, Plotly and Matplotlib if there is no conflicting project standard; verify compatibility and lock actual installed versions. Do not bulk-upgrade the application, rewrite existing services, overwrite user reports, expose secrets, create cloud infrastructure, run paid providers, send messages, publish, push, merge or deploy without authorization for that action. Complete useful local work while external gates are blocked.

## Required implementation

1. Validated suite, case, run, attempt, grade, provenance, budget and report schemas. Raw observations are immutable; derived analytics are reproducible.
2. Candidate input export strips all answers, grading notes and split metadata. Tests must prove references never reach the candidate adapter.
3. JSONL and mapped CSV output import, plus explicit aggregate-report import. Unknown latency/tokens/cost/model revisions remain null with provenance. Aggregate statistics never become synthetic individual cases. Quarantine malformed/mismatched records and detect duplicate imports.
4. SQLite persistence, deterministic fake provider, configurable provider adapter interface and resumable jobs with bounded concurrency. Live adapters can be implemented using official APIs, but no paid execution without explicit budgeted authorization.
5. Shared spend reservation, per-request output/attempt limits, cancellation, per-attempt billing, unknown provider outcome tracking and clean budget stopping. A timeout never establishes free usage or failed external action.
6. Deterministic JSON/math/schema checks where the answer is actually checkable; explicit rubrics and blind human review for semantic correctness. Optional model judges need separate budget, provenance and human calibration. Do not fabricate an accuracy percentage from stylistic checks.
7. Matched-case paired comparison, category/context coverage, cost per verified success, latency samples, critical failures, abstentions, family-aware uncertainty and declared scoring weights. Report insufficient evidence visibly.
8. Full suite validation and family/split leakage detection. Preserve family identity across paraphrases/translations/numeric/context variants. Expand family coverage before using the small seed split for router acceptance.
9. Terminal summaries, standalone escaped HTML, Markdown, JSON and CSV reports plus PNG/SVG charts. Include quality-by-domain heatmap, quality/cost frontier, latency distribution, context comparisons and missing-metric coverage; skip unavailable charts with an explanation rather than inventing values.
10. Draft router candidate recommendations with evidence, limitations and eligibility constraints. Never auto-promote models or modify production routing/subscription policies.

11. A deterministic context-fixture builder for measured 2k/8k/16k/32k conditions where supported, including beginning/middle/end evidence, distractors, corrections and multi-source synthesis. Persist seeds, source manifests and actual tokenizer counts; variants keep their original family split. Compare full context with bounded retrieval and summaries. Keep model-only, retrieval-pipeline and routed-system comparisons separate, with fixed-model baselines and total harness cost.
12. A reviewed mapping path for plain-text/Markdown reports, alongside typed CSV/JSONL. Preserve raw source/hash and extraction provenance; require confirmation for ambiguous prompt matching. Unsupported PDF/image inputs are reported honestly or retained as evidence until a verified extractor exists. Never invent trials from aggregate reports or upload private reports to external judges by default.
13. An optional, pinned Promptfoo adapter. Export frozen candidate-only Promptfoo test/configuration manifests from a ModelLab run plan; invoke Promptfoo only through the lab's approved-plan/budget path; import versioned Promptfoo result artifacts as raw attempts; then grade them with ModelLab's protected oracle. Do not inspect undocumented Promptfoo storage as the primary interface. Capture Promptfoo version, config hash, command outcome, redacted provider settings and timestamps.
14. Make oracle/split leakage impossible in candidate export, Promptfoo config and provider request capture. Quarantine altered prompt hashes, unknown/duplicate case IDs and incomplete artifacts. Promptfoo assertions may check stated properties, but only canonical grading drives quality scores and router evidence.
15. Add a separately scoped Promptfoo security/red-team workflow for nonproduction test targets. It requires synthetic/authorized data, declared attack scope, separate cost reservation and reports security results separately from product-quality metrics. Never run it automatically against production.

## Working CLI

Implement and document practical commands equivalent to the specification: init; suite validate/inspect/export; import; plan; run; grade; blind review export/import; compare; report; router recommend --draft; audit. Ensure shell commands work from a clean environment after following installation instructions. Add `--help`, meaningful exit codes, predictable output directories and safe path handling. Do not require an online service for synthetic/import workflows.

A paid plan must display cases × repeats × candidate calls, permitted retries, optional judge calls, model names, output limits, maximum concurrency and conservative total cost bound before execution. Unknown pricing must block paid execution unless a conservative explicit bound is supplied. The default provider for tests/demos is fake. Avoid infinite retry loops and silently increasing budgets.

## Verification

Write meaningful tests for malformed imports, unknown metric handling, duplicate import idempotency, unsupported modalities, reference leakage, family split leakage, known-correct and known-wrong answers, score abstention, HTML escaping, deterministic reports, concurrent budget reservations, timeout-after-success, cancellation and recovery. Tests involving remote providers must be separately marked and opt-in. CI must pass without credentials or internet. Add fixture-based Promptfoo adapter tests proving hidden evaluation data is absent, artifact hashes/case mapping are reconciled and live invocation cannot occur without an approved paid plan.

Complete a local end-to-end run with at least two explicitly synthetic model result sets covering all 60 cases; inject known differences/errors to prove reports are meaningful. Include one local Promptfoo-shaped fixture artifact that passes import/reconciliation and one deliberately tampered artifact that is quarantined. Synthetic outputs must be labeled visibly in files, reports and handoff. Never name them as real provider measurements.

Create `MANUAL_TESTING.md` with concrete commands, inputs, expected outcomes and evidence locations. Walk through import → validation → grading → blind review → analytics → report → draft router recommendation. Include opening the standalone HTML, checking at least one chart against its CSV values, confirming missing latency remains unknown and checking a deliberate arithmetic failure and verifying that the generated Promptfoo candidate config contains no reference, rubric or split field. If the environment cannot perform a step, record it as blocked rather than passed.

Stop optional test expansion once acceptance is sufficiently verified; fix actual defects before broader features. Do not make voice or a web dashboard a dependency of the Linux MVP.

## Final handoff

Deliver runnable code, locked dependencies, supplied/expanded benchmark suite, tests, manual guide, schema/import examples, sample synthetic reports and operational documentation. State what changed, how to install/run it, exact automatic/manual verification results, unresolved limitations, whether any paid calls occurred, and the next authorized gate. Update `Memory.md` with accepted/rejected worker outcomes and final evidence. Do not call the lab production-ready if recovery, budget enforcement, reference isolation or meaningful grading remain unverified.
