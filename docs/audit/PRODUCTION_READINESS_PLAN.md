# Complete ModelLab audit and production-readiness plan

Updated 2026-09-26. User selected **existing ModelLab release**, not implementation of the larger Daily AI Agent product. Baseline `27fa8ac8a9bc4bead43fe3e442d5c5b5c9985dbc`; branch `codex/production-readiness`. Historical September 21 audit conclusions are not current acceptance evidence.

## Scope: every tracked-file category

| Surface | Required audit / remediation | Exit evidence |
| --- | --- | --- |
| Root specifications, acceptance/manual guides, README, Memory, agent examples | Map lab requirements to code/tests, future product exclusions, stale claims and operating boundaries | Requirement matrix and corrected release docs |
| Schemas, benchmarks, domain, storage, compatibility shims | Immutable nested records, family split isolation, prompt/model/run bindings, transactional budgets, concurrency and interruption | Adversarial contract/ledger tests |
| Operator input, pilot, constraints, execution, Promptfoo | Actual context limits, retry-inclusive spending, immutable plan validation, repeat-launch budgets, CI/live isolation | Fail-closed regressions; explicit unsupported live gates |
| Providers | Credential destinations, redirects, bounded transport, protected payloads, provider identity/usage, retry classification | Mocked transport regressions; separate authorized live gate |
| Grading, analysis, routing | Strict deterministic equality, unknown/failed outcomes, paired coverage, family-aware uncertainty, condition/critical eligibility | Numerical and evidence-integrity tests |
| Imports, human reviews, post-pilot evidence | Timestamp/provenance truth, aggregate separation, mapped CSV, review/attempt linkage, reconciliation completeness, adjudication | Tampered/incomplete input tests |
| Reports, pipeline, CLI | Documented end-to-end workflow, safe HTML/CSV/Markdown, coverage/cost/latency/context/critical views, entry points | Subprocess E2E and artifact inspection |
| Tests, Makefile, CI, packaging, .gitignore, .jules | Clean install/build, reproducible supported runtime, fixture-only network guard, release target, secret/dependency hygiene | Clean environment checks and CI parity |
| Protected source snapshots/manifests, historical pilots, handoffs/tasks/audits | Hash validity, source provenance, archived/current distinctions, recoverability and exact review candidate | Complete file inventory and preserved originals |

## Ordered execution and release gates

1. Record clean baseline, Git fingerprint, runtime/model capability evidence and baseline tests. Inventory every tracked file and map every lab requirement.
2. Reproduce findings; prioritize security, isolation, financial and data-integrity failures. Add regression tests, not just assertions of safety.
3. Implement disjoint provider/evaluation/review slices. Boss integrates shared schemas, storage, budgets, CLI and docs serially. No recursive workers. Commit durable candidates before release of workers.
4. Run focused checks during development, then one integrated offline release suite per candidate. Verify installed CLI/build, synthetic manual walkthrough and backup/restore without paid traffic.
5. Obtain independent read-only Supervisor review of exact commit/tree. Store verdict and evidence. Boss cannot waive failed safety gates by assertion.
6. Publish implemented/tested/manually-observed/blocked/release-ready/deployed separately. Never claim fake provider observations as live proof.

## Authority and limits

Local implementation and reversible synthetic validation are authorized. No paid/live requests, customer data/messages, deployment, production migration or charges are authorized. Missing provider-specific tokenizer/context enforcement and aggregate authorization controls must prevent dispatch, not merely appear in documentation. Actual provider comparisons require approved candidates, current pricing/context evidence, explicit budget and recorded observations. Full application auth/billing/UI/channels and WhatsApp eligibility are outside the selected ModelLab release.

## Team and durable recovery

Requested Supervisor `gpt-5.6-terra`/medium and workers `gpt-5.6-luna`/medium were accepted by the spawn API; effective model metadata was not exposed. No claim that the Boss runtime was changed is made. Supervisor is read-only; Boss owns decisions and Memory. Baseline Supervisor tests: 77 passed, compileall and release target passed; this did not prove production readiness.

Candidate commits `d048b2f` and `b21b9fd` preserve initial provider/evaluation work, not acceptance. An external reset at 2026-09-26 10:39 IST removed pending integration; user explicitly authorized restoration. Subsequent slices are committed promptly. Source originals and unrelated user commits remain protected.

## Deliverables / remaining work

- Complete file/requirement coverage inventory and priority-ranked findings with evidence/status.
- Integrated fixes, focused regression tests, recoverable commits, truthful operation/release docs and compact Memory.
- Exact offline/manual evidence, Supervisor recommendation and explicit release decision. Live execution remains blocked until its safety and observation gates are genuinely satisfied.
