"""Disposable PostgreSQL/Redis for Karmi tests: Docker or rootless Podman, loopback only.

Mirrors Karmi's compose.yaml (images, credentials, ports). Karmi's integration tests refuse any
other address, so the ports are fixed; if either is already bound, nothing is started or touched.
Containers are uniquely named and always removed with their volumes on exit.
"""
from __future__ import annotations

import shutil
import socket
import subprocess
import time
import uuid
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass

POSTGRES_PORT = 55432
REDIS_PORT = 56379
# Synthetic credentials copied from Karmi compose.yaml; the database is created and destroyed here.
DATABASE_URL = (f"postgresql+psycopg://daily_agent_test:daily_agent_test@127.0.0.1:{POSTGRES_PORT}"
                "/daily_agent_test")
REDIS_URL = f"redis://127.0.0.1:{REDIS_PORT}/15"


class Unavailable(RuntimeError):
    """Environment cannot provide disposable services (reported as BLOCKED, never PASS)."""


@dataclass
class Services:
    engine: str
    postgres: str
    redis: str

    def container(self, action: str, name: str) -> None:
        subprocess.run([self.engine, action, name], check=True, capture_output=True, timeout=60)

    def wait_postgres(self, timeout: float = 60) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            probe = subprocess.run([self.engine, "exec", self.postgres, "pg_isready", "-h", "127.0.0.1",
                                    "-U", "daily_agent_test", "-d", "daily_agent_test"],
                                   capture_output=True, timeout=20, check=False)
            if probe.returncode == 0 and port_open(POSTGRES_PORT):
                return True
            time.sleep(0.5)
        return False


def engine() -> str | None:
    return shutil.which("docker") or shutil.which("podman")


def port_open(port: int) -> bool:
    with socket.socket() as probe:
        probe.settimeout(0.5)
        return probe.connect_ex(("127.0.0.1", port)) == 0


@contextmanager
def disposable() -> Generator[Services, None, None]:
    runtime = engine()
    if runtime is None:
        raise Unavailable("neither docker nor podman installed")
    for port in (POSTGRES_PORT, REDIS_PORT):
        if port_open(port):
            raise Unavailable(f"127.0.0.1:{port} already in use; refusing to reuse or stop it")
    suffix = uuid.uuid4().hex[:8]
    services = Services(runtime, f"parakh-readiness-pg-{suffix}", f"parakh-readiness-redis-{suffix}")
    started: list[str] = []
    try:
        for name, args in (
            (services.postgres, ["-p", f"127.0.0.1:{POSTGRES_PORT}:5432",
                                 "-e", "POSTGRES_DB=daily_agent_test", "-e", "POSTGRES_USER=daily_agent_test",
                                 "-e", "POSTGRES_PASSWORD=daily_agent_test", "docker.io/library/postgres:17-alpine"]),
            (services.redis, ["-p", f"127.0.0.1:{REDIS_PORT}:6379", "docker.io/library/redis:8-alpine",
                              "redis-server", "--save", "", "--appendonly", "no"]),
        ):
            created = subprocess.run([runtime, "run", "-d", "--name", name, *args],
                                     capture_output=True, text=True, timeout=600, check=False)
            if created.returncode != 0:
                raise Unavailable(f"{runtime} could not start {name.split('-')[2]}: "
                                  f"{created.stderr.strip().splitlines()[-1:] or ['unknown error']}")
            started.append(name)
        if not services.wait_postgres():
            raise Unavailable("disposable PostgreSQL did not become ready within 60s")
        deadline = time.monotonic() + 30
        while not port_open(REDIS_PORT):
            if time.monotonic() > deadline:
                raise Unavailable("disposable Redis did not open its port within 30s")
            time.sleep(0.2)
        yield services
    finally:
        for name in started:
            subprocess.run([runtime, "rm", "-f", "-v", name], capture_output=True, timeout=120, check=False)
