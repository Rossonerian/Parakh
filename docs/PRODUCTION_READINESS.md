# Readiness gates and decision ownership

The first useful output is often `PRODUCTION READY: NO`: it distinguishes product failure from absent tools, human observation and approvals. The status belongs to exact Parakh and Karmi commits, dependency lock/dataset hashes, a candidate-matched Android APK and environment. A later commit invalidates affected evidence.

## Commands and report

`./test <stage>` writes `test-results/<UTC>-<id>/results.json`, JUnit `results.xml`, bounded redacted `logs/`, `production-readiness.json` and `PRODUCTION_READINESS_REPORT.md`. `./test production-check` (or `release-check`) also writes ignored root copies of the JSON/Markdown report. JSON cases include stage, name, UTC times, duration, exit code, status and log path. `PASS`, `FAIL`, `BLOCKED` and `NOT_RUN` remain distinct; JUnit renders BLOCKED/NOT_RUN as skipped but the release gate does **not** interpret skipped as passed. Local evidence is private: do not publish raw phone screenshots, request bodies, tokens or `.env`.

A stage can be PASS only if all its named subchecks passed. `STATIC`, `UNIT`, `COMPONENT`, `INTEGRATION`, `E2E`, `MOBILE`, `SECURITY`, `PERFORMANCE`, `RESILIENCE`, `PARAKH`, `KARMI`, `CROSS_SYSTEM`, `PRODUCTION_CONFIG`, `ROLLBACK`, `REAL_IDENTITY`, `PAID_PROVIDER`, `BILLING`, `CHANNEL_ELIGIBILITY`, `DEPLOYMENT` are mandatory. An absent run is NOT_RUN; absent Flutter/Docker or manual evidence is BLOCKED; a command or negative behavior assertion that fails is FAIL. Any non-PASS gate forces `production_ready: false` and `PRODUCTION READY: NO`.

Release states are derived mechanically by `release_state()` in `scripts/readiness.py` and written to `production-readiness.json` (`state`):

| State | Condition |
| --- | --- |
| DEVELOPMENT | Either checkout missing or dirty: results cannot be attributed to a commit. |
| TESTING | Both checkouts clean, but any engineering gate (`STATIC` … `ROLLBACK`) is FAIL/BLOCKED/NOT_RUN. |
| CANDIDATE | Every engineering gate PASS; an owner/external gate (`REAL_IDENTITY`, `PAID_PROVIDER`, `BILLING`, `CHANNEL_ELIGIBILITY`, `DEPLOYMENT`) is not PASS. |
| RELEASE_READY | Every gate PASS for the exact recorded commits. |
| PRODUCTION | Never set by any command; requires an authorized human deployment record. |

The report also lists every non-passing check with its reason. Operator-owned production deployment, observed health/TLS/telemetry, approved budgets, authentication, rollback, payment/provider/channel eligibility and real device evidence are separate reviews. Never approve an external gate by assertion or by replacing it with a fake provider test. This harness records those gates BLOCKED until authorized, inspected real evidence exists.

## Gate coverage and limitations

- Parakh: its existing Makefile lint, doctor, unit/integration/E2E, frozen 60-case validation and isolated offline demo; regression snapshot compares the seed suite SHA and synthetic output digests. Fixture-only router quality says nothing about real Karmi actions or supported off-policy evaluation: Karmi's logged live propensity is 1.0 with no alternative-action support.
- Karmi: existing `scripts/tasks.py` lint/secret scan, mypy, unit/E2E, fake ModelLab; disposable PostgreSQL/Redis tests (Docker Compose or rootless Podman, same images/ports) are required, not replaced by SQLite. Flutter format/analyze/widget/golden/build are required; installed packages need candidate SHA and byte-for-byte APK proof. The current production auth/provider/payment/WhatsApp rollout does not pass simply because dev token and fake answer flows work.
- Cross-system: Karmi-exported synthetic telemetry must be accepted by Parakh with idempotency/privacy checks, a signed candidate must be verified, Karmi SHADOW evaluated without changing the live route, and bad signatures/unknown versions/duplicates rejected. Parakh's `sim/*` fixture is incompatible with Karmi's real action registry; a separately test-signed Karmi-action bundle only proves receiver/shadow mechanics, not Parakh's real-action quality gate.
- Security scan covers native tests, narrow tracked-file secret signatures and configuration checks; vulnerability database, TLS, production infrastructure and manual pentest require real evidence. Results never include matched secret values.
- Performance local sample uses only a disposable SQLite-backed loopback server with no live models. `performance.json` reports startup, /ready latency p50/p95/p99, throughput/error rate, DB `SELECT 1` latency, CPU ticks and RSS. This is **not** a customer workload or approved production SLO; missing approved thresholds BLOCK the production performance gate. Device profile/TalkBack/low-end hardware remain separate requirements.
- Resilience: `failure-injection` stops/restarts a disposable backend; `postgres-redis-outage` stops the disposable PostgreSQL under a running Karmi and requires 5xx `/ready` without internal detail, refused writes, a surviving process, recovery, successful retry and exact idempotent replay, then stops Redis (Karmi's runtime does not use Redis; only its integration test does). Device Wi-Fi loss, provider timeout-after-action reconciliation and restore remain separate required cases; missing evidence stays BLOCKED.

## CI and human verification

PR CI must run deterministic static/unit/component/contract/security checks. Main/master must run full synthetic checks with disposable Docker dependencies and compare regression snapshots. A release workflow emits candidate-bound artifact/report and must never auto-promote policy or production state. Phone checks cannot require a device in CI; the operator uses a reproducible candidate APK and records 13 observed phone steps separately. App accessibility and real TalkBack speech require a human, not just an adb accessibility tree or widget test. See `docs/MOBILE_TESTING.md` and `QUICKSTART_TESTING.md`.

Manual evidence must say timestamp, environment/device/build, expected and observed result, redacted artifact location, tester/reviewer and PASS/FAIL/BLOCKED/NOT_RUN. Re-run affected gates after source changes. An unresolved safety/data-integrity/financial failure never becomes a waiver; stop that gate, fix root cause and rerun.
