# Project agent instructions

Read PRD.md, Architecture.md, Rules.md, Phases.md, Design.md, Tier_Entitlements.md and Agent_Team.md. Merge these instructions with any existing repository instructions; preserve user work and protected configuration.

The user explicitly requests parallel agents: one Boss/main thread (Sol High), one Supervisor (Terra Medium), and up to three scoped workers (Luna Medium). Verify effective runtime capabilities and model IDs. Use custom roles when supported; never pretend an unavailable model or agent was used. See Agent_Team.md and codex-examples/. No recursive worker spawning.

Boss owns architectural decisions, integration, acceptance/rejection and root Memory.md. Supervisor independently recommends accept/rework/block based on the exact candidate; workers cannot approve their own code. Boss never waives failed security, isolation, financial correctness or data-integrity gates by assertion.

Workers require task cards, disjoint ownership and targeted validation. Preserve changes with a recoverable local commit or durable patch before releasing a worktree. Supervisor remains read-only; Boss stores its review. Shared migrations, contracts and lockfiles are integrated serially.

Create Memory.md only when implementation begins, not during specification work. Record verified state, evidence, decisions, blockers and next actions. Do not create a second memory.md. No secrets or invented completion. Read memory on resumption and verify against Git/code.

Four SUBSCRIPTIONS: ananta/free, yanta/entry paid, trika/advanced, part/premium. Model routing, customer entitlements and development-agent roles are separate. Enforce context limits AND atomic financial budgets before provider spending. Every final retry is evaluated; unresolved output never becomes successful by default.

Run automatic and manual gates in Phases.md and Model_Testing_Spec.md. Real manual device/provider/payment checks require recorded observations; do not mark them passed from a mock. Keep real-data, paid API and live outbound actions within existing authorization and explicit budgets.

Do not enable general-purpose WhatsApp AI service without current eligibility evidence for the intended users. Continue the shared backend, internal test interface and eligible app work while that channel is blocked. No unofficial-client workaround.

Maintain durable evidence and complete the selected release scope. Preserve existing changes; no destructive Git commands, production deployment/migration, real customer messages or live charges without authorization. Local tests and reversible fixes should proceed autonomously. Report implemented, tested, blocked, release-ready and deployed separately.
