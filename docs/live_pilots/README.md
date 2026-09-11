# Controlled development-only live-pilot workflow

The laboratory is locally ready to prepare an authorized pilot, but no paid
dispatch is authorized by the committed template. The first pilot is fixed to
the 36 `train` cases only. Calibration and holdout cases remain untouched.

Copy the committed template outside Git. Do not put credentials in it.

```bash
cp docs/live_pilots/operator-input.template.yaml /secure/operator-input.yaml
.venv/bin/python -m model_lab pilot validate-input \
  --input /secure/operator-input.yaml \
  --suite benchmarks/seed_cases.jsonl
.venv/bin/python -m model_lab pilot plan \
  --operator-input /secure/operator-input.yaml \
  --suite benchmarks/seed_cases.jsonl \
  --constraint-map docs/live_pilots/router-constraint-map-v0.2.0.json \
  --out /secure/pilot-plan.json
.venv/bin/python -m model_lab pilot show /secure/pilot-plan.json
```

The strict input requires three to five unique `provider:model[:revision]`
candidates, matching displayed provider/model/revision data, a dated
same-currency pricing snapshot with explicit units, positive total and
per-model ceilings, a named/date-stamped authorization, and declarations that
the work is development-only with no customer data, calibration/holdout cases,
production-router changes, or external actions. The committed template keeps
commercial fields invalid by design.

Defaults are three template candidate slots and two repeats. A complete
36 × 3 × 2 plan has 216 base candidate calls; the frozen plan displays the
retry-inclusive maximum and conservative rate-card bound. It also hashes the
operator input, product-source manifest, constraint map, model configuration,
pricing snapshot, and exact case set. It rejects unknown providers, duplicate
candidates, missing units, nonpositive caps/budgets, currency mismatch,
non-train selection, and bounds exceeding declared ceilings.

`pilot run --allow-paid --plan /secure/pilot-plan.json` first prints all frozen
hashes, the exact cases, max calls, retries, judge/red-team settings, and spend
ceilings. It cannot dispatch until validation and the explicit authorization
are present. The first runner accepts only `concurrency: 1` and has judges and
red-team calls disabled; it retains a conservative provider-expense reservation
when provider cost remains unknown. CI and `make dev` never use this command
and remain fixture-only.

The product-derived constraint map is machine-readable in
`router-constraint-map-v0.2.0.json`. `router recommend --draft` loads it and
reports evaluated, satisfied, unavailable, and blocking constraints. It emits
draft evidence only and returns non-zero if a required product constraint is
unresolved. No command here changes application routing or subscription
entitlements.

After a real authorized pilot, use the deterministic gates in
`post-pilot-gates.md`: provider/local ledger reconciliation with unknowns as
`null`, protected grading and critical-failure reporting, calibration-only
stratified blind review, explicit calibration policy selection, a one-time
holdout lock with frozen policy/config hashes, and non-mutating router shadow
replay. These are prepared gates, not completed live-pilot evidence.
