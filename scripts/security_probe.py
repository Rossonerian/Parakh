#!/usr/bin/env python3
"""Narrow offline tracked-secret scan; does not replace reviewed security testing."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

# High-specificity signatures only: never print matched content or a secret-bearing line.
PATTERNS = {
    "private-key-block": re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "github-token": re.compile(rb"\b(?:ghp_|gho_|ghs_)[A-Za-z0-9]{36,}\b"),
    "openai-token": re.compile(rb"\bsk-(?:proj-|or-v1-)[A-Za-z0-9_-]{24,}\b"),
}
MAX_BYTES = 2_000_000


def scan(repo: Path) -> list[dict[str, str]]:
    files = subprocess.run(["git", "-C", str(repo), "ls-files", "-z"],
                           capture_output=True, check=True).stdout.split(b"\0")
    issues: list[dict[str, str]] = []
    for raw in files:
        if not raw:
            continue
        relative = raw.decode("utf-8", errors="replace")
        file = repo / relative
        if not file.is_file() or file.stat().st_size > MAX_BYTES:
            continue
        data = file.read_bytes()
        if b"\0" in data:
            continue
        for name, pattern in PATTERNS.items():
            if pattern.search(data):
                issues.append({"repository": repo.name, "file": relative, "reason": name})
    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--karmi", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    parakh = Path(__file__).resolve().parents[1]
    findings = scan(parakh) + scan(args.karmi.resolve())
    (args.output / "security-findings.json").write_text(json.dumps({
        "mode": "offline", "scanned": "tracked text files <=2MB, three high-specificity signatures",
        "findings": findings, "dependency_vulnerability_database": "NOT_RUN",
        "authorization_scope": "existing native pytest tests required separately",
    }, indent=2) + "\n")
    print(f"Tracked-secret signature findings: {len(findings)} (no values emitted)")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
