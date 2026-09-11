# Operator input

The committed `operator-input.template.yaml` is intentionally invalid: it
contains no candidate IDs, prices, spend ceiling, or authorization. Copy it
outside Git, fill it with three to five supported `ollama:model[:revision]` or
`openrouter:model[:revision]` candidates, and keep credentials out of the file.

The validator requires `development_only: true`, all four exclusion
declarations, the 36 `train` cases only, dated same-currency pricing, positive
caps and ceilings, and `authorization.approved: true`. The default repeat count
is two. It calculates both the base call count and a conservative maximum
including retries. Pricing is interpreted as currency units per million tokens,
with a per-call tool rate; cache and reasoning rates are included in the
conservative bound. Unknown prices are rejected rather than estimated.

Validate a completed input without dispatching anything:

```bash
.venv/bin/python -m model_lab pilot validate-input \
  --input operator-input.yaml \
  --suite benchmarks/seed_cases.jsonl
```

Convert it to an immutable, hash-bound plan:

```bash
.venv/bin/python -m model_lab pilot plan \
  --operator-input operator-input.yaml \
  --suite benchmarks/seed_cases.jsonl \
  --source-manifest docs/product_sources/SOURCE_MANIFEST.json \
  --constraint-map docs/live_pilots/router-constraint-map-v0.2.0.json \
  --out lab-data/live-pilot-plan.json
```

The command prints the complete plan, including the exact 36 case IDs, source
and constraint hashes, 216 base calls for the default three candidates and two
repeats, retry-inclusive maximum calls, and conservative cost bounds. The
committed template is intentionally invalid, so no paid dispatch can be
authorized from it.

The same conversion is available from Python:

```python
from model_lab.operator_input import build_immutable_plan, load_operator_input, write_immutable_plan

value = load_operator_input("operator-input.yaml")
plan = build_immutable_plan(value, suite_path="benchmarks/seed_cases.jsonl")
write_immutable_plan(plan, "pilot-plan.json")
```

The plan includes exact case IDs, maximum calls, per-candidate bounds, total
bound, and operator authorization. An existing plan path cannot be overwritten
with different content.
