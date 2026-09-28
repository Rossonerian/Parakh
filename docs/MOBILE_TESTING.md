# Physical Android testing — Karmi candidate

This workflow is for **development only**. It uses synthetic data and is not production. Parakh is an offline evaluator and runs no server the phone could talk to. The system under test is Karmi: its FastAPI backend and its Flutter Android app (`ai.karmi.app`). Rules for every run:

- Never use customer accounts, real provider keys, payments, WhatsApp or a production database.
- The only sign-in the app can do locally is the development `/dev/token` flow. A passing phone journey therefore does **not** show that production identity works; that stays the owner gate `REAL_IDENTITY`.

## What `./test mobile-smoke` does

From the Parakh checkout, with one phone attached over USB:

```sh
./test mobile-smoke      # 13-step journey
./test mobile-e2e        # same journey, then checks that the Tasks, Usage and Memory tabs load
```

The command calls `../Karmi/mobile/tool/readiness_device.py --drive`, which does the following:

1. **Candidate build.** Refuses to build unless Karmi's working tree is clean. Then runs `flutter build apk --debug --dart-define=API_BASE_URL=http://127.0.0.1:8000 --dart-define=KARMI_DEV_AUTH=true` and `adb install -r -t` of that APK.
2. **Provenance.** Pulls the installed `base.apk` back from the phone and requires its SHA-256 to match the local build and the committed Karmi SHA.
3. **Disposable backend.** Starts a Karmi backend on **127.0.0.1:8000 only**, with:
   - a temporary SQLite database, deleted afterwards;
   - `DAILY_AGENT_ENVIRONMENT=test` and development sign-in;
   - live models, paid checkout and WhatsApp all disabled;
   - a random signing secret that exists only in memory.

   The phone reaches it only through `adb reverse tcp:8000 tcp:8000` over USB, so nothing is exposed on Wi-Fi.
4. **Journey.** Drives the app with `adb shell input` and reads the screen from the uiautomator accessibility tree. `pm clear ai.karmi.app` resets the app first, so every run starts signed out. Each step gets its own observation:

| # | Step | Automated observation |
|---|------|-----------------------|
| 1 | launch | `am start -W` of the launcher alias reports completion; a new app process exists; no Karmi entry in the logcat crash buffer for the whole run |
| 2 | initial_screen | welcome text is rendered (screenshot) |
| 3 | configuration | development sign-in is enabled (`KARMI_DEV_AUTH`), and the app's request arrived at the laptop backend, so `API_BASE_URL` resolved to the forwarded loopback |
| 4 | backend_reachable | the backend access log shows `POST /dev/token 200` from the phone |
| 5 | authentication | the signed-in chat screen and navigation are shown |
| 6 | primary_user_flow | typed draft request → a "Karmi replied … Completed" bubble for that text |
| 7 | api_request | exactly one `POST /v1/messages 200` for that send |
| 8 | api_error | the laptop uses up the synthetic allowance; the phone's send gets `429`; the app shows "Allowance reached" and nothing internal (no trace, exception or JSON body) |
| 9 | logout_expiration | the backend restarts with a rotated signing key; the next send gets `401`; the app shows "Session ended"; then sign in again, sign out from Settings, and a cold start stays signed out |
| 10 | app_restart | force-stop and relaunch; the stored session reopens chat with a new process |
| 11 | backend_restart | the backend stops (`/ready` unreachable), restarts on the same DB, and the existing session gets a completed reply |
| 12 | offline_handling | the USB transport is removed; the send is kept with "You're offline" / "Not sent: offline"; the backend received nothing |
| 13 | network_recovery | the transport is restored; Retry delivers the kept message (`POST /v1/messages 200`) |

A step whose prerequisite did not pass is recorded **BLOCKED**, never PASS. A failed expectation is **FAIL** with the reason.

5. **Validation.** `readiness_device.py` checks the evidence against the tree, APK, serial and step names. Any NOT_RUN, BLOCKED or FAIL makes the MOBILE gate non-PASS.

