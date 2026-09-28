#!/usr/bin/env python3
"""Local-only, fail-closed evidence runner for Parakh and the adjacent Karmi checkout."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import uuid
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GATES = (
    "STATIC", "UNIT", "COMPONENT", "INTEGRATION", "E2E", "MOBILE", "SECURITY",
    "PERFORMANCE", "RESILIENCE", "PARAKH", "KARMI", "CROSS_SYSTEM",
    "PRODUCTION_CONFIG", "ROLLBACK", "REAL_IDENTITY", "PAID_PROVIDER",
    "BILLING", "CHANNEL_ELIGIBILITY", "DEPLOYMENT",
)
SENSITIVE = re.compile(r"(?i)(authorization|bearer|api[_-]?key|access[_-]?token|password|private[_-]?key|auth[_-]?secret|webhook[_-]?secret|cookie|set-cookie)")
COMMANDS = (
    "doctor", "lint", "typecheck", "unit", "component", "integration", "e2e",
    "mobile-smoke", "mobile-e2e", "security", "performance", "resilience",
    "benchmark", "full", "production-check", "release-check",
)


def utc() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def git_info(path: Path) -> dict[str, object]:
    if not (path / ".git").exists():
        return {"status": "unavailable", "sha": None, "branch": None, "dirty": None}
    def value(*args: str) -> str:
        result = subprocess.run(["git", "-C", str(path), *args], capture_output=True, text=True, check=False)
        return result.stdout.strip() if result.returncode == 0 else "unknown"
    return {"status": "available", "sha": value("rev-parse", "HEAD"),
            "branch": value("branch", "--show-current"), "dirty": bool(value("status", "--porcelain"))}


def digest(path: Path) -> str | None:
    if not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def safe_log(text: str) -> str:
    lines = text.splitlines()
    return "\n".join("[REDACTED: credential-bearing line]" if SENSITIVE.search(line) else line[:2000]
                     for line in lines[:3000]) + ("\n[TRUNCATED]\n" if len(lines) > 3000 else "\n")


def python(path: Path) -> str | None:
    candidate = path / ".venv" / "bin" / "python"
    return str(candidate) if candidate.is_file() else None


class Runner:
    def __init__(self, command: str, karmi: Path, output: Path,
                 mobile_evidence: Path | None = None, production_env: Path | None = None):
        self.command = command
        self.karmi = karmi
        self.output = output
        self.mobile_evidence = mobile_evidence
        self.production_env = production_env
        self.output.mkdir(parents=True, exist_ok=False, mode=0o700)
        self.output.chmod(0o700)
        (self.output / "logs").mkdir(mode=0o700)
        self.cases: list[dict[str, object]] = []
        self.manifest: dict[str, object] = {
            "schema_version": 1, "runner_version": "readiness.v1", "command": command,
            "started_at": utc(), "environment": "local-synthetic-only", "parakh": git_info(ROOT),
            "karmi": git_info(karmi), "benchmark_seed": 7,
            "dataset_sha256": digest(ROOT / "benchmarks/seed_cases.jsonl"),
            "karmi_dataset_sha256": digest(karmi / "benchmarks/seed_cases.jsonl"),
            "karmi_lock_sha256": digest(karmi / "requirements.lock"),
            "python": sys.version.split()[0], "device": None,
        }

    def record(self, gate: str, name: str, status: str, reason: str,
               *, start: str | None = None, duration: float = 0,
               exit_code: int | None = None, log: str | None = None) -> None:
        assert status in {"PASS", "FAIL", "BLOCKED", "NOT_RUN"}
        self.cases.append({"gate": gate, "name": name, "status": status,
                           "started_at": start or utc(), "finished_at": utc(),
                           "duration_seconds": round(duration, 3), "exit_code": exit_code,
                           "reason": reason, "log": log})
        print(f"{gate} {name}: {status} — {reason}", flush=True)

    def run(self, gate: str, name: str, args: list[str], cwd: Path, *, timeout: int = 900,
            blocked_evidence: Path | None = None) -> None:
        start = utc()
        tick = time.monotonic()
        if not cwd.is_dir():
            self.record(gate, name, "BLOCKED", "checkout not found", start=start)
            return
        if not shutil.which(args[0]) and not Path(args[0]).is_file():
            self.record(gate, name, "BLOCKED", f"executable unavailable: {Path(args[0]).name}", start=start)
            return
        # No inherited provider/payment/channel secrets or live-mode flags enter test commands.
        env = {key: os.environ[key] for key in ("PATH", "HOME", "LANG", "LC_ALL", "TERM", "TMPDIR") if key in os.environ}
        env.update(DAILY_AGENT_ENVIRONMENT="test", DAILY_AGENT_LIVE_MODELS_ENABLED="false",
                   DAILY_AGENT_PAID_CHECKOUT_ENABLED="false", DAILY_AGENT_WHATSAPP_ENABLED="false")
        filename = f"{len(self.cases):02d}-{re.sub('[^a-z0-9-]', '-', name.lower())}.log"
        try:
            completed = subprocess.run(args, cwd=cwd, env=env, capture_output=True, text=True,
                                       errors="replace", timeout=timeout, check=False)
            content = safe_log(completed.stdout + "\n" + completed.stderr)
            (self.output / "logs" / filename).write_text(content, encoding="utf-8")
            status = ("PASS" if completed.returncode == 0 else
                      "BLOCKED" if completed.returncode == 2 and blocked_evidence and blocked_evidence.is_file()
                      else "FAIL")
            self.record(gate, name, status, f"exit {completed.returncode}", start=start,
                        duration=time.monotonic() - tick, exit_code=completed.returncode,
                        log=f"logs/{filename}")
        except subprocess.TimeoutExpired:
            self.record(gate, name, "FAIL", f"timeout after {timeout}s", start=start,
                        duration=time.monotonic() - tick)

    def native(self, gate: str, name: str, repository: Path, args: list[str], *, timeout: int = 900) -> None:
        executable = python(repository)
        if executable is None:
            self.record(gate, name, "BLOCKED", f"{repository.name} .venv/bin/python missing")
        else:
            self.run(gate, name, [executable, *args], repository, timeout=timeout)

    def parakh_make(self, gate: str, target: str) -> None:
        executable = python(ROOT)
        if executable is None:
            self.record(gate, f"parakh-{target}", "BLOCKED", "Parakh .venv/bin/python missing")
        else:
            self.run(gate, f"parakh-{target}", ["make", f"PYTHON={executable}", target], ROOT, timeout=1200)

    def karmi_task(self, gate: str, task: str, *, timeout: int = 1200) -> None:
        self.native(gate, f"karmi-{task}", self.karmi, ["scripts/tasks.py", task], timeout=timeout)

    def flutter(self, gate: str, name: str, args: list[str]) -> None:
        self.run(gate, name, args, self.karmi / "mobile", timeout=1200)

    def doctor(self) -> None:
        for repo in (ROOT, self.karmi):
            meta = git_info(repo)
            self.record("STATIC", f"{repo.name}-checkout", "PASS" if meta["status"] == "available" else "BLOCKED",
                        f"revision {meta['sha']}; branch {meta['branch']}; dirty={meta['dirty']}")
            self.record("STATIC", f"{repo.name}-python", "PASS" if python(repo) else "BLOCKED",
                        "isolated .venv/bin/python present" if python(repo) else "isolated Python absent")
        for tool in ("docker", "flutter", "adb"):
            self.record("STATIC", f"tool-{tool}", "PASS" if shutil.which(tool) else "BLOCKED",
                        "available" if shutil.which(tool) else "not installed")
        self.karmi_task("KARMI", "doctor")
        self.parakh_make("PARAKH", "doctor")

    def lint(self) -> None:
        self.parakh_make("STATIC", "lint")
        self.karmi_task("STATIC", "lint")
        self.flutter("STATIC", "flutter-format", ["dart", "format", "--output=none", "--set-exit-if-changed", "."])
        self.flutter("STATIC", "flutter-analyze", ["flutter", "analyze"])

    def typecheck(self) -> None:
        self.karmi_task("STATIC", "typecheck")
        self.record("STATIC", "parakh-typecheck", "BLOCKED", "No project-wide Parakh type-check target; pyright settings alone do not prove clean types")

    def unit(self) -> None:
        self.parakh_make("UNIT", "test-unit")
        self.karmi_task("UNIT", "test-unit")
        self.flutter("UNIT", "flutter-widget", ["flutter", "test", "--exclude-tags", "golden"])
        self.flutter("UNIT", "flutter-golden", ["flutter", "test", "--tags", "golden"])

    def component(self) -> None:
        self.native("COMPONENT", "karmi-api-auth", self.karmi,
                    ["-m", "pytest", "-q", "tests/e2e/test_api.py", "tests/e2e/test_api_remediation.py"])
        self.native("COMPONENT", "karmi-routing-telemetry", self.karmi,
                    ["-m", "pytest", "-q", "tests/e2e/test_parakh_exchange.py"])
        self.native("COMPONENT", "parakh-telemetry-router", ROOT,
                    ["-m", "pytest", "-q", "tests/test_telemetry_import.py", "tests/test_router_bandit.py"])

    def integration(self) -> None:
        self.parakh_make("INTEGRATION", "test-integration")
        if shutil.which("docker"):
            self.karmi_task("INTEGRATION", "test-integration")
        else:
            self.record("INTEGRATION", "karmi-test-integration", "BLOCKED",
                        "Docker unavailable for disposable PostgreSQL/Redis")
        if (self.karmi / "src/daily_agent/parakh/telemetry.py").is_file():
            self.native("CROSS_SYSTEM", "cross-repo-contract", ROOT,
                        ["-m", "pytest", "-q", "tests/test_cross_repo_readiness.py"])
        else:
            self.record("CROSS_SYSTEM", "cross-repo-contract", "BLOCKED",
                        "Karmi integration branch with Parakh exchange absent")

    def e2e(self) -> None:
        self.parakh_make("E2E", "test-e2e")
        self.karmi_task("E2E", "test-e2e")
        self.flutter("E2E", "flutter-android-build", ["flutter", "build", "appbundle", "--release"])

    def benchmark(self) -> None:
        self.parakh_make("PARAKH", "test-smoke")
        executable = python(ROOT)
        demo = self.output / "parakh-demo"
        if executable is None:
            self.record("PARAKH", "offline-60-case-demo", "BLOCKED", "Parakh isolated Python missing")
        else:
            self.run("PARAKH", "offline-60-case-demo",
                     ["make", f"PYTHON={executable}", f"DEMO_OUT={demo}", "demo"], ROOT, timeout=1200)
        summary = demo / "summary.json"
        baseline = ROOT / "benchmarks/readiness-baseline.json"
        if summary.is_file() and baseline.is_file():
            actual = json.loads(summary.read_text(encoding="utf-8"))
            expected = json.loads(baseline.read_text(encoding="utf-8"))
            observed = {"suite_hash": actual["suite_hash"],
                        "seed": self.manifest["benchmark_seed"],
                        "digests": {key: value["digest"] for key, value in actual["runs"].items()}}
            self.record("PARAKH", "synthetic-regression", "PASS" if observed == expected else "FAIL",
                        "60-case suite and deterministic response digests match reviewed snapshot"
                        if observed == expected else "benchmark dataset/seed or result digest changed")
        else:
            self.record("PARAKH", "synthetic-regression", "BLOCKED",
                        "Synthetic summary or reviewed baseline unavailable")
        self.karmi_task("KARMI", "benchmark-demo")

    def external(self, gate: str, name: str, relative: str, *args: str) -> None:
        script = ROOT / "scripts" / relative
        if not script.is_file():
            self.record(gate, name, "BLOCKED", f"implementation missing: scripts/{relative}")
        else:
            self.run(gate, name, [sys.executable, str(script), *args], ROOT)

    def mobile(self, *, extended: bool) -> None:
        script = self.karmi / "mobile/tool/readiness_device.py"
        evidence_file = self.output / "device/evidence.json"
        if not script.is_file():
            self.record("MOBILE", "physical-android", "BLOCKED", "candidate-bound device test script absent")
        else:
            args = [sys.executable, str(script), "--output", str(self.output / "device"),
                    "--extended" if extended else "--smoke"]
            if self.mobile_evidence is not None:
                args += ["--steps", str(self.mobile_evidence)]
            self.run("MOBILE", "physical-android", args, self.karmi, blocked_evidence=evidence_file)
        if evidence_file.is_file():
            data = json.loads(evidence_file.read_text(encoding="utf-8"))
            self.manifest["device"] = {key: data.get(key) for key in
                                       ("serial", "karmi_sha", "apk_sha256", "installed_apk_sha256")}
            for step in data["steps"]:
                self.record("MOBILE", f"phone-{step['id']}", step["status"],
                            "manual observation recorded" if step["status"] in ("PASS", "FAIL") else "no validated observation")
        else:
            for step in ("launch", "initial_screen", "configuration", "backend_reachable", "authentication",
                         "primary_user_flow", "api_request", "api_error", "logout_expiration", "app_restart",
                         "backend_restart", "offline_handling", "network_recovery"):
                self.record("MOBILE", f"phone-{step}", "NOT_RUN", "no candidate-bound device evidence")

    def security(self) -> None:
        self.karmi_task("SECURITY", "lint")
        self.native("SECURITY", "karmi-negative-auth-and-config", self.karmi,
                    ["-m", "pytest", "-q", "tests/unit/test_config.py", "tests/e2e/test_api.py"])
        self.native("SECURITY", "parakh-provider-and-import-safety", ROOT,
                    ["-m", "pytest", "-q", "tests/test_provider_safety.py", "tests/test_telemetry_import.py"])
        self.external("SECURITY", "security-probes", "security_probe.py", "--karmi", str(self.karmi), "--output", str(self.output))
        self.record("SECURITY", "dependency-vulnerability-db", "BLOCKED",
                    "No locally provisioned vulnerability advisory database or approved network audit")

    def performance(self) -> None:
        self.external("PERFORMANCE", "local-performance", "performance_probe.py", "--karmi", str(self.karmi), "--output", str(self.output))
        self.record("PERFORMANCE", "approved-thresholds", "BLOCKED",
                    "Local measurements are not approved production performance thresholds")

    def resilience(self) -> None:
        self.external("RESILIENCE", "failure-injection", "resilience_probe.py", "--karmi", str(self.karmi), "--output", str(self.output))
        self.native("RESILIENCE", "negative-policy-and-budgets", self.karmi,
                    ["-m", "pytest", "-q", "tests/e2e/test_parakh_exchange.py", "tests/unit/test_config.py"])
        if not shutil.which("docker"):
            self.record("RESILIENCE", "postgres-redis-outage", "BLOCKED",
                        "Disposable Docker PostgreSQL/Redis unavailable; no shared service will be interrupted")
        self.record("RESILIENCE", "device-network-loss", "BLOCKED",
                    "Requires candidate-bound physical Android observations")

    def production_config(self) -> None:
        executable = python(self.karmi)
        script = self.karmi / "scripts/readiness_config.py"
        destination = self.output / "production-config.json"
        if executable is None or not script.is_file():
            self.record("PRODUCTION_CONFIG", "karmi-config", "BLOCKED",
                        "Karmi isolated runtime or strict configuration scanner absent")
        else:
            args = [executable, str(script), "--output", str(destination)]
            if self.production_env is not None:
                args += ["--env-file", str(self.production_env)]
            self.run("PRODUCTION_CONFIG", "karmi-config", args, self.karmi,
                     blocked_evidence=destination)
        self.record("ROLLBACK", "rollback-exercise", "BLOCKED", "No candidate-bound isolated restore and rollback observation")
        for gate, reason in (
            ("REAL_IDENTITY", "Production authentication and account isolation have no authorized live evidence"),
            ("PAID_PROVIDER", "Real model/action quality and cost budgets not approved or measured"),
            ("BILLING", "Real payment lifecycle and financial reconciliation not approved or verified"),
            ("CHANNEL_ELIGIBILITY", "WhatsApp eligibility unresolved for intended market; channel remains disabled"),
            ("DEPLOYMENT", "No authorized deployed candidate with observed health, telemetry and TLS"),
        ):
            self.record(gate, "external-acceptance", "BLOCKED", reason)

    def full(self) -> None:
        self.doctor()
        self.lint()
        self.typecheck()
        self.unit()
        self.component()
        self.integration()
        self.e2e()
        self.benchmark()
        self.security()
        self.performance()
        self.resilience()
        self.mobile(extended=False)
        self.production_config()

    def save(self) -> bool:
        self.manifest["finished_at"] = utc()
        self.manifest["cases"] = self.cases
        gates = {gate: "NOT_RUN" for gate in GATES}
        for gate in GATES:
            observed = [row["status"] for row in self.cases if row["gate"] == gate]
            if "FAIL" in observed:
                gates[gate] = "FAIL"
            elif "BLOCKED" in observed:
                gates[gate] = "BLOCKED"
            elif observed and all(status == "PASS" for status in observed):
                gates[gate] = "PASS"
        ready = all(status == "PASS" for status in gates.values())
        report = {"schema_version": 1, "candidate": {"parakh": self.manifest["parakh"],
                  "karmi": self.manifest["karmi"]}, "gates": gates,
                  "production_ready": ready, "state": "RELEASE_READY" if ready else "TESTING",
                  "production_state": "NOT_DEPLOYED", "run": self.output.name}
        (self.output / "results.json").write_text(json.dumps(self.manifest, indent=2) + "\n", encoding="utf-8")
        (self.output / "production-readiness.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        lines = ["# Production readiness", "", f"Run: `{self.output.name}`", "",
                 f"PRODUCTION READY: {'YES' if ready else 'NO'}", "", "| Gate | Status |", "| --- | --- |"]
        lines += [f"| {gate} | {status} |" for gate, status in gates.items()]
        lines += ["", "Evidence: `results.json`, `results.xml`, and sanitized `logs/` in this run.",
                  "No automation marks a candidate deployed or PRODUCTION.", ""]
        (self.output / "PRODUCTION_READINESS_REPORT.md").write_text("\n".join(lines), encoding="utf-8")
        suite = ET.Element("testsuite", name="readiness", tests=str(len(self.cases)),
                           failures=str(sum(row["status"] == "FAIL" for row in self.cases)),
                           skipped=str(sum(row["status"] in ("BLOCKED", "NOT_RUN") for row in self.cases)))
        for row in self.cases:
            case = ET.SubElement(suite, "testcase", classname=str(row["gate"]),
                                 name=str(row["name"]), time=str(row["duration_seconds"]))
            if row["status"] == "FAIL":
                ET.SubElement(case, "failure", message=str(row["reason"]))
            elif row["status"] in ("BLOCKED", "NOT_RUN"):
                ET.SubElement(case, "skipped", message=str(row["reason"]))
        ET.ElementTree(suite).write(self.output / "results.xml", encoding="unicode", xml_declaration=True)
        if self.command in {"production-check", "release-check"}:
            (ROOT / "production-readiness.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
            (ROOT / "PRODUCTION_READINESS_REPORT.md").write_text("\n".join(lines), encoding="utf-8")
        print(f"Evidence: {self.output}; PRODUCTION READY: {'YES' if ready else 'NO'}", flush=True)
        return bool(self.cases) and all(row["status"] == "PASS" for row in self.cases)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=COMMANDS)
    parser.add_argument("--karmi", type=Path, default=Path(os.environ.get("PARAKH_KARMI_DIR", ROOT.parent / "Karmi")))
    parser.add_argument("--output", type=Path, help="new evidence directory (must not exist)")
    parser.add_argument("--mobile-evidence", type=Path,
                        help="reviewer observations matching Karmi SHA, installed APK hash and device serial")
    parser.add_argument("--production-env", type=Path,
                        help="explicit private deployment-candidate env file (values never stored in evidence)")
    args = parser.parse_args()
    output = args.output or ROOT / "test-results" / (datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8])
    runner = Runner(args.command, args.karmi.resolve(), output.resolve(),
                    args.mobile_evidence.resolve() if args.mobile_evidence else None,
                    args.production_env.resolve() if args.production_env else None)
    if args.command == "doctor": runner.doctor()
    elif args.command == "lint": runner.lint()
    elif args.command == "typecheck": runner.typecheck()
    elif args.command == "unit": runner.unit()
    elif args.command == "component": runner.component()
    elif args.command == "integration": runner.integration()
    elif args.command == "e2e": runner.e2e()
    elif args.command == "benchmark": runner.benchmark()
    elif args.command == "security": runner.security()
    elif args.command == "performance": runner.performance()
    elif args.command == "resilience": runner.resilience()
    elif args.command == "mobile-smoke": runner.mobile(extended=False)
    elif args.command == "mobile-e2e": runner.mobile(extended=True)
    elif args.command in ("full", "release-check"): runner.full()
    elif args.command == "production-check": runner.full()
    return 0 if runner.save() else 1


if __name__ == "__main__":
    raise SystemExit(main())
