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

Validation and immutable-plan conversion are available from Python until CLI
wiring is added:

```python
from model_lab.operator_input import build_immutable_plan, load_operator_input, write_immutable_plan

value = load_operator_input("operator-input.yaml")
plan = build_immutable_plan(value, suite_path="benchmarks/seed_cases.jsonl")
write_immutable_plan(plan, "pilot-plan.json")
```

The plan includes exact case IDs, maximum calls, per-candidate bounds, total
bound, and operator authorization. An existing plan path cannot be overwritten
with different content.
