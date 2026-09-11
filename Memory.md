# ModelLab implementation memory

Updated UTC: 2026-09-11
Branch: `main`; integrated pilot-preparation tree: `3004c37491b90af8b88807d321b06b829cdde76a`.

## Verified product-source intake

- Supplied root files and `/home/rosso/Downloads/daily-agent-blueprint.zip`
  were compared byte-for-byte. PRD, Architecture, Design, Tier Entitlements,
  Rules, Phases, Acceptance Testing, Model Testing Spec, and the supporting
  source-package documents all matched their archive members; no ambiguity was
  found.
- Byte-preserved snapshots are in `docs/product_sources/original/`. Current
  source inventory, paths, source revisions, and SHA-256 values are in
  `docs/product_sources/SOURCE_MANIFEST.json`; the append-only replacement of
  the previous missing-source state is in `IMPORT_AUDIT.jsonl`.
- Product source hashes for the primary routing constraints: PRD
  `779ff523…e38d054`; Architecture `f27714fb…7cfa1f`; Design
  `b15e81be…b03de1`; Tier Entitlements `a5951649…3c3f3a`.
- `docs/live_pilots/router-constraint-map-v0.2.0.json` is the active
  machine-readable draft constraint map. Its citations reference imported
  file, heading, and source hash. It preserves plan prices/quotas, provider
  allowlists, production cost ceilings, launch geography/channel eligibility,
  and measured staging evidence as `UNRESOLVED_OWNER_INPUT`.

## Current implementation

- Accepted lab safeguards remain intact: structural candidate-only isolation,
  protected-oracle grading, immutable raw evidence, train/calibration/holdout
  separation, fixture-only CI, budget controls, Promptfoo fixture controls,
  and draft-only routing.
- Strict development-only operator input and immutable plan conversion are in
  `model_lab/operator_input.py`; template and command documentation are under
  `docs/live_pilots/`. It requires 3–5 supported candidates, model/revision
  metadata, dated price/unit snapshot, frozen prompt revision and execution
  limits, `concurrency`, repeats, budgets, and named/date-stamped approval.
  The default 36 × 3 × 2 plan has 216 base calls; retry-inclusive bound and all
  hashes are frozen in the plan.
- `pilot run --allow-paid` displays source/constraint/model/pricing/case hashes,
  exact cases, max calls, retries, judge/red-team settings, and ceilings before
  it can dispatch. It rejects incomplete plans, non-train selection,
  unavailable provider configuration, enabled judge/red-team work, and any
  non-`1` concurrency setting for this first runner. No live command was run.
- Cost reservations now retain their conservative amount whenever provider
  cost remains unknown; this avoids treating unmetered/unknown attempts as
  free. Provider expense remains distinct from customer usage.
- Offline post-pilot helpers exist for provider/local reconciliation with null
  unknowns, protected critical-failure reports, calibration-only stratified
  blind review export, explicit calibration selection, one-time frozen holdout
  gate, and non-mutating router shadow replay.

## Evidence and handoffs

- Worker `Archimedes` (requested Luna/medium; effective runtime identity not
  exposed) committed `791c9d1` for post-pilot gates; focused verification: 6
  tests passed.
- Worker `Banach` (requested Luna/medium; effective runtime identity not
  exposed) committed `f57fd0a` for strict operator input; focused verification:
  9 tests passed.
- Boss integrated source constraints, dispatch preview/preflight, conservative
  unknown-cost reservation, docs, and source import in `3004c37`.
- On the integrated tree: `make PYTHON=.venv/bin/python test-release` passed
  (`doctor`, 57 pytest tests, 60-case offline E2E); direct full pytest passed
  57 tests; compileall passed; suite validation reported 60 cases, 15 families,
  36/12/12 train/calibration/holdout; two distinct disposable `make dev` runs
  completed using fake providers only.
- Read-only Terra/medium Supervisor review of exact commit `3004c37` returned
  `REWORK`: retry costs could be understated, frozen plan hashes were not
  recomputed before dispatch, and constraint citations were not bound to bytes.
  Requested model was `gpt-5.6-terra`; effective model identity was not exposed.
- Commit `4004808` addresses all three findings: retry settlement remains
  unknown unless every retry cost is known; paid preflight verifies plan,
  case-set, model, pricing, source-manifest, and constraint-map hashes; routing
  validates every citation against the manifest and imported source bytes.
  Focused and full deterministic verification passed 60 tests. A final exact
  tree Supervisor review was requested for `20ebc9b` but the Terra runtime
  returned a usage-limit error before reviewing. No final approval verdict is
  claimed; this is an available-review-capacity limitation, not a waived gate.
- After the rework and Memory commit, `make PYTHON=.venv/bin/python
  test-release` passed with 60 tests and the 60-case offline E2E. Two further
  disposable `make dev` runs were invoked on the final tree; both use fake
  providers and separate `lab-data/dev.*` outputs.

## Owner inputs and boundaries

- No paid provider calls, live provider calls, customer data, paid accounts,
  customer messages, deployment, push, migration, or production-router changes
  were made.
- Root `README.md` and root PRD/Design/Tier/Sources/Start prompt files remain
  user-supplied unstaged workspace material. Their verified source bytes were
  imported under `docs/product_sources/original/`; do not overwrite or discard
  the root copies.
- Synthetic 60-case results are laboratory evidence only, never a claim of
  real-model performance, cost, tier eligibility, or production routing
  readiness.

## Next three actions

1. Obtain a Terra (or equivalently independent, read-only) Supervisor verdict
   on exact commit `20ebc9b` when review capacity is available.
2. Owner supplies a complete secure operator input: 3–5 provider:model[:revision]
   candidates, verified dated rate card/units, caps, `concurrency: 1`, ceilings,
   and named/date-stamped approved maximum spend.
3. Validate and freeze the plan; only then, under explicit `--allow-paid`, run
   the development-only train pilot and execute the prepared reconciliation,
   protected grading, calibration review, policy freeze, holdout, and shadow
   gates.
