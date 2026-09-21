# ModelLab / Parakh — Audit and Fix Plan

Target executor: a coding agent (Antigravity, Flash-tier model) working in this repository.
Scope: the `model_lab` package, `benchmarks/`, `tests/`, `Makefile`, `pyproject.toml`, `docs/`, and the root blueprint documents.

This plan is written for a fast, cheap model. That means: **one step per prompt, small diffs, explicit acceptance criteria, and no judgement calls delegated to the agent.** Do not paste the whole document into a single task.

---

## 0. How to run this

1. Phases A–F are **read-only**. No source file is edited during them. Their only output is a findings file.
2. Phase G applies fixes, one finding per commit, in severity order.
3. Phase H verifies and writes the handoff.
4. Give the agent **one numbered step at a time**. Wait for its report. Verify the report against the pasted command output before giving the next step.
5. If a step's report contains no raw command output, reject it and re-issue the same step.

### Standing rules — paste these at the top of every task

```text
STANDING RULES (apply to every task in this session)

1. Do only the numbered step you were given. Do not start the next step.
2. Touch only the files listed in the step's "Files in scope". If you believe another
   file must change, stop and report that instead of changing it.
3. Never claim a command passed. Paste its exact stdout/stderr and its exit code.
   If you did not run it, say "NOT RUN" and why.
4. Never invent file contents, commit hashes, test counts or line numbers. If you
   cannot read something, say so.
5. Do not run: `pilot run --allow-paid`, any live provider call, any network call,
   `git push`, `git reset --hard`, `git clean`, `git checkout -- .`, force-push,
   or any command that deletes untracked files.
6. Do not edit: `benchmarks/**`, `docs/product_sources/original/**`, `Memory.md`,
   `docs/handoffs/**`, `docs/product_sources/IMPORT_AUDIT.jsonl`.
   These are evidence or protected source bytes.
7. Do not refactor, rename, reformat, upgrade dependencies, or add new libraries
   unless the step explicitly says to.
8. If the step turns out to require a design decision, stop and report the two or
   three options with their trade-offs. Do not pick one.
9. Keep each diff under ~150 changed lines. If a fix is larger, stop and report.
10. End every report with: files changed, `git status --short`, `git diff --stat`.
```

### Severity scale

| Level | Meaning | Examples |
| --- | --- | --- |
| **S1** | Repo does not work as documented; a documented command fails or a required file is missing | Missing benchmark file, import error, broken entry point |
| **S2** | A safety or correctness invariant can be violated | Oracle leakage, paid dispatch without gate, non-atomic budget reservation, mutable raw evidence |
| **S3** | Implementation diverges from its own specification or documentation | Missing CLI command, Makefile target that does not match the stated contract |
| **S4** | Hygiene and maintainability | Dead code, stale docs, missing `.gitignore`, duplicated trees |

Fix order is strictly S1 → S2 → S3 → S4. Never fix an S4 before an open S1.

### Findings file

All phases write to `docs/audit/FINDINGS.md`. Create it in Step A0. One block per finding, appended, never rewritten:

```markdown
### [ID] <one-line title>
- Severity: S1|S2|S3|S4
- Phase/Step: B2
- Evidence: <exact file path(s) and line numbers, or the pasted command + output>
- Reproduction: <exact command a human can re-run>
- Impact: <what breaks, in one sentence>
- Proposed fix: <smallest change that resolves it>
- Fix risk: <what the fix could break>
- Status: OPEN | FIXED (commit <sha>) | WONTFIX (<reason>) | NEEDS-OWNER-DECISION
```

IDs are sequential per phase: `A-01`, `B-01`, `D-03`, and so on.