Evidence lands in `test-results/<run>/device/` (the directory is mode 700 and git-ignored):

- `evidence.json`: checks, steps, `observation_method`, APK hashes and serial.
- `driver/steps.json`
- `driver/screenshots/*.png`
- `driver/backend-access.log`: method, path and status only.
- `driver/logcat-app.txt`: lines from Karmi processes only. Other apps' private log lines are excluded.
- `driver/logcat-crash.txt`

The signing secret is redacted from the logs, and neither tokens nor Authorization headers are written.

**Side effects on the phone.** A run:

- replaces the installed Karmi debug app;
- clears its app data;
- leaves `adb reverse tcp:8000 tcp:8000` in place.

It does not touch any other app or setting. It never toggles Wi-Fi or airplane mode: the app talks to the backend over USB, so the harness simulates network loss by removing that USB transport.

## From phone + laptop to evidence (first time)

1. **Laptop tools.** Install the following, then run `flutter doctor -v`:
   - Flutter **3.47.5** on `PATH`;
   - an Android SDK with platform-tools (`adb`);
   - JDK 17;
   - Karmi's `.venv` (see `QUICKSTART_TESTING.md`).

   Then run `cd ../Karmi/mobile && flutter pub get`. Accepting Android SDK licences (`flutter doctor --android-licenses`) is your decision; the debug build worked here without it.
2. **Phone.**
   - Open Settings → About phone and tap *Build number* 7 times to enable Developer options.
   - In Developer options, enable *USB debugging*. Some OEMs also need *Install via USB* and *USB debugging (Security settings)*.
   - Connect the cable and accept the RSA fingerprint prompt.
3. **Detection.** `adb devices -l` must list **exactly one** device in state `device` with `usb:`. `unauthorized` means you need to accept the prompt on the phone. Two devices make the run BLOCKED; disconnect one.
4. **Old installs.** If the phone has a Karmi build signed with a different key, `adb install` fails with `INSTALL_FAILED_UPDATE_INCOMPATIBLE` and the run is BLOCKED. Uninstalling deletes that app's data. Do it only if the phone's owner agrees: `adb -s <serial> uninstall ai.karmi.app`.
5. **Port.** Nothing may listen on laptop port 8000. Check with `ss -ltnp | grep ':8000 '`. If you started `scripts/tasks.py dev` yourself, stop it; the driver refuses to reuse it and reports BLOCKED.
6. **Run.** From Parakh, run `./test mobile-smoke` and keep the phone unlocked with its screen on. A run takes about 2 minutes.
7. **Read the result.** The console prints one row per step. `test-results/<run>/results.json` has the same rows, and `device/evidence.json` has the provenance.

## Permissions and network configuration

- **App permissions.** The app only needs `android.permission.INTERNET` and requests no runtime permissions.
- **Cleartext.** `usesCleartextTraffic=true` is set **only** in the debug manifest (`android/app/src/debug`), so plain `http://127.0.0.1:8000` works in debug builds. Release builds keep cleartext off.
- **CORS.** CORS does not apply to the native app. The backend's CORS settings matter only for the browser PWA.
- **Base URL.** `API_BASE_URL` is fixed at build time. If it is not given, the app uses the emulator's `10.0.2.2`, which a physical phone cannot reach.

## Manual and exploratory sessions

For a session of your own (not recorded as evidence), use two terminals:

```sh
# Terminal 1 (Karmi): isolated synthetic DB, loopback only
cd ../Karmi && DAILY_AGENT_DATABASE_URL=sqlite+pysqlite:////tmp/karmi-device-manual.db .venv/bin/python scripts/tasks.py dev

# Terminal 2
adb -s <serial> reverse tcp:8000 tcp:8000 && adb -s <serial> reverse --list
cd ../Karmi/mobile && flutter run -d <serial> --debug \
  --dart-define=API_BASE_URL=http://127.0.0.1:8000 --dart-define=KARMI_DEV_AUTH=true
```

Useful commands:

