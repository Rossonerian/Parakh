#!/usr/bin/env python3
"""Exercise startup, stop, unavailable-backend and restart on disposable local data."""
from __future__ import annotations

import argparse
import json
import socket
import subprocess
import tempfile
import time
from pathlib import Path

from performance_probe import fetch, serve


def ready(base: str, server: subprocess.Popen[bytes]) -> bool:
    start = time.monotonic()
    while time.monotonic() - start < 15 and server.poll() is None:
        if fetch(base + "/ready")[0] == 200:
            return True
        time.sleep(0.1)
    return False


def stop(server: subprocess.Popen[bytes]) -> None:
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
    with tempfile.TemporaryDirectory(prefix="karmi-restart-") as temporary:
        db = Path(temporary) / "isolated.db"
        with socket.socket() as address:
            address.bind(("127.0.0.1", 0))
            port = address.getsockname()[1]
        base = f"http://127.0.0.1:{port}"
        initial = serve(args.karmi.resolve(), db, port)
        try:
            first = ready(base, initial)
        finally:
            stop(initial)
        unavailable = fetch(base + "/ready")[0] == 0
        restarted = serve(args.karmi.resolve(), db, port)
        try:
            recovered = ready(base, restarted)
        finally:
            stop(restarted)
        results = {"mode": "local_synthetic", "initial_ready": first,
                   "backend_unavailable_detected": unavailable, "restart_ready": recovered,
                   "database": "disposable SQLite; PostgreSQL/Redis outages require separate Compose gate",
                   "network_loss": "NOT_RUN: physical-device gate",
                   "provider_timeout": "NOT_RUN: separate deterministic provider-fault tests"}
        (args.output / "resilience.json").write_text(json.dumps(results, indent=2) + "\n")
        return 0 if all((first, unavailable, recovered)) else 1


if __name__ == "__main__":
    raise SystemExit(main())
