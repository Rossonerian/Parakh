# Rules — Daily AI Agent

Specification v1 • 2026-09-09 • Implementation rules, not evidence of implemented behavior.

## Authority and baseline

Follow the user's current instructions and applicable repository instructions. Read PRD.md, Architecture.md, Phases.md, Design.md, Tier_Entitlements.md and Model_Testing_Spec.md. Preserve a working existing stack after inspection; an earlier chat claiming a feature exists is not proof. Record conflicts and resolve consequential ones through the Boss. Do not override an existing AGENTS.md with this package without merging its relevant instructions.

The canonical subscription IDs are `ananta`, `yanta`, `trika`, `part`, matching the latest user wording. Display labels may change without migrations. These IDs never identify model difficulty, agent roles or providers. Ananta is free; other prices remain unapproved. No invented margins, unlimited plans or model performance guarantees.

## Engineering boundaries

- Prefer a modular FastAPI backend, PostgreSQL transactions, Redis workers and private S3-compatible storage if the repository confirms that foundation. Keep SQLite for the standalone evaluation lab, not the production billing ledger.
- Use typed Pydantic contracts, explicit provider adapters, schema migrations and dependency injection at external boundaries. Adopt the repository's existing job runner; avoid installing several competing agent frameworks.
- For a new web shell, prefer TypeScript, React and one routing framework, Tailwind and an accessible component foundation. Select and lock compatible versions during intake using official documentation. No speculative version upgrades.
- Use maintained authentication and payment implementations; never trust browser storage or a caller-supplied plan/user ID as identity. Reuse a verified existing auth integration where possible.
- Keep provider keys on the server, secrets out of repositories, prompts, browser bundles, screenshots and Memory.md. No consumer subscription cookies or desktop-agent credentials in the product model gateway.
- No arbitrary shell/Python evaluation in the production agent. Tools use narrow typed contracts, server authorization and bounded results. Treat attachments, imported reports, retrieved pages and tool text as untrusted data.
- No shared production/test databases. Use disposable, explicitly named test services. No database cleanup based on a guessed environment name.
- No unsupported WhatsApp Web automation or provider switching to evade channel restrictions. Verify eligibility for the exact product, country and channel before live activation.

## Context and routing invariants

1. Authorize before retrieval. Scope full-text/vector queries, caches, summaries, tool results and media to the authenticated tenant/user/project. Post-filtering after leaking data into the prompt is too late.
2. Treat system instructions, the current request and indispensable task evidence as protected context. If they cannot fit, ask to split the task or explain the limit. Never silently truncate an uploaded document and claim a full review.
3. Record the context manifest: source IDs, versions, timestamps, relevance rationale, tokens and omitted evidence. A summary is fallible derived data; preserve references to originals and honor corrections/deletion.
4. Enforce plan/model/context/tool eligibility before selection. Use a rules-based router first; add a classifier only when measurements justify its cost. Higher tiers provide more capacity/model access, not deliberately defective routing.
5. Model score predictions and judge ratings are uncertain estimates. Never claim universal intelligence or guaranteed correctness. High-risk routes require stronger evidence or appropriate limits, not merely a bigger model.
6. Reserve financial capacity before any paid classifier, retrieval service, model, judge, tool or voice call. Enforce per-request, user-period and global-provider caps across concurrent workers.
7. Hard token caps and output limits must match the provider's actual semantics, including hidden reasoning consumption where applicable. Record provider usage as returned; unknown cost is unknown, never zero.
8. Use bounded escalation only inside the plan or an explicit funded rescue policy. No automatic upgrades, charges or plan changes.

## Evaluation and recovery

Required result states: `ACCEPT`, `REPAIR`, `ESCALATE`, `ASK_USER`, `SAFE_STOP`, `DEFERRED`. An evaluator must give reasons/evidence and identify checks it could not perform.

