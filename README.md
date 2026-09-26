# Daily AI Agent — project blueprint

Prepared 2026-09-09 for a WhatsApp-first assistant with four subscriptions and future app/voice channels. This package contains specifications, implementation prompts, agent configuration examples and a synthetic benchmark seed bank. It is not a built application or measured comparison of live models.

## Start here

1. Put the files in the actual project. For an existing repository preserve its structure; merge instructions and configuration rather than overwriting them.
2. Read PRD.md and the channel eligibility finding in Sources.md. General-purpose WhatsApp AI cannot be assumed eligible for the intended market; keep a working owned-channel path available.
3. Follow Agent_Team.md to configure and verify the requested Sol High Boss, Terra Medium Supervisor and Luna Medium workers in your installed Codex/Zed environment.
4. Paste Start_Project_Prompt.md into the Boss thread to implement the bounded core release with tests and evidence.
5. To build the Linux model comparison tool independently, paste Testing_Lab_Prompt.md into a Codex thread with Model_Testing_Spec.md and benchmarks/ available.

## ModelLab (implemented)

`model_lab/` is a working, offline-first evaluation lab (Python ≥ 3.12, no runtime dependencies; the console needs the `tui` extra). The Daily AI Agent product itself is still specification only.

```bash
python -m venv .venv && .venv/bin/pip install -e '.[dev]'   # pytest, ruff, textual
make PYTHON=.venv/bin/python tui            # interactive console; starts the offline DEMO on an empty workspace
.venv/bin/python -m model_lab tui --data lab-data/tui       # same, without auto-demo
make PYTHON=.venv/bin/python demo           # CLI: full 60-case offline workflow into lab-data/demo
.venv/bin/python -m model_lab --help        # all CLI commands
make PYTHON=.venv/bin/python test-release   # lint + doctor + unit + integration + e2e + smoke
```

Console navigation: `1`–`9`, `0`, `l` switch tabs (Dashboard, Suites, Cases, Models, Runs, Run detail, Results, Compare, Review, Routing, Events); `d` demo, `f` fake-provider run, `g` grade, `v` validate, `h` doctor, `r` refresh, `q` quit. Run data lives in `lab-data/tui/model_lab.sqlite3` (gitignored). Everything shown comes from that store; demo data is labelled `SIMULATED`, missing measurements show `N/A`/`not measured`, and the console cannot start paid/live calls — those remain `model-lab pilot run … --allow-paid` with a verified immutable plan. See `Model_Testing_Spec.md` → *Interactive console* and `MANUAL_TESTING.md`.

Layout: `cli/` (argparse surface) → `pipeline.py`, `pilot.py` and feature modules → `application/` (execution engine, reporting, event log, observability read model, operator actions) → `domain/` (isolation, budget) → `storage/` (SQLite) and `providers/` (fake, gated live). `tui/` renders the observability read model only. Module map and invariants: `model_lab/CLAUDE.md`.

## Files

| File | Purpose |
| --- | --- |
| PRD.md | Users, scope, subscription concept, requirements and success criteria |
| Architecture.md | Message lifecycle, context, routing, data, tools, cost and recovery |
| Rules.md | Engineering constraints, error handling, safety and verification boundaries |
| Phases.md | Sequenced implementation with automatic/manual and release gates |
| Design.md | Visual tokens, screens, WhatsApp/app behavior and accessible states |
| Tier_Entitlements.md | Context/usage/budget policy and pricing measurement requirements |
| Agent_Team.md | Multi-model development team, Zed setup, review and memory lifecycle |
| AGENTS.md | Instructions to merge into the repository for Codex |
| codex-examples/ | Configuration examples to merge after compatibility verification |
| Acceptance_Testing.md | Cross-cutting automated cases and concrete manual walkthrough |
| Model_Testing_Spec.md | Linux CLI, data imports, scoring, reports and router evidence |
| Testing_Lab_Prompt.md | Full prompt to implement the model-testing software |
| benchmarks/ | 60 actual synthetic seed cases with protected references and grading rubrics |
| Start_Project_Prompt.md | Full project creation/testing/readiness execution prompt |
| Sources.md | Verified setup facts and important channel-policy limitation |

`Memory.md` is intentionally absent. The Boss creates it when coding starts and records only verified progress. Use that one case-sensitive filename on Linux. Developer memory is separate from the product's customer memory feature.

## Fixed decisions and provisional choices

The four subscription IDs are ananta/yanta/trika/part, using the user's latest spelling. They are unrelated to the development-agent models or four benchmark complexity levels. Paid prices, actual context/credit quotas, model allowlists and production cost ceilings remain unset pending measurement. The user expects useful conversion into Yanta; the plan measures that hypothesis rather than assuming everyone pays.

The proposed stack extends the user's reported backend only after repository verification. The consumer web/PWA is v1.1 by default and may be promoted if needed for an eligible initial channel. Voice notes and native/realtime voice are separately gated later work. The prompt must not interpret “complete” as permission for endless scope expansion or silently omit a selected release feature.

## Evaluation limits

Every compared model should receive the same 60 seed cases under the same applicable conditions; report skipped/ineligible cases. The set exceeds the requested 50-prompt minimum, but is only an initial benchmark. It contains no actual provider results and no validated long-context or audio measurements. Expand independent held-out families before using rankings for production routing. Imported aggregate reports cannot substitute for controlled per-case evidence.

Commands in `Model_Testing_Spec.md` → *Proposed command surface* are acceptance targets; only those listed by `python -m model_lab --help` exist. Pricing figures in example commands/configuration are illustrative, not approved spend.
