"""Per-action evidence on the frozen core benchmark, for routing-policy regression.

A routing policy is judged on the core suite by *which action it picks per
case*; the outcome of that (case, action) pair comes from a stored, graded
evaluation run of that action on the core suite. Offline, those runs come from
``SimulatedModelProvider`` (the synthetic Karmi model profiles; environment mode
``offline_synthetic`` so every view labels them SIMULATED). Real evidence comes
from authorised live pilot runs imported the usual way — nothing here dispatches
paid calls.

Routing contexts for core cases use only candidate-visible data (messages,
limits, domain label); never the evaluation block.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from model_lab.application.execution import ExecutionEngine
from model_lab.pipeline import _candidate_output, grade_run
from model_lab.providers.base import ProviderCapabilities, ProviderRequest, ProviderResponse
from model_lab.schemas import Budget, Case, ModelConfig, Run, Suite, utc_now
from model_lab.storage import SQLiteStore
from model_lab.telemetry.synthetic import expected_outcome


def case_context(case: Case, tier: str) -> dict[str, Any]:
    """RoutingContext for a core case from candidate-visible data only."""
    text = " ".join(str(m.get("content", "")) for m in case.candidate_payload()["messages"])
    tokens = max(1, len(text) // 4)
    return {
        "tier": tier, "task_domain": case.domain, "estimated_input_tokens": tokens,
        "context_utilization_ratio": round(min(1.0, tokens / 128_000), 6), "tool_count": 0,
        "requires_structured_output": "json" in text.lower(), "requires_tools": False,
        "requires_memory": case.domain == "conversation_memory", "requires_external_data": False,
        "conversation_depth": max(0, len(case.messages) - 1), "retry_number": 0, "previous_tool_failure": False,
        "latency_slo_ms": None,
    }


@dataclass
class SimulatedModelProvider:
    """Deterministic stand-in for a synthetic model profile on core cases (SIMULATED evidence)."""

    action: str
    outputs: dict[str, str]
    latency_ms: dict[str, float]
    name: str = "sim"
    capabilities: ProviderCapabilities = field(init=False)

    def __post_init__(self) -> None:
        self.capabilities = ProviderCapabilities(self.name, self.action.split("/")[1], pricing_known=False)

    def generate(self, request: ProviderRequest) -> ProviderResponse:
        case_id = request.candidate.case_id
        return ProviderResponse(text=self.outputs[case_id], completion_latency_ms=self.latency_ms[case_id],
                                metadata={"synthetic": True, "simulated_action": self.action})


def run_simulated_evidence(store: SQLiteStore, suite: Suite, action: str, *, seed: int = 7) -> str:
    """Execute + grade one simulated action over the whole core suite; returns the run_id (idempotent)."""
    run_id = f"bench-{action.replace('/', '-')}-{(suite.source_hash or 'nohash')[:12]}-s{seed}"
    try:
        store.get_run(run_id)
        return run_id
    except Exception:
        pass
    outputs, latency = {}, {}
    for case in suite.cases:
        truth = expected_outcome(case_context(case, "part"), action)
        outputs[case.case_id] = _candidate_output(case, incorrect=truth["success_probability"] < 0.5)
        latency[case.case_id] = round(truth["latency_ms"], 3)
    provider, model = action.split("/")
    run = Run(run_id=run_id, suite_version=suite.suite_version, case_ids=suite.case_ids,
              model_config=ModelConfig(provider=provider, model=model, parameters={"temperature": 0, "synthetic": True}),
              seed=seed, budget=Budget(max_cases=len(suite.cases), max_requests=len(suite.cases)), started_at=utc_now(),
              environment={"mode": "offline_synthetic", "purpose": "core_regression_evidence", "suite_hash": suite.source_hash or "unknown"},
              prompt_hashes={case.case_id: case.prompt_hash for case in suite.cases})
    result = ExecutionEngine(store, SimulatedModelProvider(action, outputs, latency)).execute(suite, run)
    grade_run(suite, store, list(result.attempts))
    return run_id


def evidence_table(store: SQLiteStore, run_ids_by_action: Mapping[str, str]) -> dict[tuple[str, str], dict[str, Any]]:
    """(case_id, action) -> {passed, score, latency_ms, reviews, run_id, evidence_class} from stored runs."""
    table: dict[tuple[str, str], dict[str, Any]] = {}
    for action, run_id in sorted(run_ids_by_action.items()):
        run = store.get_run(run_id)
        grades = {g.attempt_id: g for g in store.list_grades(run_id)}
        reviews: dict[str, list[float]] = {}
        for review in store.list_reviews(run_id):
            if review.score is not None and review.decision in ("accept", "reject"):
                reviews.setdefault(review.case_id, []).append(review.score)
        latest = {}
        for attempt in store.list_attempts(run_id):
            latest[attempt.case_id] = attempt
        evidence_class = "SIMULATED" if run.environment.get("mode") == "offline_synthetic" else "MEASURED"
        for case_id, attempt in latest.items():
            grade = grades.get(attempt.attempt_id)
            table[(case_id, action)] = {"passed": grade.passed if grade else None, "score": grade.score if grade else None,
                                        "latency_ms": attempt.completion_latency_ms, "rubric_scores": reviews.get(case_id, []),
                                        "run_id": run_id, "evidence_class": evidence_class,
                                        "grader": f"{grade.grader_id}@{grade.grader_version}" if grade else None}
    return table
