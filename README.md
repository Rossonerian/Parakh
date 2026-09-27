# Daily AI Agent — project blueprint

Prepared 2026-09-09 for a WhatsApp-first assistant with four subscriptions and future app/voice channels. This package contains specifications, implementation prompts, agent configuration examples and a synthetic benchmark seed bank. It is not a built application or measured comparison of live models.

## Start here

1. Put the files in the actual project. For an existing repository preserve its structure; merge instructions and configuration rather than overwriting them.
2. Read PRD.md and the channel eligibility finding in Sources.md. General-purpose WhatsApp AI cannot be assumed eligible for the intended market; keep a working owned-channel path available.
3. Follow Agent_Team.md to configure and verify the requested Sol High Boss, Terra Medium Supervisor and Luna Medium workers in your installed Codex/Zed environment.
4. Paste Start_Project_Prompt.md into the Boss thread to implement the bounded core release with tests and evidence.
5. To build the Linux model comparison tool independently, paste Testing_Lab_Prompt.md into a Codex thread with Model_Testing_Spec.md and benchmarks/ available.

## ModelLab and offline optimization engine

`model_lab/` is a working offline-first Python ≥3.11 evaluation lab with a versioned optimization lane. The console requires the `tui` extra; the Daily AI Agent product remains specification-only. No live Karmi integration or paid-provider measurements are implied.
```bash
python -m venv .venv && .venv/bin/pip install -e '.[dev]'   # pytest, ruff, textual
make PYTHON=.venv/bin/python tui            # interactive console; starts the offline DEMO on an empty workspace
.venv/bin/python -m model_lab tui --data lab-data/tui       # same, without auto-demo
make PYTHON=.venv/bin/python demo           # CLI: full 60-case offline workflow into lab-data/demo
.venv/bin/python -m model_lab --help        # all CLI commands
make PYTHON=.venv/bin/python test-release   # lint + doctor + unit + integration + e2e + smoke
```

From any directory: `scripts/parakh` (alias it, e.g. `alias parakh=/path/to/Parakh/scripts/parakh`) — `parakh` opens the console, `parakh demo` opens it with the offline demo, `parakh stop` stops a console running in another terminal, `parakh status`, `parakh cli <args>`. It bootstraps `.venv` with the `tui` extra on first use.

Console navigation: `1`–`9`, `0`, `t`, `p`, `o`, `l` select Dashboard through Routing, telemetry Candidates, Preferences, Policies, Events. Candidate and preference tabs require named actor/reason for audited review; the Policy tab displays gates and compounding metrics. `d` demo, `f` fake-provider run, `g` grade, `v` validate, `h` doctor, `r` refresh, `q` quit. Run data lives in `lab-data/tui/model_lab.sqlite3` (gitignored). Demo data is `SIMULATED`; missing measurements show `N/A`. The console cannot start paid/live calls — those remain `model-lab pilot run … --allow-paid` with a verified immutable plan. See `MANUAL_TESTING.md`.

### Offline optimization loop

The commands below operate on a disposable SQLite evidence file; they do not dispatch providers or write production configuration. The fixture is **synthetic**, not evidence of a Karmi deployment. Use `--help` on each subcommand for flags. IDs printed by earlier commands replace placeholders.

```bash
P=.venv/bin/python
DB=/tmp/parakh-opt/model_lab.sqlite3
$P -m model_lab telemetry synthesize --out /tmp/parakh-opt/batch.json --seed 21 --runs 4000 --epsilon 0.5 --base-policy balanced_only
$P -m model_lab telemetry import /tmp/parakh-opt/batch.json --db \"$DB\"
$P -m model_lab candidates list --db \"$DB\"  # explicit candidates approve ID --role TRAIN_ONLY --actor NAME --reason WHY
$P -m model_lab reward compute all --db \"$DB\"
$P -m model_lab router dataset --db \"$DB\" --seed 37
$P -m model_lab router train DATASET_ID --db \"$DB\" --seed 37
$P -m model_lab router evaluate CANDIDATE_ID --db \"$DB\"
$P -m model_lab router benchmark --db \"$DB\" --out /tmp/parakh-opt/bench.json
$P -m model_lab verify CANDIDATE_ID --db \"$DB\" --benchmark-runs /tmp/parakh-opt/bench.json --config /secure/owner-ceilings.json --report-dir /tmp/parakh-opt/report
$P -m model_lab policy approve CANDIDATE_ID --db \"$DB\" --actor NAME --reason WHY
$P -m model_lab artifact keygen --path /secure/parakh-signing-key.hex
$P -m model_lab artifact export CANDIDATE_ID --db \"$DB\" --out /tmp/parakh-opt/bundles --key-path /secure/parakh-signing-key.hex --actor NAME
$P -m model_lab artifact karmi-check BUNDLE_PATH --trusted-public-key PUBLIC_KEY_HEX
```

