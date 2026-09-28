#!/usr/bin/env python3
"""Render a managed-worker launch for one testing role from docs/testing/agent-roles.json.

Prints the `agent-team-orca-start` command; never launches anything. The testing manager reviews
the printed spec, then runs it inside the active Orca Run.
"""
from __future__ import annotations

import argparse
import json
import shlex
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROLES = ROOT / "docs/testing/agent-roles.json"
REPOS = {"Parakh": "85618893-1953-4954-a1f4-fd8ff122fe82", "Karmi": "92af45f0-2d70-4124-ad77-8d3a97c35662"}


def main() -> int:
    config = json.loads(ROLES.read_text(encoding="utf-8"))
    launchable = sorted(name for name, role in config["roles"].items() if "worker_role" in role)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("role", choices=launchable)
    parser.add_argument("--assignment-id", required=True, help="stable ID, e.g. READY-K-UNIT-02")
    parser.add_argument("--run", required=True, help="existing Orca Run ID")
    parser.add_argument("--task", required=True, help="the bounded change or investigation")
    args = parser.parse_args()
    role = config["roles"][args.role]
    spec = "\n".join([
        f"Role: {args.role} ({args.assignment_id}). Task: {args.task}",
        f"Owned paths: {', '.join(role['owns']) or 'none (read-only)'}. Gates: {', '.join(role['gates'])}.",
        f"Verify with: {'; '.join(role['commands'])} (from the Parakh checkout, --karmi ../Karmi).",
        f"Acceptance: {role['acceptance']}",
        "Rules: " + " ".join(config["rules"]),
        ("Deliver: a local commit on your worktree branch, the evidence directory path and exact command output; "
         if role["owns"] else "Deliver: a read-only report (no commits or edits) with the evidence directory path; ")
        + "report FAIL/BLOCKED honestly.",
    ])
    command = ["agent-team-orca-start", "--project", str(ROOT), "--run", args.run, "--repo", REPOS[role["repo"]],
               "--role", role["worker_role"], "--assignment-id", args.assignment_id,
               "--task-title", f"{args.role}: {args.task[:60]}", "--spec", spec]
    print(shlex.join(command))
    return 0


if __name__ == "__main__":
    sys.exit(main())
