#!/usr/bin/env python3
"""Karmi against disposable PostgreSQL/Redis: native integration suite and real outage/recovery.

Exit 0 = all assertions held, 1 = application failure, 2 = environment unavailable (BLOCKED, with
evidence written). Only synthetic identities and disposable containers are used.
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

import disposable_services as ds
from performance_probe import serve
from resilience_probe import stop

LEAK_MARKERS = ("daily_agent_test:", "postgresql", "psycopg", "Traceback", "password")


def request(method: str, url: str, *, body: dict[str, object] | None = None,
            token: str | None = None, timeout: float = 5) -> tuple[int, str]:
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"} if data else {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=data, headers=headers, method=method),
                                    timeout=timeout) as response:
            return response.status, response.read(4096).decode("utf-8", "replace")
    except urllib.error.HTTPError as error:
        with error:
            return error.code, error.read(4096).decode("utf-8", "replace")
    except (urllib.error.URLError, TimeoutError, ConnectionError):
        return 0, ""


def wait_status(url: str, want: int, timeout: float) -> int:
    deadline, status = time.monotonic() + timeout, 0
    while time.monotonic() < deadline:
        status, _ = request("GET", url, timeout=3)
        if status == want:
            return status
        time.sleep(0.25)
    return status


def integration(karmi: Path) -> dict[str, object]:
    env = {key: os.environ[key] for key in ("PATH", "HOME", "LANG", "TMPDIR") if key in os.environ}
    env.update(PYTHONPATH=f"{karmi / 'src'}{os.pathsep}{karmi}", DAILY_AGENT_ENVIRONMENT="test",
               DAILY_AGENT_INTEGRATION_DATABASE_URL=ds.DATABASE_URL,
               DAILY_AGENT_INTEGRATION_REDIS_URL=ds.REDIS_URL, DAILY_AGENT_LIVE_MODELS_ENABLED="false")
    # Karmi's addopts already include -q; adding another would suppress the summary line.
    completed = subprocess.run([str(karmi / ".venv/bin/python"), "-m", "pytest", "-p", "no:cacheprovider",
                                "-m", "integration", "tests/integration"],
                               cwd=karmi, env=env, capture_output=True, text=True, timeout=900, check=False)
    print(completed.stdout[-4000:], completed.stderr[-2000:], sep="\n")
    summary = (completed.stdout.strip().splitlines() or [""])[-1]
    return {"passed": completed.returncode == 0, "exit_code": completed.returncode, "summary": summary}


def outage(karmi: Path, services: ds.Services) -> dict[str, object]:
    with socket.socket() as address:
        address.bind(("127.0.0.1", 0))
        port = address.getsockname()[1]
    base = f"http://127.0.0.1:{port}"
    checks: dict[str, bool] = {}
    with tempfile.TemporaryDirectory(prefix="karmi-outage-") as temporary:
        server = serve(karmi, Path(temporary) / "unused.db", port,
                       database_url=ds.DATABASE_URL, redis_url=ds.REDIS_URL)
        try:
            checks["ready_on_postgres"] = wait_status(base + "/ready", 200, 30) == 200
            status, raw = request("POST", base + "/dev/token?role=customer")
            token = json.loads(raw)["token"] if status == 200 else None
            checks["synthetic_identity"] = token is not None
            first = request("POST", base + "/v1/messages", token=token,
                            body={"text": "Draft a short status note", "idempotency_key": "outage-before"})
            checks["message_before_outage"] = first[0] == 200

            services.container("stop", services.postgres)
            down_ready = request("GET", base + "/ready", timeout=10)
            down_message = request("POST", base + "/v1/messages", token=token, timeout=10,
                                   body={"text": "Draft during outage", "idempotency_key": "outage-during"})
            checks["ready_reports_failure"] = 500 <= down_ready[0] < 600
            checks["message_not_accepted_during_outage"] = down_message[0] != 200
            checks["no_internal_detail_leaked"] = not any(
                marker in body for marker in LEAK_MARKERS for body in (down_ready[1], down_message[1]))
            checks["process_survived_outage"] = server.poll() is None

            services.container("start", services.postgres)
            recovered = services.wait_postgres() and wait_status(base + "/ready", 200, 30) == 200
            checks["ready_recovers"] = recovered
            retried = request("POST", base + "/v1/messages", token=token,
                              body={"text": "Draft during outage", "idempotency_key": "outage-during"})
            replay = request("POST", base + "/v1/messages", token=token,
                             body={"text": "Draft a short status note", "idempotency_key": "outage-before"})
            checks["retry_after_recovery_succeeds"] = retried[0] == 200
            checks["pre_outage_request_deduplicated"] = (
                replay[0] == 200 and first[0] == 200
                and json.loads(replay[1]).get("run_id") == json.loads(first[1]).get("run_id"))

            services.container("stop", services.redis)
            checks["redis_outage_does_not_break_ready"] = wait_status(base + "/ready", 200, 10) == 200
        finally:
            stop(server)
    return {"checks": checks, "passed": all(checks.values()),
            "redis_note": "Karmi's app runtime does not use Redis (config only); Redis is exercised by "
                          "tests/integration. A Redis outage therefore must not affect /ready."}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("integration", "outage"))
    parser.add_argument("--karmi", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    karmi = args.karmi.resolve()
    evidence = args.output / f"dependency-{args.mode}.json"
    if not (karmi / ".venv/bin/python").is_file():
        result: dict[str, object] = {"status": "BLOCKED", "reason": "Karmi .venv/bin/python missing"}
    else:
        try:
            with ds.disposable() as services:
                body = integration(karmi) if args.mode == "integration" else outage(karmi, services)
            result = {"status": "PASS" if body["passed"] else "FAIL", "engine": services.engine, **body}
        except ds.Unavailable as error:
            result = {"status": "BLOCKED", "reason": str(error)}
    evidence.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"{args.mode}: {result['status']}", json.dumps(result.get("checks", result.get("reason", ""))))
    return {"PASS": 0, "FAIL": 1, "BLOCKED": 2}[str(result["status"])]


if __name__ == "__main__":
    sys.exit(main())
