# Physical Android testing — Karmi candidate

This is a **development-only**, synthetic, non-production workflow. Parakh is an offline evaluator; it does not expose a phone-facing server. Karmi's FastAPI backend and Flutter Android app are the actual device under test. Do not use customer accounts, real provider keys, payments, WhatsApp or a production database. The current checkout does not implement production authentication: the development `/dev/token` flow is the only locally testable sign-in. Record that limitation as BLOCKED, never as a production auth PASS.

## Preconditions and revision identity

```sh
cd /home/rosso/Projects/Parakh
./test doctor                              # records exact Parakh/Karmi SHA and tool availability
cd ../Karmi
git rev-parse HEAD                         # record commit/branch; device probe needs readiness-harness (on parakh-shadow-integration)
adb devices -l                             # exactly one device marked 'device', USB debugging approved on phone
```

Install Karmi Python 3.12+ `.venv` following `../Karmi/README.md`. Install Flutter **3.47.5**, Android SDK with build-tools/platform-tools, JDK 17, and run `flutter doctor -v`; from `Karmi/mobile` run `flutter pub get`. Flutter and Docker were not on PATH at audit; until installed, building a candidate-matched APK and PostgreSQL/Redis integration are BLOCKED. The previously installed `ai.karmi.app` on the Pixel 9a has no known commit/build identity; do not mark it as this candidate's PASS.

## USB reverse: recommended safe local path

1. Use a disposable synthetic Karmi DB, with the dev backend bound **only** to `127.0.0.1`. In one terminal: `cd ../Karmi && .venv/bin/python scripts/tasks.py dev`. This uses `http://127.0.0.1:8000`, synthetic providers and `data/development.db`; for isolated new runs, set `DAILY_AGENT_DATABASE_URL=sqlite+pysqlite:////tmp/karmi-device-<run>.db` first and keep it separate from all existing data. Do not pass live provider/payment/channel flags or production credentials. `/health` and `/ready` must return 200; `/health` alone does not check DB.
2. In another terminal: `adb -s <serial> reverse tcp:8000 tcp:8000`; check `adb reverse --list`. This maps the phone's `127.0.0.1:8000` through USB to the laptop's loopback. No public server binding or CORS change is required. Android debug/profile manifest permits cleartext for this development route; release does not. Use only the device whose serial was recorded.
3. `cd ../Karmi/mobile && flutter run -d <serial> --debug --dart-define=API_BASE_URL=http://127.0.0.1:8000 --dart-define=KARMI_DEV_AUTH=true`. `flutter run` builds/installs the current source. Record Karmi SHA, Flutter version, generated APK SHA-256, Android package/version and serial **in the same run**; an earlier installed binary cannot establish provenance. To inspect the installed app, `adb -s <serial> shell pm path ai.karmi.app` and `adb -s <serial> shell dumpsys package ai.karmi.app` (do not paste full package dump into a shared log).
4. `cd ../Parakh && ./test mobile-smoke` starts/collects evidence from the attached device. It is intentionally nonzero until candidate matching and every required human-observed step is recorded. `./test mobile-e2e` adds longer journeys. Evidence is under ignored, private `test-results/<run>/`; review/redact screenshots before sharing. Report output never converts an unobserved screen into PASS.
5. Inspect app interactions on the phone: Welcome/sign-in; Chat send and response; usage; tasks and notes; safe API error; logout and expired session; app force-stop/restart; backend stop/restart; Wi-Fi/airplane-mode loss and recovery. For every step record expected vs actual, UTC timestamp, screenshot/log reference, and `PASS`, `FAIL`, `BLOCKED`, or `NOT_RUN`. Do not automate tapping consequential unrelated apps or change device accessibility settings without recording/restoring their original state. Android `adb logcat` can include unrelated private data: capture only scoped Karmi/tag lines and redact before sharing; private raw logs must remain in the ignored run directory.
6. After a run, `adb -s <serial> reverse --remove tcp:8000` and stop the dev server. Do not delete the user's existing DB. Explicitly record backend logs, 4xx/5xx failures, request IDs and observed latency where safe; never save token bodies, Authorization headers or customer content.

A shell/adb process check proves only that the process launched. A `/ready` request proves the endpoint and DB at that time. UI/auth/error/offline/recovery require actual observed phone interactions; an unreviewed screenshot or widget test is not equivalent to that observation. If Flutter is unavailable, the APK is not tied to the candidate, or the device is unavailable, mark those cases BLOCKED.

## Trusted Wi-Fi LAN alternative (not the default)

Only for a **private, isolated** development Wi-Fi with a single synthetic account/DB and firewall rule restricting the phone IP; dev tokens travel over cleartext and are not safe on shared/public Wi-Fi. Never bind `0.0.0.0` or expose port 8000 to the internet. On the laptop obtain its private IPv4 from `ip -4 addr show` and verify it belongs to the phone's Wi-Fi subnet. Temporarily allow only the phone's IP to TCP/8000 with the host firewall (exact command depends on the locally installed firewall; if no enforceable rule exists, use USB reverse instead). Start from Karmi root with `.venv/bin/python -m uvicorn daily_agent.api:app --host <laptop-private-ip> --port 8000` and `PYTHONPATH=src`, test `http://<laptop-private-ip>:8000/ready` from the phone browser, then build a **debug/profile** Flutter app with `--dart-define=API_BASE_URL=http://<laptop-private-ip>:8000 --dart-define=KARMI_DEV_AUTH=true`. Record phone IP/host IP, temporary firewall rule and time, then remove rule/stop server after testing. Android release builds disallow local cleartext; do not weaken the release manifest for a test. No cross-origin browser CORS workaround is needed by the native app; the bundled PWA uses same-origin relative API routes.

LAN-only phone testing without USB ADB cannot collect app logcat or prove installed binary provenance automatically; the tester must supply signed/dated manual device observations and version/build evidence. Never turn a missing observation into PASS.
