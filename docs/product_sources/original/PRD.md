# PRD — Daily AI Agent

Status: implementation specification, not evidence of an existing implementation. Owner: product Boss. Core release: v1. Names and prices require product validation; technical limits require benchmark and load-test evidence.

## 1. Product and customer

Build a WhatsApp-first daily assistant that accepts a natural-language request, retrieves relevant permitted context, chooses an appropriate available model automatically, and completes useful everyday work within a transparent subscription allowance. Users should not need to understand provider names or select a model.

Initial audience: individual adults who want help drafting, understanding supplied material, organizing notes and tasks, and setting reminders. Pilot recruitment should focus on one reachable segment rather than claiming universal product fit. The founding hypothesis is that convenience plus reliable workflow completion creates willingness to pay; it remains unproven until measured.

Subscriptions are not model identities. Canonical launch display names are **Ananta**, **Yanta**, **Trika**, **Part**, following the user's latest wording. Stable internal IDs are `ananta`, `yanta`, `trika`, `part`; free/entry/advanced/premium describe commercial positions only. Changing a display label must not change ownership or billing history. Launch with four plans only. No price, entitlement, conversion rate, accuracy guarantee, or profitable margin is established by this document.

## 2. Release boundaries

### Core v1 — required for completion

- One shared orchestration backend; WhatsApp text ingress/egress through a policy-compliant provider adapter.
- Secure customer identity, channel-account linking, subscription entitlements, usage accounting, reset times, and four finite plans.
- Conversational help, short drafting and rewriting, analysis of supplied text, private notes, tasks, reminders.
- Automatic model routing, context selection, bounded execution and recovery, transparent inability/allowance responses.
- Operational/admin web console: customers, plans, usage, queue health, model policies, redacted run traces, subscriptions, controlled support actions.
- Billing integration appropriate to the selected geography; sandbox evidence before live acceptance of money.
- ModelLab command-line benchmarking: datasets, external-output import, provenance, repeatable comparisons, charts and exportable reports, linked to `Model_Testing_Spec.md`.
- Automated verification, concrete manual pilot gates, observability, backups, operational runbooks, and release evidence.

### Later releases — do not silently include in Core v1 completion

- v1.1: consumer responsive web app/PWA, streaming, project views, richer files and usage controls; shared entitlements and linked conversations.
- v1.2: asynchronous voice notes, transcription review for consequential actions, metered synthesis if useful.
- Later, separately approved: native applications, real-time interruptible voice, broad third-party integrations, collaboration/team plans.

Do not build custom foundation models, medical diagnosis, unrestricted browser agents, autonomous purchases, or arbitrary shell execution for customers in Core v1. Research/search is optional until provider availability, citation support, cost and need are verified. Without fresh sources the bot must not claim current external facts.

## 3. Launch dependency: channel eligibility

**REQ-CH-001:** Before committing to a WhatsApp launch, verify current official WhatsApp Business terms and the selected provider's rules for general-purpose AI assistants, relevant geography, outbound messaging and consent. Save URLs, checked date, applicable wording summary, reviewer and decision. This document does not assert that this product is permitted.

