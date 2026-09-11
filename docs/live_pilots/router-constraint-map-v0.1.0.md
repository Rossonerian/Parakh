# Router-constraint map for live pilot v0.1.0

This is a draft evidence map, not a production routing change.

| Router constraint | Basis currently available | Pilot treatment | Status |
| --- | --- | --- | --- |
| Recommendations remain drafts and never edit production configuration | `Model_Testing_Spec.md`, `Rules.md` | `production_router_change=false`; `recommendation_mode=draft_only` | Applied |
| Subscription IDs are separate from model IDs | `Rules.md`, `Agent_Team.md` | Preserve `ananta`, `yanta`, `trika`, `part` as entitlement identifiers only | Applied |
| Routing evidence is workload/category-specific, not a universal intelligence ranking | `Architecture.md`, `Model_Testing_Spec.md` | Compare by domain, workflow, complexity, split, cost, latency, and coverage | Applied in lab; live evidence pending |
| Candidate eligibility must include context, tools, provider availability, and plan constraints | `Rules.md`, `Architecture.md` | Frozen in the plan as fields to populate from operator model metadata and imported product sources | Pending operator/model data |
| Calibration and holdout remain untouched until candidates/policy are frozen | `benchmarks/README.md`, `Model_Testing_Spec.md` | Pilot selects only the 36 `train` cases | Applied |
| Tier/plan-specific model eligibility and limits | Actual `Tier_Entitlements` source | Not inferred; pilot cannot finalize this mapping | Blocked: source missing |
| Product task priorities, UX constraints, and acceptance requirements | Actual PRD and Design sources | Not inferred; pilot cannot claim complete product mapping | Blocked: sources missing |

The actual Daily AI Agent PRD, Design, and Tier Entitlements documents must be supplied and imported under `docs/product_sources/` before a router recommendation can be reviewed against complete product constraints.

