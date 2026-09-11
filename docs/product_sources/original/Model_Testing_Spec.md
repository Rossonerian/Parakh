# Model Testing Lab — Product and Engineering Specification

Status: proposed implementation specification, not a claim that the software or any model evaluation has run. The included seed bank contains 60 authored test cases. No paid model calls are authorized by this document alone.

## Objective

Create a Linux terminal application that makes repeatable model comparison fast and inspectable: prepare test sets, import existing responses and reports, optionally execute explicitly budgeted experiments, grade what can be checked, organize human review, and produce model-selection evidence for the daily assistant router.

The lab measures models and execution policies. Ananta, Yanta, Trika and Part remain subscription entitlements; task complexity levels 1–4 are evaluation labels, not plan names or model identities.

## Decisions the lab must support

- Which models satisfy each task category's minimum quality requirements?
- What are the cost, latency, tool reliability and context limitations of those models?
- When does a stronger model, more context, retrieval, or a second attempt materially improve results?
- Which candidate routing policies meet a budget without excluding important workload segments?
- Where is evidence too sparse to recommend any model confidently?

Do not generate one misleading universal intelligence ranking. Provide category views and a quality/cost/latency Pareto frontier. Recommendations are drafts requiring review and production canary evidence.

## Included starting test set

`benchmarks/seed_cases.jsonl` contains 60 actual self-contained prompts: 15 per complexity level, across 15 daily workflow domains. Cases contain oracle answers or checkable rubrics and critical failure criteria. This is a smoke-test baseline; it cannot establish statistical superiority or long-context capability by itself.

The supplied split is 36 development/train, 12 calibration, 12 holdout. There are 15 conservatively grouped workflow families, each containing four complexity variants; the split is 9/3/3 families. Each case has a family ID. Any paraphrase, translation, altered numeric fixture, or long-context version derived from a case inherits its family and split. Domain coverage is currently uneven within each split; add independently authored families to cover every release-critical domain in calibration and holdout before using results for router training or release decisions. Assigning unrelated family IDs to near-duplicate prompts is prohibited.

All seed prompts contain their own source facts. Candidate models receive `messages` only. They must not receive `evaluation`, oracle answers, split labels or grading notes. Graders receive the task, response and a protected evaluation record. A source file containing all fields is acceptable; the candidate adapter must enforce this separation.

## Comparison modes

1. **Controlled batch:** same tasks, fixtures, tool availability, context conditions and explicit generation limits for all eligible models. Record provider differences; identical temperature does not imply identical sampling semantics.
2. **Imported model outputs:** parse JSONL or mapped CSV, preserve original provenance and unknown fields. Never silently fabricate timestamps, token usage, latency, pricing or successful completion.
3. **Imported aggregate reports:** store summaries separately. Do not turn a claimed aggregate score into fabricated per-case observations. Label author, methodology, tested model version, date and unknowns.
4. **Manual review:** blind paired response comparison, rubric scoring, critical error flags, abstention, disagreement and adjudication.
5. **Router replay:** simulate an explicit routing policy against available comparable observations. Missing outcomes remain unavailable; simulation does not demonstrate live performance.

Maintain separate model-only, retrieval/context-pipeline, and complete routed-system runs. In the first, hold the prompt/tools constant; in the others record the entire orchestration configuration and all intermediate paid calls. A context-retrieval failure must not silently become a model intelligence score. Include a fixed-model baseline when comparing routing policies.

For plain-text/Markdown reports, provide a local mapping/review workflow to identify model, prompt, response and provenance. Ambiguous matches require operator confirmation; never reconstruct missing trials from a narrative. PDF/image reports may be attached as source evidence with optional extraction later; unsupported formats get an actionable error, not invented metrics. Do not send imported private reports to external judges by default.

## Recommended implementation

Python 3.12 or the repository's supported Python; Typer for CLI, Rich for terminal output, Pydantic for validated schemas, SQLite for metadata/run records, pandas for analytical transformations, Plotly for standalone interactive HTML, and Matplotlib for static PNG/SVG plots. Use pytest for meaningful tests. Lock dependencies after checking actual compatible versions. Do not force replacements if the existing repository already provides equivalent tools.

Suggested package layout:

