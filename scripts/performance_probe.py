#!/usr/bin/env python3
"""Measure a disposable synthetic Karmi API and compare it with a measured, reviewed baseline.

Workload (loopback, SQLite, fake provider, synthetic development identity): startup to /ready,
then GET /ready, authenticated POST /v1/messages (unique idempotency keys; stays inside the
synthetic plan's 20-message allowance) and GET /v1/usage, each at fixed concurrency.

Thresholds are regression limits relative to the committed baseline measured on the same host
class, NOT production SLOs (see REGRESSION_RULE). Exit 0 PASS, 1 FAIL, 2 BLOCKED (no baseline,
different host class or unavailable runtime; evidence still written).
"""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import platform
import socket
import sqlite3
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "benchmarks/performance-baseline.json"
REGRESSION_RULE = ("route p95 <= max(3 x baseline p95, baseline p95 + 25 ms); route error rate 0%; "
                   "startup <= max(2 x baseline, baseline + 2000 ms); RSS <= 1.5 x baseline. Multipliers "
                   "absorb loopback scheduling noise observed between repeated local runs; they detect "
                   "order-of-magnitude regressions only and are not customer latency objectives.")
WORKLOAD = (("ready", "GET", "/ready", 40, 4), ("message", "POST", "/v1/messages", 15, 3),
            ("usage", "GET", "/v1/usage", 40, 4))


def serve(karmi: Path, db: Path, port: int, *, database_url: str | None = None,
          redis_url: str | None = None) -> subprocess.Popen[bytes]:
    python = karmi / ".venv/bin/python"
    if not python.is_file() or not (karmi / "src/daily_agent/api.py").is_file():
        raise RuntimeError("Karmi runtime or source unavailable")
    env = {key: os.environ[key] for key in ("PATH", "HOME", "LANG", "TMPDIR") if key in os.environ}
    env.update(PYTHONPATH=str(karmi / "src"), DAILY_AGENT_ENVIRONMENT="test",
               DAILY_AGENT_DATABASE_URL=database_url or f"sqlite+pysqlite:///{db}",
               DAILY_AGENT_LIVE_MODELS_ENABLED="false", DAILY_AGENT_PAID_CHECKOUT_ENABLED="false",
               DAILY_AGENT_WHATSAPP_ENABLED="false", DAILY_AGENT_ALLOW_DEVELOPMENT_AUTH="true")
    if redis_url:
        env["DAILY_AGENT_REDIS_URL"] = redis_url
    return subprocess.Popen([str(python), "-m", "uvicorn", "daily_agent.api:app",
                             "--host", "127.0.0.1", "--port", str(port), "--no-access-log"],
                            cwd=karmi, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def fetch(url: str, timeout: float = 2, *, method: str = "GET", token: str | None = None,
          body: dict[str, object] | None = None) -> tuple[int, float]:
    """HTTP status (0 = no response: refused/timeout) and elapsed seconds."""
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"} if data else {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=data, headers=headers, method=method),
                                    timeout=timeout) as response:
            response.read()
            return response.status, time.perf_counter() - start
    except urllib.error.HTTPError as error:  # a real 4xx/5xx response, not an outage
        error.close()
        return error.code, time.perf_counter() - start
    except (urllib.error.URLError, TimeoutError, ConnectionError):
        return 0, time.perf_counter() - start


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = (len(ordered) - 1) * fraction
    left = int(index)
    return round(ordered[left] + (ordered[min(left + 1, len(ordered) - 1)] - ordered[left]) * (index - left), 3)


def host_class() -> dict[str, object]:
    model = "unknown"
    cpuinfo = Path("/proc/cpuinfo")
    if cpuinfo.is_file():
        model = next((line.split(":", 1)[1].strip() for line in cpuinfo.read_text().splitlines()
                      if line.startswith("model name")), "unknown")
    return {"cpu_model": model, "cpu_count": os.cpu_count(), "machine": platform.machine(),
            "system": platform.system()}


def load(base: str, method: str, path: str, count: int, workers: int, token: str) -> dict[str, object]:
    def one(index: int) -> tuple[int, float]:
        body = ({"text": f"Draft status note {index}", "idempotency_key": f"perf-load-{index:04d}"}
                if method == "POST" else None)  # Karmi requires keys of >= 8 characters
        return fetch(base + path, 10, method=method, token=token, body=body)

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        begin = time.perf_counter()
        observations = list(pool.map(one, range(count)))
        elapsed = time.perf_counter() - begin
    times = [round(seconds * 1000, 3) for _, seconds in observations]
    errors = sum(not 200 <= code < 300 for code, _ in observations)
    return {"requests": count, "concurrency": workers, "p50_ms": percentile(times, .5),
            "p95_ms": percentile(times, .95), "p99_ms": percentile(times, .99),
            "throughput_per_second": round(count / elapsed, 3), "error_percent": round(100 * errors / count, 3)}


