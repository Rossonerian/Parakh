@AGENTS.md

## Claude Code operating guide

This section is read by Claude Code in addition to `AGENTS.md` above. It exists
to keep sessions scoped and cheap: read only what the current task needs.

### Repository shape — two workstreams, don't conflate them

1. **ModelLab** (`model_lab/`) — a small, offline-first Python CLI that runs
   reproducible LLM evaluations. **Built, tested, audited.** This is the only
   code that compiles, imports, or runs. Work here needs only this file plus
   `model_lab/CLAUDE.md`.
2. **Daily AI Agent product spec** (`PRD.md`, `Architecture.md`, `Design.md`,
   `Tier_Entitlements.md`, `Phases.md`, `Rules.md`, `Sources.md`,
   `Start_Project_Prompt.md`) — planning documents for a WhatsApp assistant
   that has **not been implemented**. No app code exists for it yet. Only open
   these files when the task is explicitly about that product's
   requirements/design, not for ModelLab work.

Do not read the product-spec docs "just in case" — they are large (~80KB
combined) and irrelevant to `model_lab/` changes.

### Primary commands (ModelLab)

Local pytest is only installed in the project venv, not system `python3`.

```
Build:      pip install -e '.[dev]'            # or: use existing .venv
Test:       .venv/bin/python -m pytest -q
Lint:       make PYTHON=.venv/bin/python lint   # ruff, pyflakes+bugbear rules (pyproject.toml)
Release:    make PYTHON=.venv/bin/python test-release   # lint + doctor + unit + integration + e2e + smoke
Demo:       make PYTHON=.venv/bin/python demo
Typecheck:  no gate; pyright-lsp plugin gives editor diagnostics (see .claude/settings.json)
```

CI (`.github/workflows/ci.yml`) runs `make test-release` then `make demo` with
system `python3` after `pip install -e '.[dev]'`, so CI does not need the venv
prefix — only local shells with a pre-existing `.venv` do.

### Important directories

| Path | Contents |
| --- | --- |
| `model_lab/` | The only shipped code. See `model_lab/CLAUDE.md`. |
| `tests/` | pytest suite, one file per behavior area, mirrors `model_lab/` modules. |
| `benchmarks/` | Frozen seed cases + grading rubrics. Treat as read-only evidence. |
| `docs/audit/` | Completed audit trail (`FINDINGS.md`, `AUDIT_REPORT.md`). Reference, don't re-run from scratch — check `FINDINGS.md` status before re-investigating something. |
| `docs/handoffs/`, `docs/tasks/` | Evidence from the separate Codex/Zed worker workflow (see `Agent_Team.md`). Read for context; do not edit — they are append-only records. |
| `lab-data/` | Disposable run output (gitignored). |

### Core engineering rules

- Never fabricate test output, commit hashes, or line counts — paste real
  command output.
- No live/paid provider calls, network calls, or `pilot run --allow-paid`
  without explicit owner authorization (see `model_lab/CLAUDE.md` for the
  isolation/budget invariants this protects).
- Keep the CLI/application/domain/storage/providers layering in
  `model_lab/` (see nested `CLAUDE.md`); don't add new flat root-level
  modules — extend an existing layer.
- Small, reviewable diffs. This codebase went through a severity-tiered
  audit (`docs/audit/FINDINGS.md`); don't reopen a `FIXED`/`VERIFIED`
  finding without new evidence.

### Protected files (enforced by `.claude/hooks/protect-files.sh`)

`Memory.md`, `docs/handoffs/**`, `benchmarks/**`,
`docs/product_sources/original/**`, `docs/product_sources/IMPORT_AUDIT.jsonl`
are evidence or byte-preserved source material. Edits are blocked by a
pre-tool-use hook, not just a convention.

### Git safety

- Never `git push --force`, `git reset --hard`, `git clean`, or
  `git checkout -- .` (blocked in `.claude/settings.json`; ask the user
  instead).
- This repo has an active branch (`codex/production-readiness`) with a
  parallel Codex-driven PR workflow (`Agent_Team.md`) that owns specific
  files per task card. Check `git status`/`git diff` before editing a file
  that might already be mid-flight there.
- Local commits of reviewed, verified work are fine (one logical change per
  commit); never push — the user controls when work leaves the machine.

### Multi-agent workflow

- **OMP/Orca (primary):** Opus 5.5 is the supervisor for this project (user
  decision, 2026-09-26). Implementation and verification go to Gemini High
  workers only through `agent-team-orca-start` (one worktree + one commit per
  assignment; supervisor reviews the diff and cherry-picks). Task specs live
  in `.agent-team/tasks/` (local, untracked); reuse their RULES/RETURN blocks.
- **Claude Code:** `.claude/agents/` — `explorer`, `implementer`,
  `test-worker` (Haiku), `reviewer` (Sonnet). Hand them a task packet with
  scope, acceptance and verify command, never "improve the repo".

### Definition of done

- Behavior claim backed by an actually-run command, not an assumption.
- New/changed behavior in `model_lab/` has a focused test in `tests/`.
- `.venv/bin/python -m pytest -q` passes.
- No edits to protected/evidence files.
- Any product-spec claim traces to a source doc, not invention.