| Purpose | Command |
|---------|---------|
| App logs (this process only) | `adb -s <serial> logcat --pid=$(adb -s <serial> shell pidof ai.karmi.app)` |
| Crashes | `adb -s <serial> logcat -b crash -d` |
| Launch | `adb -s <serial> shell am start -W -n ai.karmi.app/.LauncherAnanta` |
| Installed build | `adb -s <serial> shell pm path ai.karmi.app`, `adb shell dumpsys package ai.karmi.app \| grep version` |
| Screen tree (what the driver reads) | `adb -s <serial> exec-out uiautomator dump /dev/tty` |
| Screenshot | `adb -s <serial> exec-out screencap -p > shot.png` |
| Debugger | `flutter attach -d <serial>` |
| Clean up | `adb -s <serial> reverse --remove tcp:8000` |

**Human-reviewed evidence.** If you tested by hand (for example over LAN), use `./test mobile-smoke --mobile-evidence /private/steps.json`. The file must contain:

- `karmi_sha`, `apk_sha256` and `serial`, all matching the attached device;
- a non-empty `reviewer`;
- 13 ordered entries of the form `{id, status, observed_at, observation}`, using the step names above.

Observations must not contain tokens, passwords or customer content; the validator rejects credential-like text.

## Trusted Wi-Fi LAN alternative (not the default)

Use this only on a **private, isolated** Wi-Fi with synthetic data. Development tokens travel as cleartext HTTP, so this is never acceptable on shared or public Wi-Fi.

1. **Find the laptop's LAN IP.** Run `ip -4 route get 1.1.1.1` and read the `src` address, for example `192.168.1.20`. Confirm the phone is on the same subnet: Settings → Wi-Fi → network details.
2. **Bind the backend to that one address.** Never bind to `0.0.0.0`.

   ```sh
   cd ../Karmi && PYTHONPATH=src DAILY_AGENT_DATABASE_URL=sqlite+pysqlite:////tmp/karmi-lan.db \
     .venv/bin/python -m uvicorn daily_agent.api:app --host <laptop-ip> --port 8000
   ```

3. **Allow only the phone's IP.** Example for nftables; if your host uses a different firewall, apply the equivalent rule:

   ```sh
   sudo nft add table inet karmi_dev
   sudo nft add chain inet karmi_dev input '{ type filter hook input priority -1; }'
   sudo nft add rule inet karmi_dev input tcp dport 8000 ip saddr != <phone-ip> drop
   # afterwards: sudo nft delete table inet karmi_dev
   ```

4. **Verify the port.**
   - On the laptop: `ss -ltnp | grep ':8000 '` must show `<laptop-ip>:8000`, not `0.0.0.0`.
   - From the phone (Android's toybox `nc` has no `-z`): `adb shell "(printf 'GET /ready HTTP/1.0\r\n\r\n'; sleep 2) | nc <laptop-ip> 8000 | head -n 1"` must print `HTTP/1.1 200 OK`. Alternatively, open `http://<laptop-ip>:8000/ready` in the phone's browser; it must show `"status":"ready"`.
5. **Build and install for that address.** Run `flutter run -d <serial> --debug --dart-define=API_BASE_URL=http://<laptop-ip>:8000 --dart-define=KARMI_DEV_AUTH=true`.
6. **Test and record.** Do the 13 steps by hand, and record them as human-reviewed evidence (above).

Over LAN, the driver's automated journey does not apply: it drives network loss through `adb reverse`. Once testing ends, delete the firewall table and stop the server.

## What this does not prove

- The build is a debug build signed with the debug key, using development sign-in against a synthetic backend. That says nothing about the release build, production identity, TLS or store signing.
- TalkBack speech and real accessibility quality need a human listener. The accessibility tree only shows that labels exist.
- Chat transcripts are not stored on the device, so after a restart the chat screen is empty. That is the app's current design, not something the test missed.
- A Karmi tree that is dirty or has uncommitted changes makes `source_provenance` BLOCKED, and the MOBILE gate cannot pass.
