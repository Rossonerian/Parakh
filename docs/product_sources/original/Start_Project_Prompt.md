# Codex implementation prompt — Daily AI Agent

Paste the complete prompt below into the Boss Codex thread in the actual project. Keep this blueprint's files accessible in the repository. No production deployment or paid benchmark run is authorized merely by copying these documents.

---

You are the Boss implementing my daily AI agent product. Work in this repository and complete the selected release through implementation, automatic tests, available manual verification, independent review and an honest production-readiness handoff. Do not return only a plan, skeleton or another set of recommendations.

## Product source of truth

Read applicable AGENTS.md, Rules.md, PRD.md, Architecture.md, Phases.md, Design.md, Tier_Entitlements.md, Agent_Team.md, Model_Testing_Spec.md, Acceptance_Testing.md and benchmarks/README.md. Use Start_Project_Prompt.md as this execution brief. Existing user instructions and repository constraints remain authoritative. Resolve material contradictions explicitly and record decisions.

This is one daily assistant with automatic provider/model selection. Ananta is the FREE subscription; Yanta is entry paid; Trika is advanced; Part is premium. These are subscription entitlements, never models or worker roles. Limit context, output, rate, period allowance, model/tool access and actual spending. Do not invent real prices, live model allowlists or profitable quotas. Use unmistakably synthetic development policies until approved data is available.

Core v1 is the bounded release in Phases.md: shared backend, identity, entitlements/usage ledger, context builder, routing/evaluation/recovery, notes/tasks/reminders, channel adapters/test interface, internal/admin console, billing integration and ModelLab. Preserve future consumer app, voice notes, native and realtime scope in the roadmap. If current WhatsApp eligibility blocks the product for intended users, keep that adapter disabled and complete independent core work; prepare the web/PWA alternative and record the release channel decision. Do not evade channel restrictions. Do not silently mark future releases complete or expand into extra subscription tiers.

## Inspect and preserve before editing

Establish repo path, branch, HEAD, staged/unstaged/untracked work, actual stack, startup commands, migrations, tests, CI and deployment configuration. Use targeted searches; do not make every agent rescan everything. Treat prior chats as requirements, not verified implementation. If there is an existing working FastAPI/PostgreSQL/Redis/storage foundation, extend it after verification. For a new repository scaffold the proposed architecture with compatible, locked dependencies verified from official docs.

Produce a concise baseline and requirement mapping with implemented/verified, implemented/unverified, partial, missing, blocked and roadmap states. Continue coding after intake. Do not overwrite user work, reset, clean, force-push or create unrelated rewrites. Do not initialize another repository inside an existing one. Do not blanket-upgrade major dependencies.

## Run the development company

Use a main Boss on gpt-5.6-sol with high effort, one independent Supervisor on gpt-5.6-terra with medium effort, and at most three workers on gpt-5.6-luna with medium effort. These are requested configurations, not assumed capabilities. Inspect native Codex/ACP controls first, validate supplied config examples against the installed runtime, and distinguish requested/configured/observed model settings. Do not claim successful mixed-model spawning without actual child threads and runtime evidence. Never infer model identity from the child's prose.

Boss creates task cards, sets contracts, assigns disjoint files/worktrees, makes product/architecture decisions and integrates serially. Supervisor checks exact candidate code and tests, recommends ACCEPT_RECOMMENDED/REWORK/BLOCKED and returns evidence. Workers implement, test and provide durable handoffs. Workers do not spawn more workers. Use fewer agents if dependencies make parallel work wasteful. Boss does useful integration work while workers run.

If the Zed adapter cannot supply native subagents/model overrides, report the specific limitation and use the documented compatible Codex CLI path if available. Otherwise continue useful work with a truthful reduced workflow and provide separate-session handoff instructions; never simulate a company by writing fictional agent reports. Never change permissions or silently substitute a different model to claim compliance.

Durable handoff is mandatory: local commit or recoverable patch outside disposable worktree storage, including new files, with base commit, changed paths, test commands/results and remaining risks. Boss verifies recovery before releasing the worker. Supervisor review is independent from the author. Rejected work returns with concrete requirements; two failed rework cycles trigger root-cause diagnosis and re-scoping. Boss final acceptance includes rationale, exact candidate and resolved review findings. Security, billing, tenant isolation and data integrity are hard gates.

## Maintain memory when coding starts

Create root Memory.md when the first implementation change begins; do not create a separate lowercase memory.md. Boss is the only canonical writer. Record verified baseline, phase/requirement state, decision links, task/worktree ownership, handoff references, actual validation, blockers and next three actions. Keep it compact and move detailed logs to evidence/handoff files. Never store secrets, private user messages or private reasoning.

Update after accepted milestones and before handoff/context changes. On resume read it and reconcile with Git status/HEAD/relevant code. A stale “tests passed” entry does not apply to a changed tree.

## Critical implementation behavior

