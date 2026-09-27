"""Deterministic synthetic Karmi: known environment, known logging policy.

Produces ``TelemetryBatchV1`` documents whose ground truth is available in
closed form (``expected_outcome``), so bandit/OPE code can be tested against a
known optimal action. Every batch is labelled ``producer.repo =
"parakh-synthetic-karmi"`` and every run ``SIMULATED`` in its status metadata:
this is test/demo evidence, never production telemetry.
"""

from __future__ import annotations

import hashlib
import math
import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Mapping, Sequence

from model_lab.schema_registry import FEATURE_SCHEMA_VERSION, TELEMETRY_SCHEMA, TELEMETRY_SCHEMA_VERSION
from model_lab.schemas import DOMAINS

PRODUCER_REPO = "parakh-synthetic-karmi"
PRODUCER_VERSION = "0.1.0"
TIERS = ("ananta", "yanta", "trika", "part")
BASE_TIME = datetime(2026, 9, 1, tzinfo=timezone.utc)
HARD_DOMAINS = frozenset({"tabular_analysis", "source_reasoning", "document_extraction", "automation", "privacy"})


@dataclass(frozen=True)
class SimModel:
    provider: str
    model: str
    max_context_tokens: int
    supports_tools: bool
    supports_structured_output: bool
    input_cost_per_token: float  # USD per token
    output_cost_per_token: float
    base_latency_ms: float
    skill: float  # higher = better on hard tasks

    @property
    def action(self) -> str:
        return f"{self.provider}/{self.model}"

    def registry_entry(self) -> dict[str, Any]:
        return {"provider": self.provider, "model": self.model, "model_version": "sim-1", "max_context_tokens": self.max_context_tokens,
                "supports_tools": self.supports_tools, "supports_structured_output": self.supports_structured_output,
                "estimated_input_cost_per_token": self.input_cost_per_token, "estimated_output_cost_per_token": self.output_cost_per_token}


MODELS = (
    SimModel("sim", "cheap", 32_000, False, True, 0.10e-6, 0.40e-6, 700.0, 0.35),
    SimModel("sim", "balanced", 128_000, True, True, 0.80e-6, 3.20e-6, 1500.0, 0.65),
    SimModel("sim", "flagship", 200_000, True, True, 5.00e-6, 20.0e-6, 3200.0, 0.92),
)
MODEL_BY_ACTION = {m.action: m for m in MODELS}
TIER_ENTITLEMENTS = {"ananta": ("sim/cheap", "sim/balanced"), "yanta": ("sim/cheap", "sim/balanced"),
                     "trika": tuple(m.action for m in MODELS), "part": tuple(m.action for m in MODELS)}


def eligible_actions(context: Mapping[str, Any]) -> tuple[str, ...]:
    """Hard eligibility (Karmi's job in production): tier, context size, tools, structured output."""
    out = []
    for action in TIER_ENTITLEMENTS[context["tier"]]:
        model = MODEL_BY_ACTION[action]
        if context["estimated_input_tokens"] > model.max_context_tokens:
            continue
        if context["requires_tools"] and not model.supports_tools:
            continue
        if context["requires_structured_output"] and not model.supports_structured_output:
            continue
        out.append(action)
    return tuple(out)


def difficulty(context: Mapping[str, Any]) -> float:
    """Ground-truth task difficulty in [0, 1]."""
    d = 0.15
    d += 0.35 if context["task_domain"] in HARD_DOMAINS else 0.0
    d += 0.15 if context["requires_structured_output"] else 0.0
    d += 0.15 if context["requires_tools"] else 0.0
    d += 0.2 * min(1.0, context["estimated_input_tokens"] / 60_000)
    return min(1.0, d)


def expected_outcome(context: Mapping[str, Any], action: str) -> dict[str, float]:
    """Closed-form truth: success probability, expected cost (USD) and latency (ms)."""
    model = MODEL_BY_ACTION[action]
    gap = difficulty(context) - model.skill
    success = 1.0 / (1.0 + math.exp(8.0 * gap)) * 0.97 + 0.02
    output_tokens = 300 + (400 if context["requires_structured_output"] else 0)
    cost = context["estimated_input_tokens"] * model.input_cost_per_token + output_tokens * model.output_cost_per_token
    latency = model.base_latency_ms * (1.0 + context["estimated_input_tokens"] / 50_000)
    return {"success_probability": success, "cost": cost, "latency_ms": latency, "output_tokens": float(output_tokens)}


def static_policy(context: Mapping[str, Any], eligible: Sequence[str]) -> str:
    """Stand-in for Karmi's current static router: balanced unless tools+hard, then strongest eligible."""
    if context["requires_tools"] and context["task_domain"] in HARD_DOMAINS and "sim/flagship" in eligible:
        return "sim/flagship"
    return "sim/balanced" if "sim/balanced" in eligible else eligible[0]


