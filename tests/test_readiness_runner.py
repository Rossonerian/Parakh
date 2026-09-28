"""Consumer-visible readiness invariants: unavailable checks cannot become green."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from scripts import readiness, security_probe


def _tracked_repo(root: Path, files: dict[str, bytes]) -> Path:
    for relative, content in files.items():
        (root / relative).parent.mkdir(parents=True, exist_ok=True)
        (root / relative).write_bytes(content)
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "add", "."], check=True)
    return root


def test_secret_scan_allows_only_the_exact_reviewed_fixture(tmp_path: Path) -> None:
    source = Path(__file__).resolve().parents[1]
    fixture = (source / "tests/test_tui_console.py").read_bytes()
    # Assembled at runtime so this test file itself never contains a matching literal.
    prefix = b"sk-" + b"or-v1-"
    fake = prefix + b"thisisnotarealkey0987654321"
    unterminated = b"-----BEGIN " + b"PRIVATE KEY-----\nMIIE"
    repo = _tracked_repo(tmp_path / "Parakh", {
        "tests/test_tui_console.py": fixture,                           # reviewed: allowed
        "tests/test_other.py": b"KEY = '" + fake + b"'\n",                # same value elsewhere
        "src/app.py": b"KEY = '" + fake[:-1] + b"2'\n",                   # edited value
        "keys/raw.pem": unterminated,                                     # no END line
    })
    findings = {(item["file"], item["reason"]) for item in security_probe.scan(repo)}
    assert findings == {("tests/test_other.py", "openai-token"), ("src/app.py", "openai-token"),
                        ("keys/raw.pem", "private-key-header")}


def test_missing_checkout_is_blocked_and_report_is_not_ready(tmp_path: Path) -> None:
    runner = readiness.Runner("doctor", tmp_path / "missing-karmi", tmp_path / "evidence")
    runner.run("INTEGRATION", "karmi-test", ["missing-command"], tmp_path / "missing-karmi")
    assert runner.cases[0]["status"] == "BLOCKED"
    assert not runner.save()
    report = json.loads((tmp_path / "evidence/production-readiness.json").read_text())
    assert report["gates"]["INTEGRATION"] == "BLOCKED"
    assert report["gates"]["MOBILE"] == "NOT_RUN"
    assert report["production_ready"] is False
    assert report["production_state"] == "NOT_DEPLOYED"
    assert '<skipped message="checkout not found"' in (tmp_path / "evidence/results.xml").read_text()


def test_mixed_result_cannot_pass_gate(tmp_path: Path) -> None:
    runner = readiness.Runner("security", tmp_path / "missing", tmp_path / "evidence")
    runner.record("SECURITY", "lint", "PASS", "exit 0")
    runner.record("SECURITY", "auth", "BLOCKED", "requires real identity provider")
    runner.record("STATIC", "format", "FAIL", "exit 1")
    assert not runner.save()
    report = json.loads((tmp_path / "evidence/production-readiness.json").read_text())
    assert report["gates"]["SECURITY"] == "BLOCKED"
    assert report["gates"]["STATIC"] == "FAIL"


def test_credential_lines_are_not_kept() -> None:
    log = readiness.safe_log("normal failure\nAuthorization: Bearer do-not-store\npassword=do-not-store\n")
    assert "normal failure" in log
    assert "do-not-store" not in log
    assert log.count("[REDACTED: credential-bearing line]") == 2
