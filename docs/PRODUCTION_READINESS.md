# Readiness gates and decision ownership

The first useful output is often `PRODUCTION READY: NO`: it distinguishes product failure from absent tools, human observation and approvals. The status belongs to exact Parakh and Karmi commits, dependency lock/dataset hashes, a candidate-matched Android APK and environment. A later commit invalidates affected evidence.

## Commands and report

`./test <stage>` writes `test-results/<UTC>-<id>/results.json`, JUnit `results.xml`, bounded redacted `logs/`, `production-readiness.json` and `PRODUCTION_READINESS_REPORT.md`. `./test production-check` (or `release-check`) also writes ignored root copies of the JSON/Markdown report. JSON cases include stage, name, UTC times, duration, exit code, status and log path. `PASS`, `FAIL`, `BLOCKED` and `NOT_RUN` remain distinct; JUnit renders BLOCKED/NOT_RUN as skipped but the release gate does **not** interpret skipped as passed. Local evidence is private: do not publish raw phone screenshots, request bodies, tokens or `.env`.

A stage can be PASS only if all its named subchecks passed. `STATIC`, `UNIT`, `COMPONENT`, `INTEGRATION`, `E2E`, `MOBILE`, `SECURITY`, `PERFORMANCE`, `RESILIENCE`, `PARAKH`, `KARMI`, `CROSS_SYSTEM`, `PRODUCTION_CONFIG`, `ROLLBACK`, `REAL_IDENTITY`, `PAID_PROVIDER`, `BILLING`, `CHANNEL_ELIGIBILITY`, `SLO_APPROVAL`, `DEPLOYMENT` are mandatory. An absent run is NOT_RUN; an unavailable tool, network, baseline or manual evidence is BLOCKED; a command or negative behavior assertion that fails is FAIL. Any non-PASS gate forces `production_ready: false` and `PRODUCTION READY: NO`.

Release states are derived mechanically by `release_state()` in `scripts/readiness.py` and written to `production-readiness.json` (`state`):

| State | Condition |
| --- | --- |
| DEVELOPMENT | Either checkout missing or dirty: results cannot be attributed to a commit. |
| TESTING | Both checkouts clean, but any engineering gate (`STATIC` … `ROLLBACK`) is FAIL/BLOCKED/NOT_RUN. |
| CANDIDATE | Every engineering gate PASS; an owner/external gate (`REAL_IDENTITY`, `PAID_PROVIDER`, `BILLING`, `CHANNEL_ELIGIBILITY`, `SLO_APPROVAL`, `DEPLOYMENT`) is not PASS. |
| RELEASE_READY | Every gate PASS for the exact recorded commits. |
| PRODUCTION | Never set by any command; requires an authorized human deployment record. |

The report also lists every non-passing check with its reason. Operator-owned production deployment, observed health/TLS/telemetry, approved budgets, authentication, rollback, payment/provider/channel eligibility and real device evidence are separate reviews. Never approve an external gate by assertion or by replacing it with a fake provider test. This harness records those gates BLOCKED until authorized, inspected real evidence exists.

## Gate coverage and limitations

