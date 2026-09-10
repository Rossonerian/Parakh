# Phases — Build, Verify and Release

Status: executable sequence. Core v1 includes phases 0–8. Consumer PWA/voice phases 9–11 are separately gated scope. If WhatsApp eligibility fails, phase 0 explicitly selects whether the owned app becomes the initial channel; do not call a blocked WhatsApp deployment complete.

## Operating protocol for every phase

Boss assigns bounded tasks and file ownership, Supervisor independently reviews diffs and evidence, specialists implement and perform targeted checks. Boss integrates and makes acceptance/rework decisions with written reasons. Use `Agent_Team.md` or equivalent delivered team guide for model/capability limitations and durable handoffs. All code-changing workers must provide a persistent commit or patch outside disposable worktrees before release. Do not run broad test suites redundantly in each worker.

At each phase record baseline commit/status, requirement IDs, changed files, automatic results, manual evidence, skipped checks/blockers, migration impact, rollback path and Boss decision. Preserve uncommitted work; use isolated worktrees when beneficial. Create `Memory.md` only once coding begins, with Boss as sole writer. Worker notes are proposals until integrated. Memory records current state and evidence locations, not secrets or unsupported claims; immutable Git history remains the authority.

Manual results are `PASS`, `FAIL`, or `BLOCKED`, with actual observation, timestamp and environment. Never convert a proposed checklist into a claimed pass. Use disposable synthetic fixtures and provider sandboxes. Live provider spending, external messages, migrations and deployment obey explicit session authorization and `Rules.md`; complete all safe preparation first if approval is required.

## Phase 0 — Intake, scope and feasibility

Deliver: repository map; verified baseline; applicability of local instructions; dependency inventory; existing authentication/storage architecture; scope decision; initial requirement matrix; launch dependencies; selected pilot segment and model-provider shortlist. No application rewrite at intake.