As checked on 2026-09-09, the official terms restrict AI Providers from supplying general-purpose AI as primary functionality, with a scoped exception for users registered with EEA or Brazil country codes. The provisional India market is outside that stated exception. Keep this product’s WhatsApp launch disabled pending a documented eligibility decision; a BSP does not itself remove the restriction. [Official terms](https://www.whatsapp.com/legal/business-solution-terms). This is a launch dependency assessment, not a final legal determination.

If blocked, Core v1 implementation and isolated tests may continue, but WhatsApp launch must be marked blocked. Boss chooses an expressly compliant scope or promotes the owned app/PWA as the initial channel; do not disguise the product or circumvent enforcement. Scheduled reminders depend on the verified permitted template/session workflow; a stored reminder is not proof it can be delivered.

## 4. Requirements and acceptance

| ID | Requirement | Acceptance evidence |
|---|---|---|
| REQ-ID-001 | Resolve a verified user and account scope before retrieving private content or calling tools | Cross-account and mismatched-link tests deny access; linking cannot be claimed with a phone number alone |
| REQ-ID-002 | Separate service/admin privileges from customer access | Server-side policy tests and admin session/authentication checks; no UI-only authorization |
| REQ-PLAN-001 | Resolve versioned plan policy server-side | Client-supplied tier ignored; active/past-due/cancelled transitions tested against documented policy |
| REQ-PLAN-002 | Distinct request context, output, rate, period usage and monetary limits | Each limit independently exercised; no token-limit claim substitutes for a cost ceiling |
| REQ-COST-001 | Atomically reserve finite spend and capacity before chargeable execution | Parallel requests cannot overspend the user's or platform's configured remaining budget; interrupted reservations reconciled |
| REQ-COST-002 | Record actual model, router, judge, retrieval, tool, channel and media costs where known | Rate version and units persisted; unknown cost flagged, never counted as zero; replay causes no duplicate customer charge |
| REQ-CTX-001 | Compile a token-bounded context with source IDs, ownership and timestamps | Relevant recall, stale/contradictory memory, unanswerable query and deletion tests; missing facts are not invented |
| REQ-CTX-002 | Explain and control durable memory | User can inspect/delete supported memory; derived summaries/indexes follow deletion; new sessions cannot retrieve deleted content |
| REQ-ROUTE-001 | Select among plan-eligible capable models using evaluation evidence and live availability | Routing replay reports selected policy/model/reason, out-of-distribution status, estimated cost and fallback |
| REQ-ROUTE-002 | Offer useful limited scope, clarification or explicit deferral when no eligible route exists | No silent paid-tier access, unlimited retries or premium guarantee; reset timestamp displayed when relevant |
| REQ-EXEC-001 | Bound calls, tools, input/output, wall time and spend per request | Timeout, agent loop and provider error tests show enforced caps and terminal states |
| REQ-EXEC-002 | Validate permissions and arguments independently of model output | Adversarial tool argument and retrieved-prompt injection cases cannot cross scope or execute forbidden operations |
| REQ-EVAL-001 | Evaluate with deterministic checks, source checks and selective calibrated judges | Accept/repair/escalate/ask/stop/defer reason codes covered; second failure does not bypass evaluation |
| REQ-ACT-001 | Private notes/tasks and reminders support explicit CRUD operations | Completed action responses match durable records; duplicate delivery produces at most one logical action |
| REQ-ACT-002 | Handle uncertain external actions without blind replay | Timeout after remote success becomes unknown/reconciliation state; duplicate reminder or charge prevented |
| REQ-CH-002 | Handle signed webhook duplicates, ordering, retries and delivery status | Invalid signature denied; duplicate event idempotent; process crash recovers; reply delivery failures visible |
| REQ-BILL-001 | Billing events update a server-owned subscription ledger | Signed, duplicate, reordered and stale sandbox events tested; no entitlement based solely on checkout return URL |
| REQ-ADMIN-001 | Admin can investigate without default raw-message exposure | Scoped roles, redacted traces, audit trail, controlled sensitive-content access and support expiry |
| REQ-LAB-001 | Compare models on at least 50 unique versioned prompts per compared model | Results disclose completion/coverage; skipped/missing cases cannot improve average; separate scored categories and context sizes |
| REQ-LAB-002 | Import user reports/data without fabricated measurements | Schema validation, provenance, units, missing values, partial uploads and formula-injection-safe exports tested |
| REQ-OPS-001 | Fail safely during dependency/model outages | Readiness, circuit breakers, bounded retries, queued recovery and operator runbooks exercised |
| REQ-PRIV-001 | Encrypt traffic, protect stored data and minimize retention | Secrets absent from code/bundles/log samples; scoped retrieval and deletion evidence; backup retention documented |
| REQ-UX-001 | Show task state, limits, reset time and accurate completion status | User can distinguish queued, working, needs input, deferred, completed and failed; no artificial delay of finished answers |

## 5. Subscription policy

All amounts remain configuration proposals until selected from real cost measurements. Treat `unset` production money limits as deployment-blocking, not unlimited. All plans have baseline permission checks, essential output validation and honest failure handling.

| Entitlement | Ananta / free | Yanta / entry | Trika / advanced | Part / premium |
|---|---|---|---|---|
| Commercial role | Finite discovery/pilot allowance | Useful everyday paid plan | Heavier analysis and workflows | Highest supported capacity |
| Context/input/output | Small finite configured caps | Larger configured caps | Extended configured caps | Largest validated caps |
| Eligible models | Economical evaluated pool | Broader pool | Advanced pool | Widest approved pool |
| Deep-task/compute usage | Small finite reserve | Regular allowance | Higher allowance | Highest finite allowance |
| Recovery | Essential bounded recovery | Larger permitted budget | More verified depth | Highest permitted depth |
| Tools | Safe basic subset | Routine workflows | Additional approved tools | Broadest approved tools |
| Queue | Standard | Standard | Higher priority when justified | Priority, no guaranteed instant results |
| Future media | Metered trial if offered | Metered | Larger allowance | Largest allowance |

Yanta must independently deliver useful recurring value. Do not assume everyone will pay or use intentional errors, hidden throttling or confusing balances to force conversion. Higher plans may obtain genuinely better analytical results from stronger models, more context and verification; no plan can guarantee correctness.

Everyday/Deep Task counters are public product units. They must map predictably to bounded internal execution policies. Define whether a unit is reserved or consumed, treatment of cancellations/provider faults, exact reset timezone and timestamp, rollover, downgrades and refunds before launch. Internal route repairs do not appear as duplicate customer tasks; their actual costs still belong in the service ledger.

## 6. Representative journeys

1. **Draft:** user asks for a short polite reply. Resolve budget; include relevant prior sentence only; use economical eligible model; check basic constraints; deliver and settle usage.
2. **Recall:** user asks for a saved appointment. Retrieve scoped authoritative note, with date/timezone; ask if conflicting or missing. Never manufacture a remembered appointment.
3. **Task action:** user asks to add an item. Validate intent/fields; backend creates one scoped task using an idempotency key; confirm only the committed result.
4. **Reminder:** parse local time and ambiguity; ask when needed; persist schedule; dispatch through authorized policy-compliant channel; distinguish saved from delivered.
5. **Complex comparison:** identify required supplied material, context and work. Select an eligible validated model; if outside allowance, explain available reduced scope or reset/upgrade without returning a misleading incomplete conclusion.
6. **Allowance exhausted:** display remaining applicable pools and exact reset; offer wait or supported simpler request. Never execute expensive work first and discover there is no budget later.
7. **Provider timeout:** preserve run state; reconcile possible actions; use eligible fallback only within budget and with required checks; disclose incomplete work if recovery ends.

## 7. Success measures and economics

Measure real task completion, audited error rates, user-reported usefulness, repeat usage, paid retention, support requests, costs per completed task, retry amplification, routing regret, p50/p95 latency, and category-specific quality. Segment by tier, model, task, context size and channel. Do not use message volume alone as success.

Compute cost from provider-metered billable units and versioned rates. Distinguish gross revenue from tax, payment fees, refunds and other deductions; compute contribution after inference, tools, channel and variable serving costs. Set free-pool and platform daily/monthly ceilings. Stress-test heavy users, abuse and provider pricing changes; final tariffs require measured typical and upper-tail usage plus an explicit commercial margin target.

Prototype targets become release thresholds only after baseline measurement and product approval. Reports must show denominator, sample sizes, missing observations and uncertainty. No invented benchmark scores or conversion assumptions.

## 8. Definition of done

Core v1 is complete when every Core v1 requirement has linked implementation and evidence, required automatic/manual gates in `Phases.md` pass against the exact release candidate, unit economics and eligibility decisions are recorded, and blockers are explicit. `Production-ready`, `deployed`, and `live-verified` are separate statuses. Deployment and money-spending boundaries follow `Rules.md`; passing a build is not production readiness. Future app/voice/native phases do not invalidate an honestly complete Core v1, and must not be claimed as delivered.