def balanced_only_policy(context: Mapping[str, Any], eligible: Sequence[str]) -> str:
    """A deliberately naive pre-optimization router (balanced for everything) with real, learnable headroom."""
    return "sim/balanced" if "sim/balanced" in eligible else eligible[0]


def epsilon_greedy(base: Callable[[Mapping[str, Any], Sequence[str]], str], epsilon: float) -> Callable[[Mapping[str, Any], Sequence[str], random.Random], tuple[str, float, bool]]:
    """Logging policy with exact propensities: base choice w.p. 1-ε+ε/k, others ε/k."""
    def choose(context: Mapping[str, Any], eligible: Sequence[str], rng: random.Random) -> tuple[str, float, bool]:
        greedy = base(context, eligible)
        k = len(eligible)
        explore = rng.random() < epsilon
        action = eligible[rng.randrange(k)] if explore else greedy
        probability = (1 - epsilon) + epsilon / k if action == greedy else epsilon / k
        return action, probability, explore and action != greedy
    return choose


def _iso(moment: datetime) -> str:
    return moment.isoformat().replace("+00:00", "Z")


def _context(rng: random.Random) -> dict[str, Any]:
    domain = rng.choice(sorted(DOMAINS))
    tier = rng.choice(TIERS)
    tools = rng.random() < 0.35
    tokens = int(rng.choice((800, 2_000, 6_000, 20_000, 45_000, 90_000)) * rng.uniform(0.7, 1.3))
    return {
        "tier": tier, "task_domain": domain, "estimated_input_tokens": tokens,
        "context_utilization_ratio": round(min(1.0, tokens / 128_000), 4), "tool_count": rng.randint(1, 3) if tools else 0,
        "requires_structured_output": rng.random() < 0.4, "requires_tools": tools, "requires_memory": rng.random() < 0.3,
        "requires_external_data": rng.random() < 0.2, "conversation_depth": rng.randint(0, 12), "retry_number": 0,
        "previous_tool_failure": False, "latency_slo_ms": rng.choice((None, 4_000, 10_000)),
    }