`verify` fails closed on missing support, regression evidence, dirty Git or unapproved cost/latency envelopes; default envelopes are *provisional* relative bounds, not owner authorization. Supply explicitly approved `tier_cost_ceiling_usd` and `tier_latency_ceiling_ms` mappings only after measuring the applicable tiers. Signed bundles are read-only JSON with Ed25519 signatures; the bundled Karmi **reference fixture** loads into shadow while its active policy stays static. Trust a known public key out-of-band; never publish private signing keys. Import a subsequent simulated shadow batch with `telemetry synthesize --shadow-bundle BUNDLE_PATH --trusted-public-key PUBLIC_KEY_HEX --batch-index 1`, then `telemetry import` to close the fixture loop. `harness optimize`, `preferences extract/review/export` and `policy report` are separate offline commands. Shared formats: `contracts/README.md`.

`metrics` reports data efficiency as approved distinct candidates divided by all imported telemetry candidates, including candidates later rejected as duplicates. Accepted runs are an intake count, not the ratio's denominator. With no candidates the ratio is unavailable (`N/A` in the console), not zero.

The frozen 60-case core stays at `benchmarks/seed_cases.jsonl` in source; built wheels install the same SHA-256-pinned bytes as data under `share/parakh/benchmarks/` for standalone CLI use. Its family splits are 36 train / 12 calibration / 12 sealed holdout. The core holdout is rubric-only and requires blind human review for harness promotion; fake results do not satisfy that gate. Real Karmi shadow telemetry and provider/payment/manual release gates remain unobserved. Offline fixture success is **not production readiness**.

Layout: `cli/` (argparse surface) → `pipeline.py`, `pilot.py` and optimization modules → `application/` (execution, reporting, operator views) → `domain/` (isolation, budget) → `storage/` (SQLite evidence) and `providers/` (fake, gated live). `tui/` renders the read model and separate operator reviews. Module map: `model_lab/CLAUDE.md`.

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

`Memory.md` is protected historical state. Do not delete, replace or edit it without explicit owner authorization.

## Fixed decisions and provisional choices

The four subscription IDs are ananta/yanta/trika/part, using the user's latest spelling. They are unrelated to the development-agent models or four benchmark complexity levels. Paid prices, actual context/credit quotas, model allowlists and production cost ceilings remain unset pending measurement. The user expects useful conversion into Yanta; the plan measures that hypothesis rather than assuming everyone pays.

The proposed stack extends the user's reported backend only after repository verification. The consumer web/PWA is v1.1 by default and may be promoted if needed for an eligible initial channel. Voice notes and native/realtime voice are separately gated later work. The prompt must not interpret “complete” as permission for endless scope expansion or silently omit a selected release feature.

## Evaluation limits

Every compared model should receive the same 60 seed cases under the same applicable conditions; report skipped/ineligible cases. The set exceeds the requested 50-prompt minimum, but is only an initial benchmark. It contains no actual provider results and no validated long-context or audio measurements. Expand independent held-out families before using rankings for production routing. Imported aggregate reports cannot substitute for controlled per-case evidence.

Commands in `Model_Testing_Spec.md` → *Proposed command surface* are acceptance targets; only those listed by `python -m model_lab --help` exist. Pricing figures in example commands/configuration are illustrative, not approved spend.
