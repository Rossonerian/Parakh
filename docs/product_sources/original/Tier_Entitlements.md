# Tier entitlements and cost policy

Draft engineering policy • 2026-09-09. Four subscriptions: Ananta (free), Yanta, Trika, Part. Prices, paid allowances, provider lists and production spending ceilings require measured costs and owner approval. No model is selected by subscription name alone.

## Two views of the same plan

| Plan | Customer value | Internal allocation |
| --- | --- | --- |
| Ananta | Useful everyday assistance with a finite free allowance | Compact working context; economical eligible models; small funded rescue reserve |
| Yanta | Regular daily work, more continuity, tasks and reminders | Higher usage/context limits; operational tools; broader eligible model pool |
| Trika | Longer analysis, documents and multi-step workflows | Larger evidence budget; more advanced calls and selective verification |
| Part | Highest included capacity, advanced workflows and priority | Widest evaluated pool; larger request caps; deeper verification where useful |

Access to correct identity handling, private data isolation and truthful action status is shared across all plans. Customers upgrade for useful capacity. Conversion to Yanta is a hypothesis to measure, not an assumption that all free users will pay. Track activation, retention, upgrade conversion, task success and support cost by cohort.

## Required versioned configuration

Every plan version defines: `plan_id`, display label, validity dates, price/currency (null until approved), billing interval, request-rate/burst limit, per-user concurrency, period start/end policy, everyday allowance, Deep Task allowance, working-input cap, output cap, allowed model IDs, tools/features, document bytes/pages, voice seconds, durable-memory/storage retention, queue class, request cost cap, period cost cap and rescue pool policy. Set both customer-visible entitlements and separate internal cost protection.

A development-only example may use input ceilings of 4k/8k/16k/32k tokens and output ceilings of 512/1024/2048/4096. These are test fixtures, not release quotas or benchmarked recommendations. Provider context windows and minimum viable evidence further constrain them. Tokenizers differ. Include tool schemas and evidence in token counts. Store retained history separately from working context.

Production startup refuses unconfigured pricing/entitlements when paid checkout is enabled. Offline fixtures work without prices or API keys. Unknown provider rates block cost-based live routing until resolved; a model's cost must not silently become zero.

## Admission before execution

Use a fixed cheap preflight estimate/rules step locally. Before any paid classification or provider operation, atomically reserve its worst-case bounded cost against request, user-period and global budgets. Follow-on operations extend the reservation before starting. Concurrent requests cannot independently spend the same remaining allowance. A lease expiration is not evidence a timed-out remote call was free.

Track distinct ledgers:
- Customer usage: the published charge for the logical request, with reservation, settlement, refund and reset records.
- Provider expenses: every attempt, tool, judge, retrieval, transcription, synthesis and delivery charge incurred, even on user-visible failure.

Use transactional idempotency keys for admission and settlement. Charge a logical request once; compensate failed service according to the documented customer policy, not by deleting real provider costs. Reconcile unknown usage. Keep period boundaries explicit and fixed; resetting everyday capacity must not reset accumulated financial spend incorrectly.

## Correct units

Text cost in a single currency = `(uncached_input_tokens × input_rate_per_million + cached_input_tokens × cached_rate_per_million + billable_output_tokens × output_rate_per_million) / 1,000,000`, adjusted to each provider's actual billing schema. Add separately billed categories only when not already included. In particular, do not count reasoning tokens twice if included in output usage. Voice/media may have seconds, minutes or tokens as billing units; preserve the actual rate unit and date.

Total variable expense also includes classifier, embeddings, retrieval/search, repair, escalation, judge calls, channel charges and attributable compute/storage. Track payment fees and support/hosting allocations separately for plan economics. A context cap alone cannot cap total monthly cost.

For scenario planning: contribution per subscriber = net subscription receipts − variable service expense. Evaluate p50 and heavy-use cohorts, free-user subsidy, conversion uncertainty, regional costs, failures, currency changes and acquisition/support overhead. Break-even scenarios must carry assumptions; they do not justify claiming profitability.

## Exhaustion and recovery

If Deep Tasks are exhausted but everyday capacity remains, permit a genuinely smaller task. Explain excluded scope before treating it as complete. If no eligible model can meet a request, ask to split, wait until the actual reset, or select an optional top-up/upgrade. Do not force repeated prompts as a paywall. Never retry indefinitely or spend premium capacity just because the free model is uncertain.

Use one bounded repair and one escalation as a provisional aggregate policy; not every request receives both. An escalation may use a stronger eligible model or an explicitly budgeted rescue route. Apply all checks again. If it still fails, return a limited result or a clear unresolved state. No automatic billing changes. Budget exhaustion is a normal state with a usable error contract.

## Subscription lifecycle

Signed, idempotent billing webhooks update versioned entitlements. Handle duplicates, out-of-order renewal/cancellation events, pending payments, refunds, expired subscriptions and scheduled downgrades. Backend derives access from trusted billing state. Avoid resetting usage on every plan edit. Define upgrade proration and allowance carryover before checkout; do not invent provider behavior.

Use the same identity and allowance across app and WhatsApp after secure account linking. Channel-specific charges may justify different included delivery allowances; advertise them plainly. Do not imply app use is cost-free. Cancellation and deletion have separate financial and data-retention consequences.

## Activation gates

Before setting real plan limits: run ModelLab comparisons, select a small validated provider pool, measure end-to-end success/cost under representative workloads, stress concurrent budgets, simulate heavy users and set a global daily emergency stop. Record model/policy versions and evidence. Customer-facing price/limits and provider eligibility must be reviewed before payments/live channel launch.