```
model_lab/
  cli.py
  schemas.py
  storage.py
  ingestion/
  providers/
  execution/
  grading/
  analysis/
  reporting/
  routing/
  fixtures/
tests/
benchmarks/
```

Provider integration is an adapter boundary. Start with a deterministic fake provider and imported results; support the real providers selected by the project after verifying their official APIs and available credentials. Secrets belong in environment variables or the established secret store, never result exports.

## Promptfoo integration

Integrate Promptfoo as an optional, pinned evaluation-runner adapter. It is useful for declarative multi-provider matrices, assertions, caching/concurrency, local results viewing, CI gates and red-team scenarios. Promptfoo itself supports CLI/library/CI execution and multiple providers. [Promptfoo introduction](https://www.promptfoo.dev/docs/intro/) Its YAML configuration can load tests from YAML, JSON, JSONL or CSV and supports assertions. [Promptfoo configuration](https://www.promptfoo.dev/docs/configuration/guide/)

ModelLab remains canonical for the protected benchmark record, grading, expense ledger, family-aware statistics, human review, router proposal and immutable evidence. Do not use a Promptfoo pass percentage as a deployment or routing decision by itself. In particular, Promptfoo assertions test only the properties they encode; a model judge or similarity score is not proof of answer truth.

**Required boundary:** ModelLab exports a Promptfoo run manifest and candidate-only test inputs. The export contains run ID, case ID, candidate messages, declared generation/context/tool condition, provider aliases and deterministic prompt hash. It excludes `evaluation`, reference answers, rubrics, critical-failure text and split labels. Promptfoo returns response artifacts plus its command/version/config hash, redacted provider configuration, invocation timestamps and exit outcome. ModelLab imports those results as attempts, reconciles case IDs/prompt hashes, then performs canonical grading against the protected evaluation data. A mismatch, missing case, duplicate attempt or altered prompt hash is quarantined.

Do not parse undocumented cache/database internals as the primary contract. Pin the Promptfoo version; use a versioned exported artifact or a tested adapter fixture. Store the original unmodified artifact and a schema-versioned normalized copy. Promptfoo config/provider labels are experiment metadata, not an entitlement or production router allowlist.

Generate one Promptfoo configuration per frozen run manifest. Freeze candidate model IDs, system prompt/template revision, temperature/seed where supported, context fixture revision, tool simulator revision, output cap, timeout and provider-specific options before dispatch. Never compare a model-only Promptfoo run against a routed/RAG/tool-enabled run as if the model were the only difference. Read current provider and Promptfoo semantics at execution time; identical parameter names do not guarantee identical provider behavior.

Promptfoo's own assertions are useful for safe syntax/schema, deterministic fixture checks and explicitly scoped custom checks. Use ModelLab deterministic graders for protected oracles. If a Promptfoo assertion invokes an LLM judge, treat it as a separate paid model attempt with provider/model/version, prompt, rate/budget reservation and correlated-bias disclosure. A Promptfoo red-team run is a distinct security suite: use a nonproduction target, synthetic/authorized data, explicit attack scope and its own budget; report security failures separately from ordinary answer quality.

CI runs fake/fixture Promptfoo artifacts only. Any live Promptfoo provider run requires the same approved plan and `--allow-paid` protection as native ModelLab providers. It must show candidate calls, retries, output caps, optional judge/red-team calls, maximum concurrency and conservative cost ceiling before execution. Neither `promptfoo eval` nor CI credentials authorize a paid or production-targeted run.

## Proposed command surface

These commands are acceptance targets, not commands that already exist:

```bash
model-lab init ./lab
model-lab suite validate benchmarks/seed_cases.jsonl
model-lab suite inspect --group-by domain,complexity_level
model-lab suite export --candidate-only --out ./candidate-inputs.jsonl
model-lab import responses.jsonl --format jsonl --source-label experiment-a
model-lab import responses.csv --mapping mapping.yaml --source-label experiment-b
model-lab import report.json --format aggregate-report --source-label vendor-report
model-lab plan --suite seed-v1 --models models.yaml --repeats 3 --budget-usd 5
model-lab run --plan plan.json --provider fake
model-lab run --plan approved-plan.json --allow-paid
model-lab grade --run RUN_ID --deterministic
model-lab review export --run RUN_ID --blind --out review.html
model-lab review import completed-review.jsonl
model-lab compare --runs RUN_A,RUN_B --paired
model-lab report --run RUN_ID --formats html,md,csv,json,png
model-lab router recommend --run RUN_ID --policy policy.yaml --draft
model-lab audit --run RUN_ID
model-lab promptfoo export --run-plan plan.json --out ./promptfoo/run.yaml
model-lab promptfoo run --manifest ./promptfoo/manifest.json --allow-paid
model-lab promptfoo import --artifact ./promptfoo/results.json --run RUN_ID
```

`--allow-paid` requires an explicit run plan with models, cases, repeats, maximum request/output counts, timeouts, concurrency and spend ceiling. It is an operator acknowledgement, not a mechanism that grants credentials or bypasses existing approval controls. Interactive paid execution asks only when paid work is not already authorized. CI uses the fake provider and cannot execute paid calls accidentally.

## Dataset and result contracts

Case: ID, suite version, immutable family ID, split, domain, complexity, language, tags, candidate messages, limits, evaluation method, reference, rubric, critical failures and provenance.

Attempt: run ID, logical request ID, attempt ID, case ID, resolved provider/model identifier and model revision if supplied, generation settings, prompt hash, prompt assembly version, context condition, timestamps, response text, finish reason, tool traces, status, retry reason, token usage, cache usage, reasoning usage if reported, observed billing and estimated billing, pricing snapshot, currency, and provenance.

Record first-token latency separately from completion latency. Mark not-applicable for imported non-streamed output when first-token timing was never measured. Distinguish measured, provider-reported, imported, estimated and unknown values. Use `null` for unknown; zero means measured zero. Never substitute inferred whitespace word counts for provider token billing without an explicit estimate label and tokenizer identity.

Grades: grader type/version, rule ID, raw evidence, pass/fail/abstain, rubric dimensions, critical flags, judge provider/model when used, human reviewer pseudonym, review date and adjudication state. Keep raw observations immutable and derived reports reproducible.

## Test levels and context experiments

- **Level 1:** direct extraction, short drafting, arithmetic, simple intent and basic ambiguity handling.
- **Level 2:** a few constraints, calculations, corrections, basic policy application and simple tool planning.
- **Level 3:** dependent steps, conflicting sources, constrained scheduling, reconciliation, memory provenance and recovery.
- **Level 4:** infeasibility proofs, multiple interacting constraints, partial side effects, evidence uncertainty and robust decisions with missing information.

Complexity labels are hypotheses and can be revised after expert review; they do not establish clinical, legal or mathematical certification.

Expand beyond the short seed prompts with measured 2k/8k/16k/32k input conditions only for models whose actual window and output reserve permit them. Tokenize the complete final request per target model. Include relevant information at beginning/middle/end, distractors, stale summaries and contradictory updates. Keep the correct answer and family split unchanged. Also compare full context, bounded retrieval and summary-plus-retrieval using the same task fixture. The provided 60 cases alone contain no validated long-context or audio benchmark.

Tool tests use a local simulator with schema validation, authorization, transient failures, idempotency, timeout-after-success and cancellation. Optional ModelLab voice-comparison suites later use separately licensed synthetic audio with specified transcripts, accents, noise and latency; no voice conclusions from text-only tests. This lab roadmap does not defer Core v1 product speech-input acceptance in Phases.md and Acceptance_Testing.md.

Implement a deterministic context-fixture builder with seed, target size, source manifest and prompt hash. Distinguish simple needle lookup, contradictory-update resolution and multi-document synthesis; success on a single needle does not establish reasoning across long input. Context sizes are measured after prompt assembly for each tokenizer. Persist family identity across expansions and show total estimated requests/cost before running the expanded grid. Unsupported windows are reported as ineligible rather than silently shortened.

## Scoring and uncertainty

Exact JSON cases use a safe schema/equality comparator with explicit rules for extra keys, numeric tolerance and semantic normalization. Rubric tasks use deterministic subchecks where defensible, then blind human review or a separately calibrated model judge. Formatting checks are not evidence of factual correctness. Source support, relevance and coherence generally require semantic evaluation; do not describe these as fully deterministic guarantees.

A rubric must specify whether each criterion is binary or ordinal and define anchors before scoring. Start with binary criteria for the seed bank. Publish the denominator, ungraded coverage and abstention rate. An operational critical failure blocks routing eligibility even if average rubric score is high. A judge must be tested on known good/bad responses and human-reviewed samples; record false acceptance, false rejection and disagreement. If judge and candidate share a model family, disclose the potential correlated bias.

Use paired comparisons on matched cases and conditions. Report observed counts and uncertainty intervals, with the method and unit of resampling. Repeated attempts from one prompt family are not independent new cases: cluster bootstrap or aggregate at family level. Do not imply 60 prompts multiplied by 5 repeats equals 300 independent tasks. A zero-observed-failure result is not a zero-risk guarantee. Predefine primary outcomes and distinguish exploratory slices to limit cherry-picking.

Latency reports show observed sample count and median/p90/p95 where sample sizes permit; otherwise label tail metrics unstable. Cost views show total observed spend, estimated pending spend, completed successes and cost per verified success. Include failed initial calls, retries, judge calls, retrieval, tools, voice and any channel costs actually measured. Separate customer credit debit from internal provider expenditure.

## Budget and failure controls

Reserve worst-case known request cost before dispatch, including output ceilings and paid judges. Share reservations atomically across workers. Unknown pricing prevents paid scheduling unless an explicit conservative operator-supplied bound is configured and labeled. Reconcile reservations with usage once available; retain unresolved amounts when provider outcomes or billing are unknown. A client timeout or cancellation does not prove the provider did not bill the call.

Use bounded retry policies by failure class and exponential backoff with jitter where appropriate. Preserve each attempt. Never blindly retry external side effects. Halt new dispatch on budget exhaustion; return a partial report with complete evidence. A logical task can have several billed internal attempts but one customer-visible charge according to the product's policy.

## Reports and router proposals

Export standalone HTML and Markdown summaries, CSV comparison tables, machine-readable JSON, and static charts. Required views: model-by-domain quality heatmap, cost versus verified success, latency distribution, performance by context condition, critical failures, coverage/unknown metrics, paired differences with uncertainty, and eligible model sets by task. Escape imported HTML/script text.

Draft router output contains task condition, candidate model, observed evidence and coverage, minimum quality/critical requirements, context/modality/tool eligibility, expected cost with assumptions, fallback candidates and unresolved questions. It must not automatically alter production router configuration or subscription entitlements.

## Automatic and manual acceptance

Automatic tests must exercise schema rejection, oracle separation, family split leakage, unknown metric preservation, import idempotency, mismatched-case quarantine, exact answer grading, deliberately wrong arithmetic rejection, tool timeout recovery, atomic spend reservations, cancellation, immutable raw outputs, report escaping, reproducible export and unsupported modality labeling. Promptfoo adapter tests use versioned local fixtures: candidate export contains no hidden evaluation/split data; prompt-hash and case-ID mismatch quarantine works; a result artifact normalizes deterministically; live invocation is impossible in CI; a judge/red-team call is included in planned cost only when explicitly enabled.

Manual walkthrough:
1. Validate the 60-case seed suite and inspect all 4 levels/15 domains.
2. Import two synthetic model result sets containing a deliberate arithmetic error, missing latency, duplicate records and one malicious HTML string.
3. Confirm the erroneous response is marked incorrect, unknown latency stays unknown, duplicates are flagged and HTML is escaped.
4. Blind-review 10 paired cases including disagreement; import the reviews and inspect adjudication.
5. Run the fake provider with deterministic failures and a tiny fake budget; verify clean stopping, complete cost ledger and no paid traffic.
6. Generate/open HTML, Markdown, CSV/JSON and images; reconcile counts with SQLite.
7. Generate a draft router proposal and confirm no production configuration changed.
8. Generate a Promptfoo configuration from a candidate-only manifest; inspect it for absent oracles/splits, import a fixture result and reconcile it to the same ModelLab run.
9. Only after paid authorization, run a small budgeted live pilot and reconcile provider-reported usage against the local ledger. Treat this as a separate evidence gate.

Done means this complete import → validate → grade → human review → compare → report → draft recommendation flow works with the supplied cases and reproducible synthetic fixtures. Provider comparisons remain unverified until actual comparable model runs exist.
