# Architecture — Daily AI Agent

Status: proposed design. Confirm the actual repository, instructions and deployed baseline before editing. FastAPI, PostgreSQL, Redis and MinIO were reported in prior conversation; no current repository inspection establishes them here. Preserve working architecture until intake evidence justifies changes. Pin supported dependency versions and provider APIs during implementation; do not infer versions from past assistant messages.

## 1. Structure and ownership

Use a modular monolith initially, with separately runnable workers. One backend owns identity, subscription policies, context, execution and cost accounting across channels. Avoid microservices until isolation or scaling evidence requires them.

Proposed components:

- Python/FastAPI API and workers; typed request/response validation; SQLAlchemy/Alembic if compatible with the inspected baseline.
- PostgreSQL as source of truth. Redis supplies queues/cache/rate acceleration, never the only record of customer balances, action state or accepted work.
- S3-compatible object interface; retain existing MinIO locally if verified. Production storage selection is an explicit operational choice.
- A small responsive TypeScript admin application, using existing frontend conventions or a deliberately chosen supported stack. Consumer PWA is a later release unless required as the compliant initial channel.
- Model gateway with provider adapters, explicit model IDs/capabilities, rate versions and test doubles. Use a compatible SDK only after evaluating it; avoid forcing every provider into lossy common token fields.
- ModelLab as an independently runnable Python CLI package with versioned data contracts; plotting/data libraries chosen and pinned at intake.
- Existing verified authentication provider preferred. If absent, choose maintained OIDC/session infrastructure; implement application authorization without inventing a home-grown password system.

```text
repository/
  AGENTS.md
  docs/
    PRD.md
    Architecture.md
    Rules.md
    Phases.md
    Design.md
    Agent_Team.md
    Model_Testing_Spec.md
    decisions/
    runbooks/
    release-evidence/
  Memory.md                 # Boss creates only after coding begins
  apps/
    api/app/
      identity/
      subscriptions/
      accounting/
      ingress/
      context/
      routing/
      execution/
      evaluation/
      tools/
      channels/
      admin/
      observability/
    admin/
    web/                   # v1.1 or approved initial-channel pivot
  workers/
    ingress/
    execution/
    reminders/
    outbox/
    reconciliation/
  packages/
    contracts/
    model_gateway/
    model_lab/
  migrations/
  tests/
    unit/
    integration/
    contracts/
    security/
    e2e/
    fixtures/
  ops/
    local/
    deploy/
```

Adapt to existing folder names; this tree describes ownership and is not permission for a repository-wide move. The supplied blueprint keeps its planning documents at the package root; either retain those locations or update all references together if the existing repository uses docs/.

## 2. Request lifecycle

1. **Authenticate ingress.** Verify signature against raw provider payload with official adapter semantics; reject unknown origin/replay outside applicable policy. App clients use verified sessions. Link phone identity through a secure claim flow, never a client-submitted phone number alone.
2. **Durably accept.** In one transaction record an inbox event with a unique provider/message ID and work-to-enqueue record; acknowledge promptly after durable acceptance. A dispatcher publishes jobs; duplicate queue delivery is expected and harmless.
3. **Resolve policy.** Load account scope, subscription policy version, retention consent, available tools, usage windows, rate and concurrency limits. Check platform channel eligibility feature flag before live sending or processing policy-restricted traffic.
4. **Reserve planning capacity.** Before chargeable classification/embedding work, atomically reserve a bounded planning allowance against account and platform budgets. Cheap deterministic checks can reject exhausted requests first. Reservations have owners, limits and reconciliation state; expiry alone cannot permit overspend while a call is still running.
5. **Profile the task.** Rules extract size, modality and obvious action intent. A small classifier is optional for ambiguity; its cost is accounted. Produce intent, required capabilities, context needs, dependent steps, freshness, missing fields, risk flags and confidence/unknown state. Classifier confidence is not a correctness guarantee.
6. **Build scoped context.** Retrieve only account-authorized sources, count tokens with the selected candidate tokenizer, preserve provenance and report missing evidence. Never retrieve broadly and hope the model filters other users' records.
7. **Choose execution policy and reserve.** Filter plan allowlist, capabilities, observed quality by task, context fit, region/privacy restrictions, health and cost limits. Choose lowest expected total execution cost meeting empirically calibrated task requirements, including probable failures/retries. Atomically extend reservation for chosen execution, bounded recovery and tool charges. If impossible, clarify, scope down with consent or defer.
8. **Generate/execute.** Send typed context and allowed tools through gateway. Enforce per-call and total run limits. Validate every proposed tool action outside the model. Required confirmation depends on action consequences and product authorization, not model confidence.
9. **Evaluate.** Produce `ACCEPT`, `REPAIR`, `ESCALATE`, `ASK_USER`, `SAFE_STOP`, or `DEFERRED`, with explicit evidence and reason. No repair/escalation without a remaining permitted budget.
10. **Deliver.** Commit the accepted answer/appropriate terminal message and an outbox entry atomically. Deliver via channel adapter with tracked provider status. A response can be generated but undelivered; show that distinction operationally.
11. **Settle.** Reconcile provider usage and actual costs against reservation; release unused amounts and apply documented public usage-unit rules once. Late provider usage adjusts the internal ledger without duplicating a customer action. Derived memory updates require provenance and consent.