- Parakh: its existing Makefile lint, doctor, unit/integration/E2E, frozen 60-case validation and isolated offline demo; regression snapshot compares the seed suite SHA and synthetic output digests. Fixture-only router quality says nothing about real Karmi actions or supported off-policy evaluation: Karmi's logged live propensity is 1.0 with no alternative-action support.
- Karmi: existing `scripts/tasks.py` lint/secret scan, mypy, unit/E2E, fake ModelLab; disposable PostgreSQL/Redis tests (Docker Compose or rootless Podman, same images/ports) are required, not replaced by SQLite. Flutter format/analyze/widget/golden/build are required; installed packages need candidate SHA and byte-for-byte APK proof. The current production auth/provider/payment/WhatsApp rollout does not pass simply because dev token and fake answer flows work.
- Cross-system: Karmi-exported synthetic telemetry must be accepted by Parakh with idempotency/privacy checks, a signed candidate must be verified, Karmi SHADOW evaluated without changing the live route, and bad signatures/unknown versions/duplicates rejected. Parakh's `sim/*` fixture is incompatible with Karmi's real action registry; a separately test-signed Karmi-action bundle only proves receiver/shadow mechanics, not Parakh's real-action quality gate.
- Security: native negative auth/config tests, tracked-file secret signatures (reviewed fake fixtures pinned by exact fingerprint), and `dependency-vulnerabilities`: `scripts/dependency_audit.py` sends only package names/versions from Karmi `requirements.lock`, Karmi `mobile/pubspec.lock` (hosted) and Parakh's installed runtime to the OSV batch API; any advisory is FAIL, no network is BLOCKED. TLS, production infrastructure and a manual pentest still require real evidence. Results never include matched secret values.
- Performance: `scripts/performance_probe.py` starts a disposable SQLite-backed loopback Karmi (fake provider, synthetic identity) and measures startup, then `GET /ready` (40 req, 4 workers), authenticated `POST /v1/messages` (15 unique keys, 3 workers, inside the synthetic 20-message allowance) and `GET /v1/usage` (40 req, 4 workers): p50/p95/p99, throughput, error %, DB `count(runs)` latency, RSS and CPU seconds. It compares with the committed measured baseline `benchmarks/performance-baseline.json` using the documented regression rule (route p95 ≤ max(3× baseline, baseline + 25 ms), 0% errors, startup ≤ max(2×, +2 s), RSS ≤ 1.5×). The multipliers were chosen after three repeated runs on the baseline host varied by up to ~1.5× at p95; they catch order-of-magnitude regressions, not customer objectives. A different host class is BLOCKED until re-baselined (`./test performance --accept-baseline`, review, commit). Production objectives are the separate owner gate `SLO_APPROVAL`.
- **Resilience.**
  - `failure-injection` stops and restarts a disposable backend.
  - `postgres-redis-outage` stops the disposable PostgreSQL under a running Karmi. It requires a 5xx `/ready` without internal detail, refused writes, a surviving process, recovery, a successful retry and an exact idempotent replay. It then stops Redis; Karmi's runtime does not use Redis, only its integration test does.
  - Phone-side network loss and recovery, and backend restart, are MOBILE journey steps.
  - Provider timeout-after-action reconciliation needs a real provider and remains part of `PAID_PROVIDER`.
- **Mobile.** `./test mobile-smoke` runs Karmi `mobile/tool/readiness_device.py --drive`. It:
  - builds the committed candidate APK and installs it;
  - proves the installed `base.apk` bytes match the build;
  - drives the 13 steps on the USB-attached phone against a disposable loopback backend reached through `adb reverse`;
  - observes the screen through the uiautomator tree, screenshots, the backend access log (status codes), Karmi-only logcat and the crash buffer.

  A dirty Karmi tree, a missing or ambiguous device, or an occupied port 8000 is BLOCKED. Any failing step is FAIL. The journey proves debug-build behaviour with development sign-in only.
- **Rollback.** `./test rollback` (`dependency_probe.py rollback` + `migration_rollback.py`) runs on a disposable PostgreSQL. It:
  - upgrades Karmi to head;
  - downgrades through every revision to the first, compares the reflected schema at each level on the way back up, and runs `alembic check` against the models;
  - requires the destructive base downgrade to refuse without its explicit opt-in;
  - rehearses a one-release rollback with live data: core rows are preserved, the upgrade succeeds again, `/ready` recovers and idempotent replay still returns the same run.

  The evidence lists the tables a one-release rollback discards; currently that is the Parakh routing and policy-bundle tables. The rehearsal first found and fixed a real Karmi bug: the `d0e1f3a5b6c7` downgrade crashed on every dialect. Not covered: running the previous release's binary against the downgraded schema, and restoring from a production backup. Both belong to the `DEPLOYMENT` review.

## CI and human verification

PR CI must run deterministic static/unit/component/contract/security checks. Main/master must run full synthetic checks with disposable dependencies and compare regression snapshots. A release workflow emits a candidate-bound artifact and report, and must never auto-promote a policy or production state.

CI cannot hold the phone. `./test mobile-smoke` on the operator's machine is the pre-release device gate: it is automated on one attached phone, or runs from human-reviewed evidence via `--mobile-evidence`. Real TalkBack speech and subjective accessibility still need a human. See `docs/MOBILE_TESTING.md` and `QUICKSTART_TESTING.md`.

Manual evidence must say timestamp, environment/device/build, expected and observed result, redacted artifact location, tester/reviewer and PASS/FAIL/BLOCKED/NOT_RUN. Re-run affected gates after source changes. An unresolved safety/data-integrity/financial failure never becomes a waiver; stop that gate, fix root cause and rerun.
