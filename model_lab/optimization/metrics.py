"""Compounding flywheel metrics (plan P15), computed only from stored evidence.

Each metric states its denominator; a metric with no data is ``None`` with a
note, never 0. First-shot recovery metrics deliberately report unrecovered and
average recovery attempts alongside success so hidden retry loops cannot look
like improvement.
"""

from __future__ import annotations

from statistics import mean
from typing import Any

from model_lab.storage.evidence import CANDIDATE_ROLES, EvidenceStore

CRITICAL_GATES = ("oracle_isolation", "harness_oracle_isolation", "core_regression", "critical_failures", "holdout")


def _ratio(numerator: float, denominator: float) -> float | None:
    return numerator / denominator if denominator else None


def compounding_metrics(evidence: EvidenceStore, *, propensity_floor: float = 0.01) -> dict[str, Any]:
    observations = evidence.list("router_observations")
    live = [o for o in observations if not o["shadow"]]
    shadow = [o for o in observations if o["shadow"]]
    trajectories = evidence.list("trajectories")
    rewards = {r["subject_id"]: r for r in evidence.list("rewards") if r.get("subject_type") == "telemetry_run"}
    candidates = evidence.list("evaluation_candidates")
    candidate_states = evidence.states("evaluation_candidate")
    reports = evidence.list("verification_reports")

    approved = sum(1 for c in candidates if candidate_states.get(c["candidate_id"]) in ("APPROVED", *CANDIDATE_ROLES))
    imported_runs = sum(1 for r in evidence.list("telemetry_records") if r["status"] == "accepted")

    outcomes = [t.get("final_outcome") or {} for t in trajectories]
    first_shot = [o["first_shot_success"] for o in outcomes if o.get("first_shot_success") is not None]
    retried = [o for o in outcomes if (o.get("retry_count") or 0) > 0]
    recovered_clean = [o for o in retried if o.get("completed") is True and not o.get("user_retry_signal") and not o.get("user_abandon_signal")]
    completed_known = [o for o in outcomes if o.get("completed") is not None]

    live_by_run = {o["run_id"]: o["chosen_action"] for o in live}
    disagreements: dict[str, list[bool]] = {}
    for o in shadow:
        if o["run_id"] in live_by_run:
            disagreements.setdefault(o["policy_version"], []).append(o["chosen_action"] != live_by_run[o["run_id"]])

    successes, cost_total, reward_values, reward_cost, reward_seconds = 0, 0.0, [], 0.0, 0.0
    for t in trajectories:
        outcome = t.get("final_outcome") or {}
        if outcome.get("completed") is True:
            successes += 1
        if outcome.get("final_cost") is not None and outcome.get("currency") == "USD":
            cost_total += float(outcome["final_cost"])
        reward = rewards.get(t["run_id"])
        if reward and reward.get("scalar") is not None:
            reward_values.append(reward["scalar"])
            reward_cost += float(outcome.get("final_cost") or 0.0) if outcome.get("currency") == "USD" else 0.0
            reward_seconds += float(outcome.get("final_latency_ms") or 0.0) / 1000.0

    coverage: dict[str, dict[str, int]] = {}
    supported_cells, total_cells = 0, 0
    cells: dict[tuple[str, str], set[str]] = {}
    for o in live:
        coverage.setdefault(o["tier"], {}).setdefault(o["chosen_action"], 0)
        coverage[o["tier"]][o["chosen_action"]] += 1
        key = (o["tier"], o["task_domain"])
        cells.setdefault(key, set())
        for action in o["eligible_actions"]:
            cells[key].add(f"eligible:{action}")
        if o["propensity"] >= propensity_floor:
            cells[key].add(f"logged:{o['chosen_action']}")
    for marks in cells.values():
        eligible = {m.split(":", 1)[1] for m in marks if m.startswith("eligible:")}
        logged = {m.split(":", 1)[1] for m in marks if m.startswith("logged:")}
        total_cells += len(eligible)
        supported_cells += len(eligible & logged)

    latest = reports[-1] if reports else None
    critical_failed = [r for r in reports if any(g["gate"] in CRITICAL_GATES and not g["passed"] for g in r["hard_gates"])]
    return {
        "data_efficiency_ratio": {"value": _ratio(approved, imported_runs), "approved_candidates": approved, "imported_runs": imported_runs,
                                  "note": "approved novel candidates / accepted imported runs; a low value can simply mean stable production"},
        "frontier_migration": (latest or {}).get("soft_metrics", {}).get("frontier_migration"),
        "first_shot_recovery": {
            "first_shot_success_rate": _ratio(sum(first_shot), len(first_shot)),
            "recovered_without_user_visible_failure": _ratio(len(recovered_clean), len(retried)),
            "average_recovery_attempts": mean(o["retry_count"] for o in retried) if retried else None,
            "unrecovered_failure_rate": _ratio(sum(o["completed"] is False for o in completed_known), len(completed_known)),
            "runs": len(outcomes),
        },
        "shadow_disagreement": {version: {"rate": _ratio(sum(v), len(v)), "n": len(v)} for version, v in sorted(disagreements.items())},
        "cost_per_successful_run_usd": _ratio(cost_total, successes),
        "reward_per_dollar": _ratio(sum(reward_values), reward_cost),
        "reward_per_second": _ratio(sum(reward_values), reward_seconds),
        "mean_reward": mean(reward_values) if reward_values else None,
        "critical_regression_rate": {"value": _ratio(len(critical_failed), len(reports)), "reports": len(reports)},
        "model_tier_coverage": coverage,
        "propensity_support_coverage": {"value": _ratio(supported_cells, total_cells), "supported_cells": supported_cells, "eligible_cells": total_cells,
                                        "note": "share of (tier, domain, eligible action) cells with a logged choice at propensity >= floor"},
        "holdout_gap": (latest or {}).get("soft_metrics", {}).get("holdout_gap"),
        "optimizer_overfit_gap": (latest or {}).get("soft_metrics", {}).get("train_validation_gap"),
    }
