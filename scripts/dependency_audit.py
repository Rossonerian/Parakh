#!/usr/bin/env python3
"""Known-vulnerability audit of exact dependency sets via the OSV batch API (PyPI + Pub).

Sources: Karmi `requirements.lock` and `mobile/pubspec.lock` (hosted packages), and the exact
distributions installed in Parakh's isolated runtime (Parakh has no lock file). Only package
names/versions are sent. Exit 0 = no known advisories, 1 = advisories found, 2 = BLOCKED
(network/source unavailable; evidence still written).
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

OSV_BATCH = "https://api.osv.dev/v1/querybatch"
ROOT = Path(__file__).resolve().parents[1]
LOCAL_DISTRIBUTIONS = {"parakh-model-lab", "daily-agent"}  # the projects themselves, not dependencies


def pypi_lock(path: Path) -> list[tuple[str, str]]:
    pins = re.findall(r"^([A-Za-z0-9._-]+)==([^\s;#]+)", path.read_text(encoding="utf-8"), re.MULTILINE)
    return sorted(set(pins))


def pub_lock(path: Path) -> list[tuple[str, str]]:
    packages: list[tuple[str, str]] = []
    for block in re.split(r"\n  (?=[a-z0-9_]+:\n)", path.read_text(encoding="utf-8")):
        name = re.search(r"^\s*name: ([a-z0-9_]+)$", block, re.MULTILINE)
        version = re.search(r'^    version: "([^"]+)"$', block, re.MULTILINE)
        if name and version and re.search(r"^    source: hosted$", block, re.MULTILINE):
            packages.append((name.group(1), version.group(1)))
    return sorted(set(packages))


def installed(python: Path) -> list[tuple[str, str]]:
    listed = subprocess.run([str(python), "-c", "import importlib.metadata as m; print('\\n'.join("
                             "f\"{d.metadata['Name']}=={d.version}\" for d in m.distributions()))"],
                            capture_output=True, text=True, timeout=60, check=True).stdout
    pins = {tuple(line.split("==", 1)) for line in listed.splitlines() if "==" in line}
    return sorted((name, version) for name, version in pins
                  if name.lower().replace("_", "-") not in LOCAL_DISTRIBUTIONS)


def query(ecosystem: str, packages: list[tuple[str, str]]) -> list[dict[str, object]]:
    findings: list[dict[str, object]] = []
    for start in range(0, len(packages), 500):
        chunk = packages[start:start + 500]
        body = json.dumps({"queries": [{"package": {"name": name, "ecosystem": ecosystem}, "version": version}
                                       for name, version in chunk]}).encode()
        request = urllib.request.Request(OSV_BATCH, data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=60) as response:
            results = json.load(response)["results"]
        for (name, version), result in zip(chunk, results, strict=True):
            ids = sorted(vuln["id"] for vuln in result.get("vulns", []))
            if ids:
                findings.append({"ecosystem": ecosystem, "package": name, "version": version, "advisories": ids})
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--karmi", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    karmi = args.karmi.resolve()
    sources = {
        "karmi-python (requirements.lock)": ("PyPI", karmi / "requirements.lock", pypi_lock),
        "karmi-mobile (pubspec.lock)": ("Pub", karmi / "mobile/pubspec.lock", pub_lock),
        "parakh-python (installed .venv)": ("PyPI", ROOT / ".venv/bin/python", installed),
    }
    coverage: dict[str, object] = {}
    findings: list[dict[str, object]] = []
    status = "PASS"
    for label, (ecosystem, path, reader) in sources.items():
        if not path.is_file():
            coverage[label] = "BLOCKED: source missing"
            status = "BLOCKED" if status == "PASS" else status
            continue
        packages = reader(path)
        try:
            found = query(ecosystem, packages)
        except (urllib.error.URLError, TimeoutError, ConnectionError, KeyError, ValueError) as error:
            coverage[label] = f"BLOCKED: OSV query failed ({type(error).__name__})"
            status = "BLOCKED" if status == "PASS" else status
            continue
        coverage[label] = f"{len(packages)} packages queried, {len(found)} with advisories"
        findings += found
    if findings:
        status = "FAIL"
    (args.output / "dependency-audit.json").write_text(json.dumps(
        {"status": status, "database": OSV_BATCH, "coverage": coverage, "findings": findings}, indent=2) + "\n")
    print(f"dependency audit: {status}", json.dumps(coverage))
    return {"PASS": 0, "FAIL": 1, "BLOCKED": 2}[status]


if __name__ == "__main__":
    sys.exit(main())