## 3. Internal contracts

```json
{
  "request_id": "uuid",
  "account_id": "server-resolved",
  "conversation_id": "uuid",
  "channel": "whatsapp|web|internal_test",
  "source_message_id": "provider-unique-id",
  "policy_version": "immutable-policy-id",
  "task_profile": {
    "intent": "draft|recall|task_action|reminder|analysis|unknown",
    "required_capabilities": [],
    "missing_fields": [],
    "risk_flags": [],
    "classification_source": "rule|model|human"
  },
  "execution_limits": {
    "max_input_tokens": "configured integer",
    "max_output_tokens": "configured integer",
    "max_calls": "configured integer",
    "max_tool_calls": "configured integer",
    "deadline_ms": "configured integer",
    "cost_ceiling_minor_units": "configured integer"
  }
}
```

The above illustrates fields, not valid production JSON values for numeric fields. Enforce strict schemas, validated integer units and immutable server-derived limits. Do not pass internal money ceilings as instructions the model is expected to enforce.

## 4. Context algorithm

Compute usable input capacity as `min(plan request-input cap, model total context - output reservation - provider overhead/safety reserve)`. Reasoning-token semantics vary by provider; consult its accounting rather than assuming every token counter adds independently.

Candidate sources: current request, exact recent messages, rolling summaries, user-approved durable facts, relevant notes/tasks, supplied text chunks and recent authoritative tool results. For each keep source ID, version, ownership, creation/update time, confidence or fact status and deletion generation.

Retrieve using filtered lexical search first where adequate; introduce embeddings/hybrid retrieval only with measured benefit. Rank by relevance, explicit reference, recency when appropriate and source authority. Numerical relevance scores are retrieval aids, not truth probabilities. Contradictory current records beat stale derived summaries only when supported by documented source precedence; otherwise ask.

Token-pack mandatory instructions/current request and essential evidence first; include the most useful remaining chunks until cap. Compress with traceable summaries, preserving negation, amounts, deadlines and uncertainty. Count summarization cost. If indispensable material cannot fit, ask for focus, process explicit bounded chunks with aggregation validation, or disclose that the plan cannot complete full scope. Do not silently trim decisive evidence.

Persist conversation history separately from active context. Memory retention and per-request context are different policies. Deletion propagates to summaries, embeddings, caches and downstream extracts; backups follow documented expiry/restore safeguards. Retrieval cannot claim absence of a fact as proof it never existed.

## 5. Routing and evaluation

Maintain registry rows keyed by exact provider/model/version/config. Store modality/tool support, effective validated context, pricing source/date, retention restrictions, health and evaluation dataset version. Metrics are empirical distributions by task and context bucket, not invented permanent intelligence scores.

Initial routing can be interpretable rules and an evaluation lookup table. More expensive meta-routing or learned routers require enough labeled traffic to justify operational complexity. Higher paid tiers widen eligible models/context/work budgets; baseline classifier and permission correctness remain shared.

Evaluation layers:

- Deterministic: valid JSON/schema where requested, required fields, known arithmetic, scope, tool result references, redacted secrets, bounded output and explicit task constraints that are machine-checkable.
- Evidence-aware: check claimed actions against durable action receipts and current source values. Citation existence is machine-checkable; whether a source truly supports nuanced prose often requires semantic evaluation or a human.
- Selective model judge: task rubric, blinded candidate where practical, per-dimension evidence and uncertainty; calibrate against human ratings. Judge and generator can share biases. Scores are signals, not proof of truth.
- Human/clarification: inherently subjective preferences, missing inputs, ambiguous authority and consequential unsupported conclusions need explicit handling.

Do not use one weighted score to override a failed mandatory dimension. A polished unsupported factual answer cannot pass because style is strong. Simple rewrites need lightweight checks; tool actions need outcome validation; complex analysis may need a paid judge within its reservation.

| Decision | Required transition |
|---|---|
| ACCEPT | Commit answer only after mandatory checks pass |
| REPAIR | Same-model format/constraint correction if eligible; re-evaluate |
| ESCALATE | Stronger eligible model or better context route if failure evidence supports it; re-evaluate |
| ASK_USER | Store pending task and ask one useful clarification; no claim of completion |
| SAFE_STOP | Stop prohibited, unauthorized or unverifiable consequential action; safe explanation |
| DEFERRED | No permitted budget/capability/time; expose actual partial result and reset/next option |

Every rejected answer is classified again against remaining policy limits. The provisional policy allows at most one repair and one escalation after the initial answer, subject to the aggregate call/time/cost ceiling; fewer attempts may be affordable. Exhausted recovery terminates, defers or asks for input. There is **no edge from exhausted escalation directly to successful delivery**. Provider fallback is distinct from intellectual escalation; never retry unauthorized actions on a less restrictive model.

