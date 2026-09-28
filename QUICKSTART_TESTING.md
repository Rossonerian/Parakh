# Testing quickstart (two checkouts)

You need two repositories side by side:

- **Parakh** is the offline evaluator and runs this evidence harness.
- **Karmi** is the FastAPI and Flutter app.

Branch requirements:

- The Parakh ↔ Karmi exchange exists on Karmi's `parakh-shadow-integration` branch, **not** Karmi main.
- The device driver and validator (`mobile/tool/device_driver.py`, `readiness_device.py`), the production-config audit (`scripts/readiness_config.py`) and the migration-downgrade fix are on the local `readiness-harness` branch, which is built on `parakh-shadow-integration`.
- If either branch is missing, the affected checks show as BLOCKED.

Don't assume these branches arrive with a blind `git pull`. Record the exact commits with `./test doctor` before testing.

```sh
cd /home/rosso/Projects/Parakh
python3 -m venv .venv && .venv/bin/python -m pip install -e '.[dev]'
cd ../Karmi
python3.12 -m venv .venv && .venv/bin/python -m pip install -c requirements.lock -e '.[dev]'
# Confirm the intended integration branch, then return to Parakh:
git branch --show-current
cd ../Parakh
./test doctor                 # tool availability; saves test-results/<run>/results.json/XML
```

1. **Infrastructure:** local synthetic development can use Karmi's SQLite and requires no container. Real disposable PostgreSQL/Redis tests need Docker/Compose (Karmi's own `scripts/tasks.py test-integration`) **or** rootless Podman: without Docker, `./test integration`/`resilience` start uniquely named `postgres:17-alpine`/`redis:8-alpine` containers on `127.0.0.1:55432/56379` (Karmi's compose values), refuse to run if either port is already bound, and remove the containers and volumes afterwards. Never substitute a shared DB. With neither engine, those checks are BLOCKED.
2. **Start Karmi (manual exploration only):** in a separate terminal run `cd ../Karmi && .venv/bin/python scripts/tasks.py dev`.
   - It binds `127.0.0.1:8000` and serves a synthetic account via `/dev/token`; check `http://127.0.0.1:8000/ready`.
   - This dev server does not implement production auth.
   - Every `./test` command starts its own disposable backend. Stop this one before `mobile-smoke`, which needs port 8000.
3. **Start Parakh:** it has no API server; run its offline CLI via `cd ../Parakh && .venv/bin/python -m model_lab --help` or `make PYTHON=.venv/bin/python tui` (optional console). The `./test benchmark` command runs its frozen 60-case synthetic demo in a new private run directory.
4. **Connect phone:**
   - Requires Flutter 3.47.5, JDK 17 and an Android SDK with `adb`.
   - Enable USB debugging and accept the RSA prompt. `adb devices -l` must list exactly one `device` with `usb:`.
   - Keep laptop port 8000 free, and keep the phone unlocked.
   - An older Karmi install signed with another key must be uninstalled first, which deletes its app data; only do that with the phone owner's approval.
   - Details: `docs/MOBILE_TESTING.md`.
5. **Mobile smoke:** `cd ../Parakh && ./test mobile-smoke` (use `mobile-e2e` to also tour the tabs). Karmi must be committed and clean. The command:
   - builds and installs the candidate APK;
   - starts a disposable loopback backend reached through `adb reverse`;
   - drives the 13 steps through uiautomator;
   - saves screenshots, the backend access log and Karmi-only logcat.

   It also clears Karmi's app data on the phone. For human-observed runs (for example over LAN), pass `--mobile-evidence /private/steps.json` instead; the format is in the mobile guide.
6. **Integration:** each command uses disposable PostgreSQL/Redis:
   - `./test integration` runs Parakh's integration tests, Karmi's disposable PostgreSQL/Redis suite and the two-repo synthetic shadow contract.
   - `./test resilience` stops and starts PostgreSQL under a running Karmi. It expects 5xx responses without internal detail, refused writes, recovery and idempotent replay, and it also stops Redis.
   - `./test rollback` walks Karmi's whole migration chain down and back on PostgreSQL and rehearses a one-release rollback with live data.
   - `./test benchmark` exercises both fake ModelLabs. No paid provider is used and no route is promoted.
7. **Full:** `./test full` records:
   - native lint, typecheck, unit, component, integration and E2E;
   - benchmark;
   - security;
   - performance;
   - resilience;
   - the phone journey;
   - rollback;
   - production config.

   It exits nonzero if any mandatory check is unavailable or failing. With no phone attached, MOBILE is BLOCKED. Logs are sanitized and stored in the private, ignored `test-results/`.
8. **Readiness:** `./test production-check` regenerates the full evidence plus root `production-readiness.json` and `PRODUCTION_READINESS_REPORT.md` (ignored generated files). Any FAIL, BLOCKED or NOT_RUN means `PRODUCTION READY: NO`; no command deploys or promotes a policy. Review `docs/PRODUCTION_READINESS.md` for external gates.

`./test --help` displays the full command vocabulary:

- `doctor`, `lint`, `typecheck`
- `unit`, `component`, `integration`, `e2e`
- `mobile-smoke`, `mobile-e2e`
- `security`, `performance`, `resilience`, `benchmark`, `rollback`
- `full`, `production-check`, `release-check`

If the checkouts are not adjacent, pass `--karmi /absolute/path/to/Karmi` after the subcommand, or set `PARAKH_KARMI_DIR` for the orchestrator. Never run live providers, payments, WhatsApp or production migrations as part of these commands.
