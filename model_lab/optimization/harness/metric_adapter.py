"""Harness candidate evaluation adapter and evidence persistence.

Evaluates harness candidates against a set of cases using candidate isolation,
constructs real Attempt records graded by model_lab.grading.grade_attempt, and
maps failure reasons into coarse categories without leaking reference text.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from model_lab.domain.isolation import candidate_input
from model_lab.grading import grade_attempt
from model_lab.optimization.harness.candidate import HarnessCandidate
from model_lab.optimization.harness.prompt_registry import PromptRegistry
from model_lab.optimization.harness.simulated import PromptSensitiveProvider
from model_lab.providers.base import Provider, ProviderRequest
from model_lab.schemas import Attempt, AttemptStatus, Case, Grade, ModelConfig, freeze_json, stable_hash, utc_now
from model_lab.storage.evidence import EvidenceStore

FAILURE_CATEGORIES = ("json_mismatch", "invalid_json", "text_mismatch", "abstained", "provider_error", "other")


def classify_failure(grade: Grade, attempt: Attempt) -> str | None:
    """Extract a coarse failure category without leaking reference text."""
    if grade.passed is True:
        return None
    if grade.passed is None:
        return "abstained"
    if attempt.status != AttemptStatus.SUCCESS:
        return "provider_error"

    reason = (grade.failure_reason or "").lower()
    if "not valid json" in reason or "invalid json" in reason or "parse_error" in reason:
        return "invalid_json"
    if "json value differs" in reason or "json" in reason:
        return "json_mismatch"
    if "text does not" in reason or "match reference" in reason or "text" in reason:
        return "text_mismatch"
    if "provider" in reason or "status" in reason or "timeout" in reason:
        return "provider_error"
    return "other"


@dataclass(frozen=True)
class HarnessEvaluation:
    """Frozen summary of candidate evaluation across a dataset split."""

    candidate_id: str
    split: str
    case_ids: tuple[str, ...]
    per_case: dict[str, dict[str, Any]]
    pass_rate: float | None
    decided: int
    abstained: int
    evidence_class: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "case_ids", tuple(self.case_ids))
        object.__setattr__(self, "per_case", freeze_json(self.per_case))

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "split": self.split,
            "case_ids": list(self.case_ids),
            "per_case": dict(self.per_case),
            "pass_rate": self.pass_rate,
            "decided": self.decided,
            "abstained": self.abstained,
            "evidence_class": self.evidence_class,
        }


def evaluate(
    candidate: HarnessCandidate,
    registry: PromptRegistry,
    cases: Iterable[Case],
    provider: Provider,
    *,
    split_label: str,
) -> HarnessEvaluation:
    """Evaluate a candidate over cases using the provided model provider."""
    case_list = list(cases)
    harness_texts = candidate.texts(registry)

    is_simulated = (
        isinstance(provider, PromptSensitiveProvider)
        or getattr(provider, "evidence_class", None) == "SIMULATED"
        or getattr(provider, "name", "").lower() in {"prompt_sensitive", "simulated", "fake"}
    )
    evidence_class = "SIMULATED" if is_simulated else "MEASURED"

    per_case: dict[str, dict[str, Any]] = {}
    provider_name = getattr(provider, "name", "simulated")
    provider_model = getattr(provider, "model", "simulated-v1")

    for case in case_list:
        c_input = candidate_input(case)
        req = ProviderRequest(
            candidate=c_input,
            model=provider_model,
            parameters={"harness": harness_texts},
        )
        resp = provider.generate(req)

        status = AttemptStatus.SUCCESS if resp.text is not None else AttemptStatus.PROVIDER_FAILURE
        attempt_id = f"att-{stable_hash({'cand': candidate.candidate_id, 'case': case.case_id, 'split': split_label})[:16]}"
        run_id = f"run-harness-{candidate.candidate_id[:16]}"
        req_id = f"req-{stable_hash({'case': case.case_id, 'cand': candidate.candidate_id})[:16]}"

        attempt = Attempt(
            attempt_id=attempt_id,
            run_id=run_id,
            logical_request_id=req_id,
            case_id=case.case_id,
            model_config=ModelConfig(provider=provider_name, model=provider_model),
            prompt_hash=case.prompt_hash,
            response_text=resp.text,
            status=status,
            started_at=utc_now(),
            completed_at=utc_now(),
            finish_reason=resp.finish_reason or "stop",
            input_tokens=resp.input_tokens,
            output_tokens=resp.output_tokens,
            cost_minor=resp.cost_minor,
            currency=resp.currency,
        )

        grade = grade_attempt(case, attempt)
        cat = classify_failure(grade, attempt)

        per_case[case.case_id] = {
            "passed": grade.passed,
            "score": grade.score,
            "failure_category": cat,
        }

    decided = sum(1 for res in per_case.values() if res["passed"] is not None)
    passed_count = sum(1 for res in per_case.values() if res["passed"] is True)
    abstained = sum(1 for res in per_case.values() if res["passed"] is None)
    pass_rate = (passed_count / decided) if decided > 0 else None

    return HarnessEvaluation(
        candidate_id=candidate.candidate_id,
        split=split_label,
        case_ids=tuple(case.case_id for case in case_list),
        per_case=per_case,
        pass_rate=pass_rate,
        decided=decided,
        abstained=abstained,
        evidence_class=evidence_class,
    )


def persist(evidence: EvidenceStore, evaluation: HarnessEvaluation) -> None:
    """Persist a harness evaluation record into append-only evidence store."""
    record_id = f"{evaluation.candidate_id}:{evaluation.split}"
    record = {
        "record_id": record_id,
        "prompt_id": evaluation.candidate_id,
        "split": evaluation.split,
        "case_ids": list(evaluation.case_ids),
        "per_case": dict(evaluation.per_case),
        "pass_rate": evaluation.pass_rate,
        "decided": evaluation.decided,
        "abstained": evaluation.abstained,
        "evidence_class": evaluation.evidence_class,
    }
    evidence.append("harness_evaluations", record_id, record)
