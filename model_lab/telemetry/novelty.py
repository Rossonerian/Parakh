"""Novelty scoring for incoming telemetry runs against historical evidence.

Computes a deterministic novelty score in [0, 1] across domain rarity,
feature distances, failure signatures, tool combinations, shadow disagreements,
user corrections, cost/latency outliers, recovery patterns, and context/tier edges.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
import math
from typing import Any, Mapping, Sequence

from model_lab.optimization.router.features import extract
from model_lab.storage.evidence import EvidenceStore
from model_lab.telemetry.schema import RunRecord


@dataclass(frozen=True)
class Novelty:
    score: float
    components: dict[str, float]
    reasons: list[str]


@dataclass
class NoveltyContext:
    domains: list[str] = field(default_factory=list)
    feature_vectors: list[tuple[float, ...]] = field(default_factory=list)
    failure_signatures: set[tuple[tuple[str, ...], bool | None]] = field(default_factory=set)
    tool_combinations: set[tuple[str, ...]] = field(default_factory=set)
    costs_by_action: dict[str, list[float]] = field(default_factory=lambda: defaultdict(list))
    latencies_by_action: dict[str, list[float]] = field(default_factory=lambda: defaultdict(list))
    model_registry: dict[str, int] = field(default_factory=dict)

    @classmethod
    def from_store(cls, evidence: EvidenceStore) -> NoveltyContext:
        """Construct historical context from previously stored router observations, trajectories, and candidates."""
        ctx = cls()

        # Load models from imports
        try:
            imports = evidence.list("telemetry_imports")
            for imp in imports:
                for m in imp.get("model_registry", []):
                    action = f"{m.get('provider')}/{m.get('model')}"
                    max_ctx = m.get("max_context_tokens")
                    if isinstance(max_ctx, int):
                        ctx.model_registry[action] = max_ctx
        except Exception:
            pass

        # Load router observations
        run_actions: dict[str, str] = {}
        try:
            obs_list = evidence.list("router_observations")
            for obs in obs_list:
                domain = obs.get("task_domain")
                if domain:
                    ctx.domains.append(domain)
                feats = obs.get("features")
                if isinstance(feats, (list, tuple)):
                    ctx.feature_vectors.append(tuple(float(x) for x in feats))
                if not obs.get("shadow"):
                    run_id = obs.get("run_id")
                    action = obs.get("chosen_action")
                    if run_id and action:
                        run_actions[run_id] = action
        except Exception:
            pass

        # Load trajectories for cost/latency outliers
        try:
            trajs = evidence.list("trajectories")
            for traj in trajs:
                run_id = traj.get("run_id")
                action = run_actions.get(run_id)
                outcome = traj.get("final_outcome", {})
                if action and isinstance(outcome, Mapping):
                    cost = outcome.get("final_cost")
                    if isinstance(cost, (int, float)):
                        ctx.costs_by_action[action].append(float(cost))
                    lat = outcome.get("final_latency_ms")
                    if isinstance(lat, (int, float)):
                        ctx.latencies_by_action[action].append(float(lat))
        except Exception:
            pass

        # Load candidates for tool combinations and failure signatures
        try:
            cands = evidence.list("evaluation_candidates")
            for cand in cands:
                case = cand.get("case", {})
                tools = case.get("tool_names")
                if isinstance(tools, (list, tuple)) and tools:
                    ctx.tool_combinations.add(tuple(tools))
                fail_sig = case.get("failure_signature")
                if isinstance(fail_sig, (list, tuple)) and len(fail_sig) == 2:
                    errors = tuple(fail_sig[0]) if isinstance(fail_sig[0], (list, tuple)) else ()
                    ctx.failure_signatures.add((errors, fail_sig[1]))
        except Exception:
            pass

        return ctx

    def register_model_catalog(self, catalog: Sequence[Mapping[str, Any]]) -> None:
        """Register model info entries into the registry."""
        for m in catalog:
            provider = m.get("provider") if isinstance(m, Mapping) else getattr(m, "provider", None)
            model = m.get("model") if isinstance(m, Mapping) else getattr(m, "model", None)
            max_ctx = m.get("max_context_tokens") if isinstance(m, Mapping) else getattr(m, "max_context_tokens", None)
            if provider and model and isinstance(max_ctx, int):
                self.model_registry[f"{provider}/{model}"] = max_ctx


def _run_failure_signature(run: RunRecord) -> tuple[tuple[str, ...], bool | None]:
    errors: set[str] = set()
    for att in run.attempts:
        if isinstance(att, Mapping) and att.get("error_type") is not None:
            errors.add(str(att["error_type"]))
    for te in run.tool_events:
        if isinstance(te, Mapping) and te.get("error_class") is not None:
            errors.add(str(te["error_class"]))
    for ve in run.validation_events:
        if isinstance(ve, Mapping) and ve.get("error_class") is not None:
            errors.add(str(ve["error_class"]))
    completed = run.outcome.get("completed") if isinstance(run.outcome, Mapping) else None
    return tuple(sorted(errors)), bool(completed) if completed is not None else None


def score(run: RunRecord, history: NoveltyContext) -> Novelty:
    """Score the novelty of a validated run in [0, 1] relative to historical context."""
    components: dict[str, float] = {}

    # 1. domain_rarity: 1 - share of domain in history
    if not history.domains:
        components["domain_rarity"] = 1.0
    else:
        domain_count = sum(1 for d in history.domains if d == run.task_domain)
        share = domain_count / len(history.domains)
        components["domain_rarity"] = max(0.0, min(1.0, 1.0 - share))

    # 2. feature_distance: min L2 distance of feature vector to history vectors, scaled by sqrt(dim); 1.0 when no history
    feat_vec = extract(run.routing_context)
    dim = len(feat_vec)
    if not history.feature_vectors or dim == 0:
        components["feature_distance"] = 1.0
    else:
        min_dist_sq = min(
            sum((a - b) ** 2 for a, b in zip(feat_vec, h_vec, strict=False))
            for h_vec in history.feature_vectors
        )
        l2 = math.sqrt(min_dist_sq)
        components["feature_distance"] = max(0.0, min(1.0, l2 / math.sqrt(dim)))

    # 3. new_failure_signature
    sig_errors, completed = _run_failure_signature(run)
    if not sig_errors and (completed is True):
        components["new_failure_signature"] = 0.0
    else:
        is_new = (sig_errors, completed) not in history.failure_signatures
        components["new_failure_signature"] = 1.0 if is_new else 0.0

    # 4. new_tool_combination
    tool_names = tuple(sorted({e["tool_name"] for e in run.tool_events if isinstance(e, Mapping) and "tool_name" in e}))
    if not tool_names:
        components["new_tool_combination"] = 0.0
    else:
        components["new_tool_combination"] = 1.0 if tool_names not in history.tool_combinations else 0.0

    # 5. shadow_disagreement
    live_act = run.live_decision.action
    has_disagreement = any(d.action != live_act for d in run.shadow_decisions)
    components["shadow_disagreement"] = 1.0 if has_disagreement else 0.0

    # 6. correction_magnitude
    corr_dist = run.outcome.get("correction_distance") if isinstance(run.outcome, Mapping) else None
    components["correction_magnitude"] = max(0.0, min(1.0, float(corr_dist))) if corr_dist is not None else 0.0

    # 7. unusual_cost and unusual_latency: |z| >= 3 vs history for same live action; 0 when < 20 samples
    action_costs = history.costs_by_action.get(live_act, [])
    if len(action_costs) < 20:
        components["unusual_cost"] = 0.0
    else:
        cost = run.outcome.get("final_cost") if isinstance(run.outcome, Mapping) else None
        if cost is None:
            components["unusual_cost"] = 0.0
        else:
            mean_c = sum(action_costs) / len(action_costs)
            var_c = sum((c - mean_c) ** 2 for c in action_costs) / len(action_costs)
            std_c = math.sqrt(var_c)
            components["unusual_cost"] = 1.0 if (std_c > 0 and abs(cost - mean_c) / std_c >= 3.0) else 0.0

    action_latencies = history.latencies_by_action.get(live_act, [])
    if len(action_latencies) < 20:
        components["unusual_latency"] = 0.0
    else:
        lat = run.outcome.get("final_latency_ms") if isinstance(run.outcome, Mapping) else None
        if lat is None:
            components["unusual_latency"] = 0.0
        else:
            mean_l = sum(action_latencies) / len(action_latencies)
            var_l = sum((l - mean_l) ** 2 for l in action_latencies) / len(action_latencies)
            std_l = math.sqrt(var_l)
            components["unusual_latency"] = 1.0 if (std_l > 0 and abs(lat - mean_l) / std_l >= 3.0) else 0.0

    # 8. repeated_recovery: retry_count >= 2
    retry_count = run.outcome.get("retry_count", 0) if isinstance(run.outcome, Mapping) else 0
    components["repeated_recovery"] = 1.0 if (isinstance(retry_count, int) and retry_count >= 2) else 0.0

    # 9. context_limit_edge: context_utilization_ratio >= 0.9
    cur = run.routing_context.get("context_utilization_ratio", 0.0)
    components["context_limit_edge"] = 1.0 if (isinstance(cur, (int, float)) and cur >= 0.9) else 0.0

    # 10. tier_edge: tier in ("ananta", "yanta") and estimated_input_tokens >= 0.8 * smallest max_context among eligible models
    tier = run.tier
    tokens = run.routing_context.get("estimated_input_tokens", 0)
    if tier in ("ananta", "yanta"):
        eligible = run.live_decision.eligible_models
        max_contexts = [history.model_registry.get(m, 32000) for m in eligible]
        smallest_max = min(max_contexts) if max_contexts else 32000
        components["tier_edge"] = 1.0 if tokens >= 0.8 * smallest_max else 0.0
    else:
        components["tier_edge"] = 0.0

    # Composite score: max(components) * 0.6 + mean(components) * 0.4
    comp_values = list(components.values())
    max_val = max(comp_values)
    mean_val = sum(comp_values) / len(comp_values)
    final_score = round(max(0.0, min(1.0, max_val * 0.6 + mean_val * 0.4)), 6)

    reasons = sorted(k for k, v in components.items() if v > 0)
    return Novelty(score=final_score, components=components, reasons=reasons)
