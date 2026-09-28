#!/usr/bin/env python3
"""Measure a disposable synthetic Karmi API, never the current customer database."""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import socket
import sqlite3
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path


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


def fetch(url: str, timeout: float = 2) -> tuple[int, float]:
    """HTTP status (0 = no response: refused/timeout) and elapsed seconds."""
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
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
                time.sleep(0.1)
            if status != 200:
                raise RuntimeError("disposable backend did not become ready")
            startup_ms = round((time.perf_counter() - started) * 1000, 3)
            count = 40
            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
                begin = time.perf_counter()
                observations = list(pool.map(fetch, [base + "/ready"] * count))
                elapsed = time.perf_counter() - begin
            times = [round(seconds * 1000, 3) for _, seconds in observations]
            failures = sum(code != 200 for code, _ in observations)
            db_times: list[float] = []
            with sqlite3.connect(db) as connection:
                for _ in range(20):
                    tick = time.perf_counter()
                    connection.execute("select 1").fetchone()
                    db_times.append((time.perf_counter() - tick) * 1000)
            memory_kb: int | None = None
            cpu_ticks: int | None = None
            status_file = Path(f"/proc/{server.pid}/status")
            stat_file = Path(f"/proc/{server.pid}/stat")
            if status_file.is_file():
                for line in status_file.read_text().splitlines():
                    if line.startswith("VmRSS:"):
                        memory_kb = int(line.split()[1])
            if stat_file.is_file():
                fields = stat_file.read_text().rsplit(") ", 1)[1].split()
                cpu_ticks = int(fields[11]) + int(fields[12])
            return {"mode": "local_synthetic", "route": "/ready", "requests": count,
                    "concurrency": 4, "startup_ms": startup_ms,
                    "p50_ms": percentile(times, .5), "p95_ms": percentile(times, .95),
                    "p99_ms": percentile(times, .99), "throughput_per_second": round(count / elapsed, 3),
                    "error_percent": round(100 * failures / count, 3),
                    "db_select1_p50_ms": percentile(db_times, .5),
                    "memory_rss_kb": memory_kb, "cpu_ticks_since_start": cpu_ticks,
                    "threshold_source": None, "release_thresholds_approved": False}
        finally:
            server.terminate()
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=5)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--karmi", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = measure(args.karmi.resolve())
    (args.output / "performance.json").write_text(json.dumps(result, indent=2) + "\n")
    if result["error_percent"]:
        print("local ready endpoint returned failures")
        return 1
    print("Measured disposable local /ready latency; approved release threshold absent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