## 6. Accounting and concurrency

Use immutable ledger events plus transactional balances/reservations in PostgreSQL. Enforce account, plan-window and global spend budgets together in a transaction with appropriate locks or atomic conditional updates. Prevent parallel web/WhatsApp requests from each spending the same remaining allowance. Currency amounts use integer minor/micro units or exact decimals, never float money.

Calculate normalized cost from explicitly disjoint billable categories:

`cost = sum(billable_quantity_i × rate_i / rate_unit_i) + fixed_request/tool/channel charges`

Retain provider raw usage. If total input includes cached input, split cached and uncached portions rather than billing both total and cached again. If output includes reasoning, do not add reasoning twice. Model hidden/unknown metering as unknown/pending and reconcile conservatively. Attach provider/model, request ID, rate version, currency, timestamp and measurement source. Cached responses/retrieval can reduce model spend but still incur other work.

Separate provider expenditure, public usage units, and subscription revenue. Provider/network failures may cost money even when customer units are refunded; retain both facts. Reset windows are explicit UTC instants with customer display timezone; avoid timezone-based repeated reset exploits. Downgrades update policy prospectively without erasing consumed usage.

## 7. Tool and delivery reliability

Every logical action gets a stable idempotency key derived from the intended action identity, not a fresh key per retry. Persist `prepared`, `executing`, `succeeded`, `failed`, `unknown` and reconciliation evidence. Where provider idempotency is supported, use it. Where it is not, inspect remote state or surface uncertainty; an HTTP timeout is not evidence an action failed.

Use durable inbox/outbox records and workers with leases/fencing appropriate to implementation. PostgreSQL is authoritative if Redis loses data. Recovery scans stranded jobs and undelivered outbox entries. Per-conversation sequencing and optimistic versions prevent later user corrections being overwritten by stale responses. Cancellation/account deletion blocks new operations and marks in-flight results for authorized handling.

## 8. Data model and API boundaries

Primary tables/modules:

- `accounts`, `users`, `memberships`, `channel_links`, `sessions` or provider references.
- `plan_versions`, `subscriptions`, `billing_events`, `entitlement_overrides` with expiry/audit.
- `usage_windows`, `budget_reservations`, `cost_ledger`, `customer_usage_ledger`, `rate_versions`.
- `conversations`, `messages`, `context_summaries`, `memory_items`, `memory_sources`, `deletion_jobs`.
- `notes`, `tasks`, `reminders`, `reminder_deliveries`.
- `inbox_events`, `runs`, `run_steps`, `tool_actions`, `outbox_events`, `reconciliation_jobs`.
- `model_registry`, `routing_policy_versions`, `evaluation_results`, `audit_events`.
- ModelLab `datasets`, `cases`, `run_manifests`, `observations`, `human_reviews` as versioned artifacts or DB records; real customer content excluded unless explicit approved redaction/consent workflow exists.

Illustrative API surface (final names adapt to repository contracts):

| API | Owner and rule |
|---|---|
| `POST /webhooks/whatsapp` | Adapter signature verification; raw-body semantics; durable deduplication |
| `POST /webhooks/billing` | Billing provider verification; version/order-safe entitlement changes |
| `POST /v1/messages` | Authenticated customer; server resolves tier; idempotency key |
| `GET /v1/runs/{id}` | Owner scope; accurate status and partial/completed distinction |
| `GET /v1/usage` | Own balances, units and reset timestamps |
| `GET/DELETE /v1/memory/{id}` | Own scoped memory and deletion semantics |
| CRUD `/v1/notes`, `/v1/tasks`, `/v1/reminders` | Per-record ownership and version conflicts |
| `/admin/*` | Privileged server-side roles, audit and step-up where appropriate |
| `/health`, `/ready` | Liveness vs dependency readiness; no secrets |

Errors have stable code, safe message, request ID, retryability and optional reset/retry time. Do not leak provider credentials, internal prompts, account existence or raw database errors.

## 9. Future channels and operations

Keep WhatsApp feature-disabled until current policy eligibility is recorded. Official terms checked 2026-09-09 restrict general-purpose AI primary functionality outside a stated EEA/Brazil country-code exception; provisional India deployment must clear this gate. See [official terms](https://www.whatsapp.com/legal/business-solution-terms). Internal simulators and approved app development can proceed.

Owned app sessions share scope, budgets and optional memory with verified WhatsApp links. Voice adapters add metered ASR/TTS or real-time sessions later; speculative transcripts must not trigger irreversible actions, and audio retention must be explicit.

Trace request/run/model/tool/delivery IDs with privacy-minimal logs. Monitor completed-task cost, retries, reservation leaks, queue lag, delivery failures, duplicate suppression, policy denials, p50/p95 latency and evaluated failure rates. Back up source-of-truth DB and objects; test a restore into an isolated environment. Migrations, policy versions, gateway configuration and channel flags need rollback procedures independent from secret rotation.