def measure(karmi: Path) -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="karmi-readiness-") as temporary:
        db = Path(temporary) / "probe.db"
        with socket.socket() as address:
            address.bind(("127.0.0.1", 0))
            port = address.getsockname()[1]
        base = f"http://127.0.0.1:{port}"
        started = time.perf_counter()
        server = serve(karmi, db, port)
        try:
            status = 0
            while time.perf_counter() - started < 15 and server.poll() is None:
                status, _ = fetch(base + "/ready")
                if status == 200:
                    break
                time.sleep(0.05)
            if status != 200:
                raise RuntimeError("disposable backend did not become ready")
            startup_ms = round((time.perf_counter() - started) * 1000, 3)
            with urllib.request.urlopen(urllib.request.Request(base + "/dev/token?role=customer", method="POST"),
                                        timeout=5) as response:
                token = json.load(response)["token"]
            routes = {name: load(base, method, path, count, workers, token)
                      for name, method, path, count, workers in WORKLOAD}
            db_times: list[float] = []
            with sqlite3.connect(db) as connection:
                for _ in range(50):
                    tick = time.perf_counter()
                    connection.execute("select count(*) from runs").fetchone()
                    db_times.append((time.perf_counter() - tick) * 1000)
            memory_kb: int | None = None
            cpu_seconds: float | None = None
            status_file, stat_file = Path(f"/proc/{server.pid}/status"), Path(f"/proc/{server.pid}/stat")
            if status_file.is_file():
                memory_kb = next((int(line.split()[1]) for line in status_file.read_text().splitlines()
                                  if line.startswith("VmRSS:")), None)
            if stat_file.is_file():
                fields = stat_file.read_text().rsplit(") ", 1)[1].split()
                cpu_seconds = round((int(fields[11]) + int(fields[12])) / os.sysconf("SC_CLK_TCK"), 3)
            return {"mode": "local_synthetic", "host": host_class(), "startup_ms": startup_ms,
                    "routes": routes, "db_count_runs_p50_ms": percentile(db_times, .5),
                    "db_count_runs_p95_ms": percentile(db_times, .95),
                    "memory_rss_kb": memory_kb, "cpu_seconds_total": cpu_seconds}
        finally:
            server.terminate()
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=5)


def compare(result: dict[str, object], baseline: dict[str, object]) -> list[str]:
    """Violated regression limits (empty = within limits)."""
    violations: list[str] = []
    routes, base_routes = result["routes"], baseline["routes"]
    assert isinstance(routes, dict) and isinstance(base_routes, dict)
    for name, observed in routes.items():
        expected = base_routes.get(name)
        if expected is None:
            violations.append(f"{name}: no baseline")
            continue
        limit = max(3 * expected["p95_ms"], expected["p95_ms"] + 25)
        if observed["p95_ms"] > limit:
            violations.append(f"{name}: p95 {observed['p95_ms']} ms > {round(limit, 3)} ms")
        if observed["error_percent"]:
            violations.append(f"{name}: {observed['error_percent']}% errors")
    startup, base_startup = result["startup_ms"], baseline["startup_ms"]
    assert isinstance(startup, (int, float)) and isinstance(base_startup, (int, float))
    if startup > max(2 * base_startup, base_startup + 2000):
        violations.append(f"startup {startup} ms exceeds limit from baseline {base_startup} ms")
    rss, base_rss = result.get("memory_rss_kb"), baseline.get("memory_rss_kb")
    if isinstance(rss, int) and isinstance(base_rss, int) and rss > 1.5 * base_rss:
        violations.append(f"RSS {rss} kB > 1.5 x baseline {base_rss} kB")
    return violations


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--karmi", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--accept-baseline", action="store_true", help=f"write {BASELINE.name} from this run")
    args = parser.parse_args()
    evidence = args.output / "performance.json"
    try:
        result: dict[str, object] = measure(args.karmi.resolve())
    except RuntimeError as error:
        evidence.write_text(json.dumps({"status": "BLOCKED", "reason": str(error)}, indent=2) + "\n")
        print(f"performance: BLOCKED ({error})")
        return 2
    result["regression_rule"] = REGRESSION_RULE
    if args.accept_baseline:
        BASELINE.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        status, detail = "BLOCKED", f"baseline written to {BASELINE.relative_to(ROOT)}; review and commit, then rerun"
    elif not BASELINE.is_file():
        status, detail = "BLOCKED", "no measured baseline; run ./test performance --accept-baseline"
    else:
        baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
        if baseline.get("host") != result["host"]:
            status, detail = "BLOCKED", "baseline was measured on a different host class; re-baseline on this host"
        else:
            violations = compare(result, baseline)
            status = "FAIL" if violations else "PASS"
            detail = "; ".join(violations) or "within regression limits of measured baseline"
    result.update(status=status, detail=detail)
    evidence.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"performance: {status} — {detail}")
    return {"PASS": 0, "FAIL": 1, "BLOCKED": 2}[status]


if __name__ == "__main__":
    raise SystemExit(main())