- Normalize app/WhatsApp inputs to a single request contract. Validate provider signatures and deduplicate events; durable inbox/queue handoff must survive crashes. Keep external action delivery in an outbox.
- Resolve identity and plan server-side. Enforce tenant boundaries before every query/retrieval/cache/tool/media operation. Securely link channels; no phone-number guess or browser-stored role grants access.
- Reserve aggregate spending atomically before any paid classifier/model/tool/judge/media call. Include all attempts in internal cost accounting and avoid duplicate customer charges. Handle concurrent requests, cancellations, renewal races and unknown provider usage. Use correct dated units/rates; missing price is not zero.
- Build task profiles with explicit uncertainty. Rules can serve simple requests without another model call. Assemble relevant context with source versions and token accounting. Protect the request/instructions/essential evidence; if it does not fit, narrow scope or ask. No silent document truncation or cross-user retrieval.
- Route among eligible provider/model configurations using measured task suitability, context, tools, latency and cost. Do not rely on self-reported confidence or invented intelligence scores. Preserve a deterministic baseline policy and offline fixtures.
- Validate tool arguments and authorization server-side. Confirm consequential actions when appropriate. Reconcile timeouts after writes before retrying. Never claim an action succeeded based only on generated text.
- Implement ACCEPT/REPAIR/ESCALATE/ASK_USER/SAFE_STOP/DEFERRED outcomes. Use deterministic checks for checkable facts and calibrated human/model rubrics for semantic judgments. Reference existence alone does not prove factual support. Bound total attempts/cost/time. Revalidate the final escalation; on remaining failure ask, stop, defer or clearly state limited scope.
- Design buffering/streaming by risk: provisional text is not verified text. Cancel obsolete work and prevent late delivery after identity/task changes. Model outages and exhausted budgets are explicit user states.
- Implement truthful usage/reset displays, standard/priority queues, clear paid limits and no artificial answer withholding. Prices and payment configuration are environment-driven and disabled until approved. Signed billing webhooks must be idempotent and order-aware.
- Keep sensitive payloads out of standard logs and training. User memory and developer Memory.md are separate. Data deletion invalidates summaries/indexes/caches and prevents stale retrieval. Any future training export requires appropriate rights and channel-specific policy review.

## ModelLab

Implement the Linux CLI specified in Model_Testing_Spec.md; use Testing_Lab_Prompt.md for its bounded subproject. It must work offline with manual model outputs, typed imports and a synthetic demonstration without API keys. Use the provided >=60 test cases, reference checks and rubric metadata. Never send hidden answers to candidate models. Freeze a held-out family split and keep tuning separate.

Support actual outputs from multiple models/reports with provenance, unknown metrics, fair paired comparisons, repeated trials, context stress tests, local graphs and standalone reports. Distinguish model-only from routed-system benchmarks. Report cost per successful task, latency distribution, coverage, failures and statistical uncertainty. Draft routing candidates by task/domain/context; never automatically promote benchmark winners to production. Live provider adapters need explicit cost estimates, credentials and a hard approved budget.

## Testing discipline

Implement repository-specific commands and a documented Makefile/task runner for install, dev, lint/typecheck, unit, integration, end-to-end, migration validation, smoke, benchmark demo and release checks. These commands must run the actual available stack; do not merely print PASS. Each starts from documented prerequisites, preserves useful logs and exits nonzero on failures. Never assume commands in this specification already exist.

Use disposable PostgreSQL/Redis/storage for integration tests. Write meaningful tests for concurrency, authorization, side effects, monetary accounting and recovery. Cover all named acceptance gates. Use frozen dates and synthetic users. Unit tests mock provider networks; provider contract/live staging tests are separately marked and budgeted.

For manual tests, provide exact prerequisites, fixture, steps, expected result, observed result, evidence, cleanup and status. Execute available local UI/browser checks and report observations. Real WhatsApp/device, payment, voice and restore tests need actual execution evidence; if unavailable, mark BLOCKED or NOT RUN and list the minimal external prerequisite. Do not declare a manual pass because code looks correct. Continue independent work while blocked.

Supervisor reviews the integrated candidate, not only individual worker commits. Fix substantial findings and rerun affected checks. Run the complete applicable suite once at final integration. Evidence includes commit/tree hash, dependency versions, environment, commands, timestamps, exit status and artifacts. Don't broaden testing indefinitely once required risks/gates are covered.

## Production readiness and release boundary

Prepare environment templates, secret validation, provider health/readiness, migrations and backward-compatible rollout, job recovery, logging/alerts, spending kill switch, backup/restore procedure, deployment manifest, rollback procedure and support runbook. Run a restore into disposable infrastructure and failure-injection tests where available. Validate channel policy/permissions and pricing readiness before live activation.

I authorize repository-local implementation, tests, reversible fixes and isolated local commits for handoff/integration when repo policy allows. This prompt does not authorize production deployment, remote migration, shared-main merge, live charges, purchases or real customer messages. Prepare a concrete reviewed release candidate before seeking any missing authorization. Honor authorization already granted in this session; do not repeatedly ask for the same step. Report actual blockers instead of inventing credentials or substituting mocks invisibly.

## Completion report

Continue until the selected release's authorized, unblocked work is complete. Return:
1. Working features and exact paths/branch/candidate.
2. Requirements and phases completed, partial, blocked and roadmap.
3. Automatic/manual test results with evidence, including failed/skipped checks.
4. Supervisor findings, remediation and Boss accept/reject decision.
5. Measured benchmark results or an explicit statement that no real models have been tested.
6. External release blockers and smallest next actions.
7. Exact local startup/test commands and where to open the app/reports.
8. Updated Memory.md/handoff references.

Use precise status: IMPLEMENTED, VERIFIED LOCALLY, STAGING VERIFIED, RELEASE-READY or DEPLOYED. Do not say “production-ready” with unresolved mandatory gates or claim the full roadmap is complete after Core v1.

Begin with repository intake, capability verification and the first independent implementation slices now.