def generate_batch(*, seed: int, batch_index: int = 0, runs: int = 200, epsilon: float = 0.3,
                   logging_policy_version: str = "static-v1", shadow_policy: Callable[[Mapping[str, Any], Sequence[str]], tuple[str, float]] | None = None,
                   shadow_policy_version: str | None = None, faults: Mapping[str, int] | None = None,
                   base_policy: Callable[[Mapping[str, Any], Sequence[str]], str] = static_policy) -> dict[str, Any]:
    """One deterministic batch. ``faults`` injects bad records: missing_propensity, secret, duplicate_run, bad_context, ineligible_choice.

    ``base_policy`` is the logging router's greedy choice; ``epsilon`` exploration on top of it gives exact propensities.
    """
    rng = random.Random(f"{seed}:{batch_index}")
    choose = epsilon_greedy(base_policy, epsilon)
    start = BASE_TIME + timedelta(days=batch_index)
    out_runs: list[dict[str, Any]] = []
    for i in range(runs):
        context = _context(rng)
        eligible = eligible_actions(context)
        action, probability, explored = choose(context, eligible, rng)
        truth = expected_outcome(context, action)
        success = rng.random() < truth["success_probability"]
        retries = 0 if success or rng.random() < 0.5 else rng.randint(1, 2)
        latency = truth["latency_ms"] * rng.uniform(0.8, 1.25) * (1 + retries)
        cost = truth["cost"] * (1 + retries)
        at = start + timedelta(minutes=5 * i)
        run_id = f"srun-{seed}-{batch_index}-{i:05d}"
        session = hashlib.sha256(f"session:{seed}:{rng.randint(0, runs // 3)}".encode()).hexdigest()[:24]
        provider, model = action.split("/")
        decisions = [{
            "decision_id": f"dec-{run_id}", "selected_provider": provider, "selected_model": model,
            "policy_version": logging_policy_version, "selection_probability": round(probability, 6), "exploration": explored,
            "shadow": False, "eligible_models": list(eligible), "feature_schema_version": FEATURE_SCHEMA_VERSION, "created_at": _iso(at),
        }]
        if shadow_policy is not None:
            shadow_action, shadow_probability = shadow_policy(context, eligible)
            sp, sm = shadow_action.split("/")
            decisions.append({**decisions[0], "decision_id": f"sdec-{run_id}", "selected_provider": sp, "selected_model": sm,
                              "policy_version": shadow_policy_version or "shadow", "selection_probability": round(shadow_probability, 6),
                              "exploration": False, "shadow": True})
        structured_ok = (success or rng.random() < 0.3) if context["requires_structured_output"] else None
        tool_events = [{"event_id": f"tool-{run_id}-{t}", "tool_name": f"tool_{t}", "attempt_number": 1,
                        "schema_valid": success or rng.random() < 0.6, "execution_success": success or rng.random() < 0.4,
                        "latency_ms": round(rng.uniform(50, 400), 1), "error_class": None if success else "tool_error"}
                       for t in range(context["tool_count"])]
        accepted = success and rng.random() < 0.6
        corrected = (not success) and rng.random() < 0.35
        feedback = []
        if corrected:
            kind = rng.choice(("factual", "intent_change", "style", "schedule", "repair", None))
            feedback.append({"feedback_id": f"fb-{run_id}", "feedback_type": "intent_change" if kind == "intent_change" else "correction",
                             "original_value_hash": hashlib.sha256(run_id.encode()).hexdigest(),
                             "sanitized_original_value": f"[synthetic draft for {context['task_domain']} #{i}]",
                             "sanitized_corrected_value": f"[synthetic corrected draft for {context['task_domain']} #{i}]",
                             "correction_kind_hint": kind, "minutes_after_output": rng.randint(0, 90),
                             "same_request": kind != "intent_change", "created_at": _iso(at + timedelta(minutes=2))})
        out_runs.append({
            "run_id": run_id, "request_id": f"req-{run_id}", "session_id_hash": session, "started_at": _iso(at),
            "completed_at": _iso(at + timedelta(milliseconds=latency)), "task_domain": context["task_domain"], "tier": context["tier"],
            "harness_version": "harness-v1", "prompt_version": "prompt-v1", "policy_version": logging_policy_version,
            "feature_schema_version": FEATURE_SCHEMA_VERSION, "status": "completed" if success else "failed",
            "routing_context": context, "decisions": decisions,
            "attempts": [{"attempt_id": f"att-{run_id}-{r}", "decision_id": f"dec-{run_id}", "provider": provider, "model": model,
                          "latency_ms": round(latency / (1 + retries), 1), "input_tokens": context["estimated_input_tokens"],
                          "output_tokens": int(truth["output_tokens"]), "estimated_cost": round(truth["cost"], 8), "currency": "USD",
                          "success": success if r == retries else False, "error_type": None if (success and r == retries) else "task_failure",
                          "retry_number": r} for r in range(retries + 1)],
            "tool_events": tool_events,
            "validation_events": [{"event_id": f"val-{run_id}", "validator": "structured_output", "passed": structured_ok, "error_class": None if structured_ok else "schema_invalid"}] if structured_ok is not None else [],
            "outcome": {"completed": success, "first_shot_success": success and retries == 0, "structured_output_valid": structured_ok,
                        "tool_success": all(e["execution_success"] for e in tool_events) if tool_events else None, "retry_count": retries,
                        "user_retry_signal": (not success) and rng.random() < 0.3, "user_abandon_signal": (not success) and rng.random() < 0.2,
                        "user_accept_signal": accepted, "user_correction_signal": corrected, "correction_distance": round(rng.uniform(0.1, 0.9), 3) if corrected else None,
                        "final_latency_ms": round(latency, 1), "final_cost": round(cost, 8), "currency": "USD", "finalized_at": _iso(at + timedelta(hours=1)),
                        "critical_failure": (not success) and context["task_domain"] == "privacy" and rng.random() < 0.3},
            "feedback": feedback,
        })
    _inject_faults(out_runs, faults or {}, rng)
    return {
        "schema": TELEMETRY_SCHEMA, "schema_version": TELEMETRY_SCHEMA_VERSION, "batch_id": f"synthetic-{seed}-{batch_index}",
        "generated_at": _iso(start + timedelta(hours=23)), "producer": {"repo": PRODUCER_REPO, "version": PRODUCER_VERSION},
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "window": {"start": _iso(start), "end": _iso(start + timedelta(days=1)), "cursor": f"{seed}:{batch_index}"},
        "model_registry": [m.registry_entry() for m in MODELS], "runs": out_runs,
    }


def _inject_faults(runs: list[dict[str, Any]], faults: Mapping[str, int], rng: random.Random) -> None:
    position = 0

    def take() -> dict[str, Any]:
        nonlocal position
        run = runs[position % len(runs)]
        position += 1
        return run

    for _ in range(faults.get("missing_propensity", 0)):
        del take()["decisions"][0]["selection_probability"]
    for _ in range(faults.get("secret", 0)):
        run = take()
        run["feedback"] = [{"feedback_id": f"fb-secret-{run['run_id']}", "feedback_type": "correction", "created_at": run["started_at"],
                            "sanitized_corrected_value": "use key sk-live-" + "a1b2c3d4e5f6g7h8i9j0" + " for this"}]
    for _ in range(faults.get("bad_context", 0)):
        take()["routing_context"]["context_utilization_ratio"] = 7.5
    for _ in range(faults.get("ineligible_choice", 0)):
        run = take()
        run["decisions"][0]["eligible_models"] = [m for m in run["decisions"][0]["eligible_models"]
                                                  if m != f"{run['decisions'][0]['selected_provider']}/{run['decisions'][0]['selected_model']}"] or ["sim/cheap"]
    for _ in range(faults.get("duplicate_run", 0)):
        runs.append(dict(take()))
