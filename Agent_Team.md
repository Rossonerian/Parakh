# Agent company — Codex in Zed

Updated 2026-09-10. This configures development agents, independently of the four customer subscriptions and the product's runtime router.

## Team and responsibilities

| Role | Requested model / effort | Responsibility | Decision rights |
| --- | --- | --- | --- |
| Boss (main thread) | `gpt-5.6-sol` / high | Scope, architecture, delegation, integration, risk and release candidate | Accept/reject code based on evidence; sole canonical Memory.md writer |
| Supervisor | `gpt-5.6-terra` / medium | Independent review of changes, contracts and validation | Recommend accept/rework/block; never silently waive a failed gate |
| Workers, up to 3 | `gpt-5.6-luna` / medium | Bounded backend, frontend, tests or lab tasks | Implement owned scope and supply durable handoffs |

This is the user's requested starting allocation. Escalate difficult security/concurrency reviews to a higher-effort review or Boss examination when evidence is insufficient. Do not pretend a cheaper reviewer is independent proof of correctness. The Boss must justify acceptance, particularly when disagreeing with the Supervisor. Code approval cannot override human authorization or platform permissions.

Use one Boss with a flat set of child agents; Supervisor is organizationally above workers but need not spawn them. Boss forwards review feedback to the owning worker. This avoids nested coordination and makes integration ownership clear. The Boss can implement integration work while independent workers run. Do not keep agents alive doing duplicate scans just to resemble a company.

## Verified controls and limitations

Current Codex documents per-agent model/effort configuration and project custom agent TOML files. See [Codex subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents) and [configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference). The included configuration examples follow that documented format. Older installations may require different supported keys; validate against the installed version rather than guessing or disabling safety controls.

