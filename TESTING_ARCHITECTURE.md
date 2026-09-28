# Testing architecture — two-repository candidate

Parakh is the orchestration/evidence home; Karmi keeps its native `scripts/tasks.py` and Flutter tests. `./test` never changes a production route, pays a provider, starts a customer channel or changes subscriptions. It reports what ran, what failed and what cannot yet be tested. A green synthetic run is **not** a production release.

## Layers and observable contracts

| Layer | Command/gate | Proof and limitations |
| --- | --- | --- |
| L0 static | `lint`, `typecheck`, `security` | Native ruff/mypy/Flutter analyze/format where available, config/schema/lock and dependency checks. Missing tool or scan is BLOCKED. |
| L1 unit | `unit` | Both native pytest suites and Flutter widget tests; synthetic/isolated, exact exits. |
| L2 component | `component` | Karmi API/auth/DB tests, routing/telemetry, Parakh schema/optimizer tests; Postgres/Redis tests run under `integration` on disposable Docker or rootless Podman containers. |
| L3 integration | `integration` | Existing disposable DB/Redis test and real cross-repo schema/fixture/shadow contract; fixture-only versus actual service evidence labeled separately. |
| L4 E2E | `e2e` | Karmi FastAPI and owned PWA existing E2E; Parakh offline full-pipeline demo. Running tests does not establish a browser journey or production authentication. |
| L5 device | `mobile-smoke`, `mobile-e2e` | Candidate-matched debug/profile APK on physical device, adb-reverse or constrained private LAN, human-observed flows; each step carries a status and artifact. Device absence/provenance mismatch BLOCKED. |
| L6 resilience | `resilience` | Failures injected only in disposable local services; verify recovery, no duplicate action or route promotion and honest unknown outcomes. No destructive shared DB operations. |
| L7 security | `security` | Native secret scan + checked configs + negative auth/authorization/contract checks; tracked-secret signatures with fingerprint-pinned fixtures; OSV known-vulnerability audit of Karmi Python/Pub locks and Parakh's installed runtime (offline = BLOCKED). Scan results never include credential matches in logs. |
| L8 performance | `performance` | Disposable Karmi: startup, `/ready`, authenticated `/v1/messages`, `/v1/usage` p50/p95/p99, throughput, error %, DB latency, RSS, CPU; compared with a committed measured baseline under a documented regression rule. Local limits ≠ production SLO (owner gate `SLO_APPROVAL`). |
| L9 release | `production-check`, `release-check` | Validate evidence on both exact SHAs, all mandatory gates and config/rollback/provider/channel/security/device approvals. Missing/blocked/not-run yields `production_ready: false`; never set `PRODUCTION` automatically. |

## Evidence format

- Each invocation writes a unique `test-results/<UTC timestamp>-<run id>/` with a manifest (`schema_version`, command version, Parakh/Karmi Git SHA/branch/dirty state, Python/Flutter/device versions where observed, benchmark SHA-256 and seed, dependency-lock SHA, execution environment). `cases[]`: gate ID, test name, status `PASS|FAIL|BLOCKED|NOT_RUN`, start/end UTC, duration, exit code, safe reason, bounded log path, artifact hashes and provenance. JUnit XML mirrors results, mapping BLOCKED/NOT_RUN to skipped **but never to PASS**. Persist raw private phone/screenshots only in ignored local results, no CI upload by default.
- Case evidence must come from actual process exit/HTTP/DB/device observation; no single test can mark another gate PASS. Logs omit body/authorization/cookie, private screenshots, `.env`, private keys and token responses. Never serialize entire process environment. Errors are safe strings with exact command names/exit codes, not raw exception dumps containing credentials.
- A report is reconstructed only from this run and from explicitly imported signed/manual evidence with matching SHAs/build provenance; old or absent files are not treated as completed gates. A run may contain fixture benchmark measurements but has no authorized paid or production results.
- A baseline snapshot requires reviewed fixture hashes and labeled local conditions. Do not copy synthetic latency or cost as a production threshold. Regression comparison is meaningful only for matching dataset/seed/config and candidate revisions.

## Mandatory release matrix and state transitions

`STATIC`, `UNIT`, `COMPONENT`, `INTEGRATION`, `E2E`, `MOBILE`, `SECURITY`, `PERFORMANCE`, `RESILIENCE`, `PARAKH`, `KARMI`, `CROSS_SYSTEM`, `PRODUCTION_CONFIG`, `ROLLBACK` are mandatory, plus applicable identity, finance, provider/payment and channel approval gates from `Phases.md`. Each gate has four states; any `FAIL`, `BLOCKED` or `NOT_RUN` means `PRODUCTION READY: NO`. `DEVELOPMENT → TESTING → CANDIDATE → RELEASE_READY` needs evidence/reviewer at each boundary; the tool may suggest `RELEASE_READY` only when all required gates pass on one candidate. `PRODUCTION` requires a separate authorized human deployment and observed smoke; no automation promotes it.

CI pull requests run available non-live static/unit/component/contract/security checks; main runs the full synthetic offline suite and disposable integration services; release builds produce an evidence report, not an automatic approval. Physical phone testing remains a mandatory manual pre-release gate outside CI. A missing second checkout or unavailable Docker/Flutter is an environmental BLOCKED case, not a bypass.

## Trust boundaries and agents

Testing manager (OMP project supervisor) owns scope, audit, integration and release decision. Bounded Karmi backend, Parakh evaluation, integration, mobile, security, performance and read-only release verifier assignments may be created when independent slices justify them. OMP planner advises; managed Gemini High workers/verifier start only via `agent-team-orca-start` with stable IDs, disjoint worktrees and recoverable commits. Prefer three concurrent workers, four only with documented need; independent verifier checks exact integrated tree. Workers cannot declare production readiness. No normal OpenAI worker route is configured; quota exhaustion means checkpoint/pause.

Cross-repo protocol stays JSON with Karmi `SHADOW` only. Parakh's `sim/*` artifact is *not* accepted by real Karmi's action registry; a test-signed Karmi-action fixture proves compatibility of transport and shadow, not that Parakh has validated that policy for deployment. Parakh's unsupported real-action verification gate remains BLOCKED pending authorized benchmark/provider evidence. The permanent test must assert signature, schema, duplicate handling, unknown version, rollback to unchanged live route and shadow-only output; an incompatible contract fails rather than being silently coerced.