Verify current WhatsApp/selected BSP terms, primary general-purpose AI eligibility, target geography/country-code rules, consent and reminder delivery rules. Current official terms checked 2026-09-09 restrict general-purpose AI primary functionality outside the stated EEA/Brazil country-code exception; an India-first plan is blocked pending an eligibility decision. See [official terms](https://www.whatsapp.com/legal/business-solution-terms). Retain WhatsApp feature-disabled; no BSP workaround assumption. Boss may approve owned-app-first scope explicitly.

Automatic gate: existing safe lint/type/unit checks run against exact baseline, with failures attributed; secret scan configured without reproducing secrets; environment validation classifies unset required limits as errors.

Manual gate: fresh checkout/local setup instructions reproduced where infrastructure permits; operator verifies access to provider sandbox, identity provider and selected channel eligibility evidence. Missing access is recorded rather than invented.

Exit: scope and protected behavior recorded; baseline failures distinguished; policy dependency has a decision owner. Rollback: no changes beyond intake documents/config stubs unless explicitly justified.

## Phase 1 — Contracts, data and deterministic local harness

Deliver: canonical schemas, modular ownership, migrations, synthetic fixture data, service health/readiness, provider stubs, inbox/outbox skeleton, request/run/error contracts. Start `Memory.md` now when first code changes begin.

Automatic gate: clean database bootstrap and upgrade from baseline; contract validation; transaction rollback; fixture isolation; liveness/readiness dependency-failure tests.

Manual gate: start local stack using documented command; confirm healthy services; submit a signed synthetic event through the local adapter; find one persisted request ID and queued record; stop/restart worker and observe recovery. No real customer data or external send.

Exit: reproducible local path with source-of-truth persistence and no provider cost. Rollback: revert new application slice; reversible migration or tested restore procedure documented.

## Phase 2 — Identity, subscriptions and finite budgets

Deliver: verified identity/channel linkage, roles, plan policy versions for Ananta/Yanta/Trika/Part, distinct context/output/rate/period budgets, transactional reservations and ledger, billing sandbox integration, exact reset display.

Automatic gate: cross-user access denial; forged tier ignored; duplicate/reordered billing events; parallel budget reservation; reset boundary/timezone; downgrade/cancel policy; unknown actual provider usage; cached/reasoning token double-count prevention; provider-fault customer-unit refund without erased internal cost.

Manual gate:

1. Sign in as customer A and create a private note fixture; customer B cannot read it by ID.
2. Activate Yanta through sandbox event; refresh to see entitlements; replay event and see no extra credit.
3. Use a deliberately tiny test allowance and issue concurrent requests; total reservations remain within account and platform caps.
4. Exhaust allowance; observe exact reset and no chargeable gateway call after denial.
5. Simulate suspicious phone-link claim; it cannot inherit another account's memories.

Exit: REQ-ID/PLAN/COST/BILL core tests pass. Rollback: disable new ingress/checkout and retain ledger history; never delete money events to reverse a release.

## Phase 3 — ModelLab baseline and provider gateway

Deliver: CLI offline import/validation/report flow, at least 50 versioned unique prompts per compared model, task/context/difficulty coverage, run manifest, provider gateway test doubles and optionally explicitly authorized live runs. Follow `Model_Testing_Spec.md` for schemas and required reports.

Automatic gate: malformed imports, missing outputs, unit mismatches, duplicated run rows, stale rates, absent provenance, formula-injection-safe exports, numerical aggregation, repeatability, incomplete coverage and judge failure all handled. Reports do not synthesize missing model answers or assert causal superiority from uncontrolled runs.

Manual gate:

1. Run CLI help/setup and validate a supplied fixture dataset.
2. Import two fixture models, including one incomplete model; report shows incomplete coverage and missing cells.
3. Generate HTML/CSV/JSON/chart outputs and inspect labels, denominators, units and accessible colors.
4. Change a rate version and verify only cost comparison changes, while raw outputs remain immutable.
5. If authorized, run a small paid smoke subset under an explicit currency cap; compare ledger with provider usage.

Exit: reproducible baseline and empirical router evidence format. Zero-model live results are labeled fixture/offline only. Rollback: previous CLI package and immutable dataset versions retained.

## Phase 4 — Context and evidence-based routing

Deliver: scoped recent history, traceable summaries, explicit durable memory, filtered retrieval, token packing, model eligibility table, interpretable routing policy and reason codes. Seed policies come from actual evaluation results or are explicitly provisional.

Automatic gate: relevant needle recall at several context sizes; stale/contradictory facts; missing evidence; current request oversized; deletion propagation; cross-scope retrieval; tokenizer budgets; no capable model; provider unavailable; plan exclusion; reserved planning/execution costs; adversarial retrieved instructions.

Manual gate: save two distinct users' task facts; ask each for their own fact; ask an unknown question and get an honest missing-info response; edit/delete a fact and confirm later responses follow current source; ask an oversized analysis and see an explicit narrower-scope/deferral response. Inspect a redacted routing trace showing actual source IDs, token totals and eligibility reason.

Exit: context improves continuity without invented recall; router explanations match executed model. Rollback: version routing/context policy, switch back while preserving compatible stored records.

## Phase 5 — Bounded execution and useful actions

Deliver: drafts, supplied-text analysis, note/task/reminder tools, backend permissions, action receipts, evaluator decisions and bounded repair/escalation. Reminder scheduling is locally testable while live channel sending stays eligibility-gated.

Automatic gate: schemas, tool argument validation, action authorization, exact logical idempotency, timeout-after-remote-success reconciliation, cancellation, limits across retries, generator/judge disagreement, final failed escalation, missing-input clarification, worker crash and durable outbox replay.

Manual gate:

1. Request a short draft with three explicit constraints; verify output and allowance consumption.
2. Create/edit/complete one task; resend original webhook; exactly one intended task exists.
3. Schedule a synthetic reminder for a near-future local time; verify correct UTC storage and test-adapter delivery.
4. Force a model format failure, then repair; trace includes both provider costs but one documented customer task unit.
5. Force both initial and escalated candidates to fail; user gets a clear incomplete/blocked response, never a success claim.
6. Simulate unknown remote action after timeout; the harness reconciles rather than repeating it blindly.

Exit: representative PRD journeys pass; execution cannot loop or overspend. Rollback: disable affected tools/policy version; retain action receipts and reconcile in-flight runs.

## Phase 6 — Channel, admin and usable release experience

Deliver: signed webhook integration, ordering/deduplication, delivery state, billing/usage screens, admin investigation views, accessible UI and customer limit/failure copy. Live WhatsApp flows require documented eligibility; otherwise use simulator and build explicitly approved initial owned-channel surface.

Automatic gate: forged/replayed event, out-of-order messages, provider send timeout, outbox loss/recovery, server-side admin roles, session/logout, redacted errors/logs, screen keyboard/accessibility checks and responsive behavior.

Manual gate: customer sees correct subscription/reset after refresh; keyboard-only operator finds a failed run without viewing unnecessary raw content; simulate delayed delivery and verify generated vs delivered distinction; send two rapid corrections and confirm the newer instruction is respected. Only if expressly eligible/authorized, use a controlled test recipient to verify inbound text, reply and compliant reminder delivery; record delivery receipts.

Exit: UI and channel reflect actual state; policy-blocked checks remain `BLOCKED`. Rollback: feature flags disable live adapter/checkout independently; previous admin build restorable.

## Phase 7 — Integration, resilience and production readiness

Deliver: one integrated release candidate, dependency and security review, observability dashboards, alert runbook, retention/deletion controls, backup/restore evidence, finite production config, abuse limits, model outage policies, model/tier cost analysis and load profiles.

Automatic gate: full required suite once after integration; migration bootstrap/upgrade; ownership/adversarial tests; concurrent spend; queue/model/DB outage recovery; realistic load with measured latency, backlog and cost; no unbounded list/query/run; dependency findings triaged by actual exposure. Broad retries only to resolve specific failures.

Manual gate:

1. Restore a backup into an isolated environment and verify fixture ownership, task state and object references.
2. Delete a test customer's memory/content, then check retrieval/index/cache behavior and documented backup handling.
3. Disable one provider; verify bounded approved fallback or transparent deferral.
4. Stop Redis/worker and recover accepted work without duplicate actions.
5. Follow runbook to identify a synthetic incident and toggle a failing capability off.
6. Compare representative and heavy-user serving costs with proposed prices, margin assumptions and free-pool cap.
7. Reproduce complete onboarding → task → reminder → usage → upgrade sandbox → exhaustion → reset journey.

Exit: Supervisor issues evidence-backed findings; Boss resolves release-blocking defects. Labels are `READY_FOR_DEPLOYMENT`, `BLOCKED`, or `NOT_READY`. “Ready” requires applicable gates to pass; no unsupported perfect-accuracy claim. Rollback: exact previous release/config/migration strategy rehearsed; breaking migration requires tested restore/forward recovery.

## Phase 8 — Authorized deployment, pilot and completion

Prepare deployment artifacts and reviewable release report first. If authorization is absent, stop at deploy-ready handoff and identify the specific approval boundary; do not ask before completing safe preparation. Unavailable credentials/infrastructure are explicit blockers.

After authorized deployment: verify actual domain/TLS, production secrets management, readiness, migrations, monitoring, error alerts, finite budgets, verified channel flags and selected payment mode. Run small synthetic production smoke tasks under authorized costs/recipients. Pilot with a controlled cohort; inspect real success, support, spend and latency rather than extrapolating from fixtures.

Manual gate: one complete authorized live journey, one real delivery verification where eligible, one billing lifecycle in approved mode, and one operator rollback exercise appropriate to the environment. Confirm no fixture customers/messages leaked into production.

Final handoff: exact branch/commit, deployment URL/version if deployed, completed requirement map, actual automatic/manual evidence, migration/rollback notes, known risks, run commands, incident instructions, model/pricing policy version, and roadmap exclusions. `DEPLOYED` requires observed deployment; `LIVE_VERIFIED` requires actual smoke evidence. If WhatsApp is blocked, state that clearly even if the alternative app is live.

## Phase 9 — Consumer app/PWA (v1.1 unless explicitly promoted)

Build linked account chat, streaming with finalization state, usage/reset display, history/projects, preference controls and richer accessible responses. Preserve shared budgets and memory scope across channels. Verify reconnect, duplicate send, mobile keyboard, cancellation, logout and cross-channel concurrency. Manual gate: begin an authorized conversation in one channel and continue in the linked app; unrelated account receives no history. Feature completion requires device/browser evidence, not only responsive screenshots.

## Phase 10 — Voice notes (v1.2)

Add asynchronous ASR, transcript provenance, language handling, audio retention and metered optional TTS. Reserve audio/model costs first. Confirm uncertain dates/amounts/action targets before execution. Verify noisy/empty/multilingual audio, file limits, failed transcription, partial uploads and deletion. Manual gate includes actual consented audio examples and measured end-to-end latency/cost. Do not infer voice quality from text benchmarks.

## Phase 11 — Native/realtime/integration expansion (separate decision)

Proceed only with validated demand, viable unit economics and defined release scope. Native UX, interruption/turn detection, streaming audio, background behavior, external tools and any additional commercial plans require their own PRD delta, benchmarks, security review and release gates. Four launch tiers remain unchanged unless an explicit product decision approves expansion.