The requested model IDs appear in the official [model catalog](https://learn.chatgpt.com/docs/models). Account, sign-in method and client determine access; these files do not grant model access.

Zed's Codex External Agent uses ACP, with agent-native model/auth configuration. Zed's native agent profiles do not automatically govern Codex threads. Start Codex through the ACP Registry/Agent Panel and use its authentication/configuration. Inspect `dev: open acp logs` for integration diagnostics, redacting secrets before sharing. [Zed External Agents](https://zed.dev/docs/ai/external-agents)

No Zed or Codex process from the user's computer was available for testing here. The setup is documentation-grounded, not a claim that the user's installed adapter exposes every capability.

## Windows workstation: recommended operation

Yes: the Boss/Supervisor/worker process works on a Windows machine. Use **WSL 2 with Ubuntu** as the authoritative development environment for Codex CLI, Git worktrees, Python/Node tools and the Linux ModelLab. Keep the repository at `~/src/<project>` inside the WSL filesystem, then open that folder from Windows/Zed through the WSL integration. Microsoft recommends storing Linux-command-line projects under `/home/<user>/...`, not `/mnt/c/...`, for performance and cross-filesystem reliability. [WSL filesystems](https://learn.microsoft.com/en-us/windows/wsl/filesystems)

Install WSL from an elevated PowerShell with `wsl --install`, restart, create the Ubuntu user, and confirm WSL 2 with `wsl -l -v`. [Microsoft WSL installation](https://learn.microsoft.com/en-us/windows/wsl/install) In Ubuntu, install and authenticate Codex using current official instructions, clone or move the repository into `~/src`, then use the existing project `.codex/config.toml`, `.codex/agents/` and `AGENTS.md`. Run the capability-test prompt in this document before starting implementation.

Use one authoritative Git checkout and one toolchain per run. Do not run one worker in Windows PowerShell against `C:\...` while other workers use WSL against the same checkout; line endings, file locks, case behavior, paths and dependency caches can produce false diffs or lost handoffs. Windows Terminal can open WSL tabs; `explorer.exe .` opens the current WSL folder in Explorer. Android Studio/device tooling may remain on Windows when required, but record the boundary and run project commands through WSL unless the project intentionally supports a native Windows toolchain.

Zed on Windows is acceptable if its installed Codex ACP adapter exposes the required child-agent/model controls. It is not proof that it does. If the adapter lacks them, use Codex CLI in a WSL terminal as the canonical Boss session and either use supported native subagents or separate WSL sessions/worktrees with durable task cards. Windows changes the host OS, not the role protocol: Boss retains integration/acceptance, Supervisor stays independent/read-only, and workers hand off a commit or durable patch before termination.

## Setup steps

1. On Windows, complete the WSL setup above and work from the WSL filesystem. Then open the actual project in Zed or a WSL terminal. Inspect existing AGENTS.md and local Codex configuration before merging anything.
2. Confirm Codex is installed as an External Agent through the ACP Registry. Open a Codex thread; authenticate inside Codex. Zed provider credentials alone do not configure it.
3. Check the installed adapter/runtime version and model picker. If a shell Codex exists, `codex --version` is useful, but it may differ from Zed's bundled runtime. Record both when available.
4. Merge `codex-examples/config.toml` into the project's `.codex/config.toml`; copy the example custom agent TOML files into `.codex/agents/`. Do not overwrite existing MCP settings, credentials, permission settings or agent definitions. Merge the supplied AGENTS.md instructions with the repository's existing instructions.
5. Restart the Codex thread if needed to load configuration. Select Sol High using Codex's exposed selector, or confirm that the project default is active. The examples deliberately omit permission relaxations.
6. Perform the harmless capability test below. Only claim mixed-model orchestration if runtime metadata or logs establish the effective models. A worker saying “I am Luna” is not sufficient.
7. Start the implementation with `Start_Project_Prompt.md` after successful capability verification. Workers execute on isolated worktrees where supported; otherwise use explicit disjoint file ownership and serialize shared edits.

## Capability test prompt

```text
Run a read-only capability check in this project. Do not edit files or install packages.
Inspect the active Codex/ACP capabilities and model configuration without exposing credentials.
Use the configured supervisor agent for a short read-only review of PRD.md and one implementation_worker for a read-only review of Phases.md, concurrently if the runtime supports it. Each returns one concrete implementation risk. Collect both results.
Report whether actual child threads were created, their requested model/effort and effective model/effort from runtime evidence when available. Distinguish configured, observed and unknown. Do not infer model identity from an agent's prose.
If custom roles or model overrides are unavailable, report the specific capability gap; do not simulate multiple agents in one response or silently claim the requested model allocation worked.
```

## If the Zed adapter lacks the needed controls

Use Codex CLI in Zed's integrated terminal with the same project instructions and compatible native configuration. A documented invocation for the Boss model is:

```bash
codex -m gpt-5.6-sol
```

Set high reasoning via the supported selector/configuration. Do not assume a terminal command exists if Codex is only bundled with the adapter.

Alternatively open separate supported agent sessions with each model explicitly selected, giving each a distinct worktree. Exchange task cards/reviews through files. This is manual coordination unless an actual orchestration channel connects the sessions; independent Zed threads do not automatically form a shared-memory team. If the requested model is unavailable, preserve the role and ask for a concrete substitute only after identifying available options; never silently remap names.

## Work ownership and review cycle

Each task card records: ID, requirement IDs, base commit, owner/model, exact file ownership, allowed dependencies, input/output contracts, acceptance criteria, targeted tests, estimated bounds and known blockers. Workers must not change another owner's files, shared lockfiles, schema contracts or migrations without Boss coordination.

Cycle:
1. Boss establishes contracts and assigns independent slices.
2. Worker implements and runs meaningful focused checks.
3. Worker provides durable handoff; Supervisor reviews the exact candidate and relevant tests.
4. Supervisor returns `ACCEPT_RECOMMENDED`, `REWORK` or `BLOCKED`, with severity, file, reproduction and required evidence.
5. Boss accepts for integration or returns explicit remediation to the owner. Two unsuccessful rework cycles trigger diagnosis/re-scoping, not another identical attempt.
6. Boss integrates serially, runs affected integration tests and the release suite, and obtains review of the integrated diff.

At most four spawned agents concurrently: one Supervisor and three workers. Workers do not spawn additional agents. Use fewer when tasks depend on each other. Run one broad suite per integrated candidate; avoid each worker installing every dependency and rerunning all tests.

## Durable handoff contract

Before closing/reclaiming a worker worktree, require a local commit or a patch outside temporary worktree storage. Include untracked new files and binary artifacts if needed; `git diff` alone omits untracked files. Boss verifies the handoff is recoverable before releasing the agent. Do not rely on a final message with a list of files as the only copy of code.

Every handoff contains:
```text
Task ID and requirement IDs:
Role and effective model evidence:
Base commit and candidate commit/tree:
Files changed:
Behavior changed and why:
Commands run, exit status, environment:
Manual scenarios and actual observations:
Commit/patch location and recovery procedure:
Known failures, skipped checks, risks:
Next action:
```

Supervisor reports are stored under `docs/reviews/<task-id>.md` by the Boss if the Supervisor is read-only. Review tools may write temporary test artifacts only in an explicitly allowed disposable area; a read-only reviewer should request the Boss to run checks it cannot execute.

## Memory lifecycle

Do not create Memory.md for this planning bundle. The Boss creates root `Memory.md` when the first implementation work begins and updates it after accepted milestones and before ending a working session. One canonical case-sensitive filename; worker handoffs use `docs/handoffs/<task-id>.md` and do not overwrite it.

Keep Memory.md compact (target <=200 lines), factual and chronological only where useful. Fields:
- Updated UTC, branch, baseline and last verified commit/tree fingerprint.
- Current release/phase, accepted requirement IDs and actual implementation state.
- Active tasks/owners/worktrees and durable handoff references.
- Decisions with rationale and ADR links.
- Exact checks passed/failed/skipped with evidence links and date.
- External blockers, missing credentials by name only, unresolved risks.
- Next three concrete actions and resume commands.

Archive detail to ADRs, handoffs and evidence files. Never store raw user chats, credentials or private reasoning. On a new thread read Memory.md, then compare Git status, HEAD and relevant code; invalidate stale verification. Memory saves discovery effort, but cannot guarantee context or replace reading changed files.
