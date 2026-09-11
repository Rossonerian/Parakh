# Controlled live-pilot workflow

The initial plan is intentionally blocked: no candidate models, pricing snapshot, or spend authorization were supplied by the operator.

Create and display a development-only plan:

```bash
.venv/bin/python -m model_lab pilot plan \
  --suite benchmarks/seed_cases.jsonl \
  --out docs/live_pilots/plan-v0.1.0.json
.venv/bin/python -m model_lab pilot show docs/live_pilots/plan-v0.1.0.json
```

The plan contains exactly the 36 `train`/development cases. Calibration and holdout cases are not selected. It freezes the prompt revision, temperature, seed, output limit, timeout, concurrency, retries, repeats, candidate list, pricing snapshot field, spend ceiling field, and draft-only routing constraints.

The operator must regenerate the displayed plan with explicit candidates such as `provider:model[:revision]`, a pricing snapshot, and a maximum spend. A separate authorization record is required before any paid dispatch. `pilot run` fails closed without those fields and is not a paid-call shortcut.

No customer data is allowed. Pilot outputs must remain separate from synthetic evidence, be reconciled to the local cost ledger, graded with protected oracles, and blind-reviewed on a stratified calibration sample after execution. Production routing configuration is never modified.