Deterministic checks prove only their specific properties. Schema validity cannot prove factual accuracy; source presence cannot prove entailment; an LLM judge cannot prove correctness. Do not represent semantic citation checking as a cheap deterministic guarantee.

Allow a maximum of one repair and one escalation by the provisional default, subject to an aggregate request cap that includes all model/tool/judge attempts. Revalidate after each attempt. If the final attempt still fails, ask, defer, give a clearly limited partial result, or stop. Never route an unsuccessful final evaluation to normal success delivery.

Retry read-only transient operations with bounded exponential backoff and jitter. Mutations require stable idempotency keys and outcome reconciliation. A timeout after a calendar/payment/message operation is an unknown result until checked; do not repeat it blindly. The durable result and delivery outbox survive worker restarts. Customer allowance is settled once per logical request under a published policy; the internal ledger includes every billable retry.

Streaming is provisional: content already displayed cannot be withdrawn. Buffer responses requiring pre-delivery checking. Never stream private tool payloads, credentials or unverified action-success claims. A new message or cancellation increments a task generation/version so obsolete work cannot send a late answer.

## Errors and observability

Use stable error codes, correlation IDs and safe customer messages. Classify auth, quota, invalid-input, unavailable-provider, unsupported-capability, ambiguous-action and internal errors. Logs include stage timing, attempt IDs, selected model, config version and numeric usage; raw prompts are opt-in restricted diagnostics. No success on an error path. Distinguish delivery queued, delivered, failed and unknown.

Publish no universal latency guarantee before measuring the whole route. Count classifier, retrieval, queues, retries and delivery separately. Cancellation may not avoid a provider bill; reconcile it.

## Tests and release evidence

Run focused tests for each substantial behavioral change and the integrated release suite once per candidate. Use real disposable PostgreSQL/Redis for transaction, idempotency and concurrency tests. Mocked green tests do not establish production integration.

Required gates: auth/tenant isolation; payment event deduplication; atomic quota reservations; provider timeout/cancellation; context overflow/deletion; tool unknown-outcome handling; evaluator false acceptance; failed escalation; actual UI journeys; app/WhatsApp shared identity where enabled; restore/rollback; missing secret fail-closed behavior. Follow Phases.md for manual tests with expected result and evidence.

Keep model-quality benchmarking separate from software unit tests. Never run paid benchmarks without a declared estimate and configured approved spending ceiling. Synthetic results must be unmistakably marked. Compare imported model outputs only when prompts/configurations are comparable; record unavailable fields as null.

## Agent company and memory

Follow Agent_Team.md. The Boss accepts/rejects changes against evidence; Supervisor independently reviews; workers own bounded files. No self-approval. No unbounded recursive delegation. Keep at most three workers and one Supervisor active alongside the Boss.

Each worker hands off a local commit or durable patch with base commit, changed files, tests and risks before its worktree is released. Boss is the sole writer of canonical Memory.md and integration/shared lockfiles. Workers write separate task handoffs. Keep reviews tied to an exact commit/tree; edits invalidate affected approvals.

Do not create Memory.md during this planning package. When implementation begins, create root `Memory.md` once; on Linux do not also create `memory.md`. It contains verified progress, unresolved decisions, evidence references and next steps, never invented history or secrets. Memory narrows re-reading but never overrides code and Git evidence.

## Git and external actions

Preserve staged, unstaged and untracked user work. Do not reset, clean, force-push, erase history or discard work. Local integration commits on a dedicated branch are permitted for durable handoffs when repository policy allows; never sweep unrelated files into a commit. No push, merge to shared main, production deploy, live payment, production migration, cloud purchase or real outbound customer message without applicable existing authorization. Prepare the concrete release candidate first. Continue independent local work when one external gate is blocked.

Only report production-ready after the defined release gates are evidenced. Distinguish implementation complete, automated checks passed, manual verification pending, staging verified, release-ready and deployed. Do not declare roadmap/native/realtime work complete because the core release passed.
