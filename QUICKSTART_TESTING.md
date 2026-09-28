# Testing quickstart (two checkouts)

Two repositories are required side by side. Parakh is the offline evaluator/evidence runner; Karmi is the FastAPI and Flutter app. The Parakh ↔ Karmi exchange currently exists on Karmi's `parakh-shadow-integration` branch, **not** Karmi main. Do not blindly `git pull` and assume that branch is present. Record exact commits with `./test doctor` before testing; neither this guide nor historical evidence proves a changed checkout.

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

1. **Infrastructure:** local synthetic development can use Karmi's SQLite and requires no container. For real disposable PostgreSQL/Redis tests install Docker/Compose first; Karmi's `scripts/tasks.py test-integration` starts only the named `daily-agent-test` services and removes their volumes. Do not substitute a shared DB. If Docker is unavailable `./test integration` records BLOCKED.
2. **Start Karmi:** in a separate terminal `cd ../Karmi && .venv/bin/python scripts/tasks.py dev`. It binds `127.0.0.1:8000` by default and serves a synthetic account via `/dev/token`. Test `http://127.0.0.1:8000/ready`. This dev server is not a production-auth implementation.
3. **Start Parakh:** it has no API server; run its offline CLI via `cd ../Parakh && .venv/bin/python -m model_lab --help` or `make PYTHON=.venv/bin/python tui` (optional console). The `./test benchmark` command runs its frozen 60-case synthetic demo in a new private run directory.
4. **Connect phone:** Flutter 3.47.5/JDK17/Android SDK required. With one authorized USB Android device `adb devices -l`, run `adb reverse tcp:8000 tcp:8000`; from `Karmi/mobile` run `flutter pub get && flutter run --debug --dart-define=API_BASE_URL=http://127.0.0.1:8000 --dart-define=KARMI_DEV_AUTH=true`. Save the APK and compare its SHA with the installed APK. See `docs/MOBILE_TESTING.md` for isolation, safe LAN variant and 13 manual observations.
5. **Mobile evidence:** `cd ../Parakh && ./test mobile-smoke --mobile-evidence /private/observed-steps.json`; omit `--mobile-evidence` for probes only: all unobserved phone steps remain NOT_RUN. The reviewer file requires `karmi_sha`, `apk_sha256`, `serial`, `reviewer`, and 13 ordered entries `{id,status,observed_at,observation}` matching the named steps in `../Karmi/mobile/tool/readiness_device.py`. Do not save secrets/customer content in observations.
6. **Integration:** `./test integration` runs Parakh integration tests, Karmi's disposable Docker DB/Redis suite and the two-repo synthetic shadow contract. `./test benchmark` exercises both fake ModelLabs; no paid provider or route promotion.
7. **Full:** `./test full` records native lint/type/unit/component/integration/E2E, mobile, security, performance, resilience and production config. It exits nonzero for any unavailable/failing mandatory check. Logs are sanitized and stored in private ignored `test-results/`.
8. **Readiness:** `./test production-check` regenerates the full evidence plus root `production-readiness.json` and `PRODUCTION_READINESS_REPORT.md` (ignored generated files). Any FAIL, BLOCKED or NOT_RUN means `PRODUCTION READY: NO`; no command deploys or promotes a policy. Review `docs/PRODUCTION_READINESS.md` for external gates.

`./test --help` displays the full command vocabulary (`doctor`, `lint`, `typecheck`, `unit`, `component`, `integration`, `e2e`, `mobile-smoke`, `mobile-e2e`, `security`, `performance`, `resilience`, `benchmark`, `full`, `production-check`, `release-check`). If checkouts are not adjacent, pass `--karmi /absolute/path/to/Karmi` after the subcommand or set `PARAKH_KARMI_DIR` for the orchestrator. Never run live providers, payment, WhatsApp or production migrations as part of these commands.
