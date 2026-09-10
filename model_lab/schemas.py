"""Typed, JSON-serializable contracts for the ModelLab.

The lab intentionally uses standard-library dataclasses so the offline workflow
has no runtime dependency or network requirement. Constructors validate all
external values before records enter the rest of the system.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
import re
from typing import Any, Mapping, Sequence

from .errors import ValidationError

ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
DIFFICULTIES = {1, 2, 3, 4}
SPLITS = {"train", "calibration", "holdout"}
DOMAINS = {
    "communication", "calendar", "task_planning", "expenses", "shopping",
    "travel", "document_extraction", "tabular_analysis", "support",
    "source_reasoning", "privacy", "conversation_memory", "multilingual",
    "automation", "ambiguity",
}
EVALUATION_METHODS = {"exact_json", "exact_text", "rubric", "schema", "imported"}


class AttemptStatus(str, Enum):
    SUCCESS = "success"
    REFUSAL = "refusal"
    PROVIDER_FAILURE = "provider_failure"
    TIMEOUT = "timeout"
    INVALID_PROVIDER_RESPONSE = "invalid_provider_response"
    MALFORMED_OUTPUT = "malformed_output"
    CANCELLED = "cancelled"
    PARTIAL = "partial"
    IMPORTED_INVALID = "imported_invalid"
    GRADING_FAILURE = "grading_failure"
    INFRASTRUCTURE_FAILURE = "infrastructure_failure"


class MetricKind(str, Enum):
    MEASURED = "measured"
    PROVIDER_REPORTED = "provider_reported"
    IMPORTED = "imported"
    ESTIMATED = "estimated"
    UNKNOWN = "unknown"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def require_id(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not ID_RE.fullmatch(value):
        raise ValidationError(f"{field_name} must be a stable identifier")
    return value


def require_text(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{field_name} must be non-empty text")
    return value


def stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def stable_hash(value: Any) -> str:
    return hashlib.sha256(stable_json(value).encode("utf-8")).hexdigest()


def _plain(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return {k: _plain(v) for k, v in asdict(value).items()}
    if isinstance(value, Mapping):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    return value


@dataclass(frozen=True)
class RubricCriterion:
    criterion: str
    weight: float = 1.0

    def __post_init__(self) -> None:
        require_text(self.criterion, "rubric criterion")
        if not isinstance(self.weight, (int, float)) or self.weight <= 0:
            raise ValidationError("rubric weight must be positive")


@dataclass(frozen=True)
class Evaluation:
    method: str
    reference_answer: Any
    rubric: tuple[RubricCriterion, ...]
    critical_failures: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.method not in EVALUATION_METHODS:
            raise ValidationError(f"unsupported evaluation method: {self.method}")
        if not self.rubric:
            raise ValidationError("evaluation rubric cannot be empty")
        if any(not isinstance(x, RubricCriterion) for x in self.rubric):
            raise ValidationError("rubric must contain criteria")
        if any(not isinstance(x, str) or not x.strip() for x in self.critical_failures):
            raise ValidationError("critical failures must be non-empty strings")
        if self.method == "exact_json" and not isinstance(self.reference_answer, (dict, list, str, int, float, bool, type(None))):
            raise ValidationError("exact_json reference must be JSON-compatible")


@dataclass(frozen=True)
class Limits:
    max_output_tokens: int
    max_tool_calls: int

    def __post_init__(self) -> None:
        if not isinstance(self.max_output_tokens, int) or self.max_output_tokens <= 0:
            raise ValidationError("max_output_tokens must be a positive integer")
        if not isinstance(self.max_tool_calls, int) or self.max_tool_calls < 0:
            raise ValidationError("max_tool_calls must be a non-negative integer")


@dataclass(frozen=True)
class Provenance:
    origin: str
    real_personal_data: bool
    source_uri: str | None = None
    source_hash: str | None = None

    def __post_init__(self) -> None:
        require_text(self.origin, "provenance origin")
        if not isinstance(self.real_personal_data, bool):
            raise ValidationError("real_personal_data must be boolean")


@dataclass(frozen=True)
class Case:
    case_id: str
    family_id: str
    split: str
    complexity_level: int
    domain: str
    language: str
    tags: tuple[str, ...]
    messages: tuple[dict[str, str], ...]
    evaluation: Evaluation
    fixture_policy: str
    suite_version: str
    provenance: Provenance
    limits: Limits

    def __post_init__(self) -> None:
        require_id(self.case_id, "case_id")
        require_id(self.family_id, "family_id")
        require_text(self.suite_version, "suite_version")
        if self.split not in SPLITS:
            raise ValidationError(f"invalid split: {self.split}")
        if self.complexity_level not in DIFFICULTIES:
            raise ValidationError("complexity_level must be 1, 2, 3, or 4")
        if self.domain not in DOMAINS:
            raise ValidationError(f"invalid domain: {self.domain}")
        if not self.language or not isinstance(self.language, str):
            raise ValidationError("language is required")
        if not self.messages:
            raise ValidationError("messages cannot be empty")
        for message in self.messages:
            if not isinstance(message, dict) or message.get("role") not in {"system", "user", "assistant", "tool"}:
                raise ValidationError("messages must contain valid role/content records")
            require_text(message.get("content", ""), "message content")
        require_text(self.fixture_policy, "fixture_policy")

    @property
    def prompt_hash(self) -> str:
        return stable_hash(self.messages)

    def candidate_payload(self) -> dict[str, Any]:
        """Return the only structure allowed to cross into candidate execution."""
        return {
            "case_id": self.case_id,
            "messages": [dict(message) for message in self.messages],
            "limits": {"max_output_tokens": self.limits.max_output_tokens, "max_tool_calls": self.limits.max_tool_calls},
            "prompt_hash": self.prompt_hash,
        }


@dataclass(frozen=True)
class Suite:
    suite_version: str
    cases: tuple[Case, ...]
    source_path: str | None = None
    source_hash: str | None = None

    def __post_init__(self) -> None:
        require_text(self.suite_version, "suite_version")
        if not self.cases:
            raise ValidationError("suite must contain at least one case")
        ids = [case.case_id for case in self.cases]
        if len(ids) != len(set(ids)):
            raise ValidationError("duplicate case IDs")
        families = {case.family_id for case in self.cases}
        if not families:
            raise ValidationError("suite must contain family IDs")
        if any(case.suite_version != self.suite_version for case in self.cases):
            raise ValidationError("case/suite version mismatch")

    @property
    def case_ids(self) -> tuple[str, ...]:
        return tuple(case.case_id for case in self.cases)

    def get(self, case_id: str) -> Case:
        for case in self.cases:
            if case.case_id == case_id:
                return case
        raise ValidationError(f"unknown case ID: {case_id}")

    def candidate_records(self) -> tuple[dict[str, Any], ...]:
        return tuple(case.candidate_payload() for case in self.cases)


@dataclass(frozen=True)
class ModelConfig:
    provider: str
    model: str
    revision: str | None = None
    parameters: dict[str, Any] = field(default_factory=dict)
    context_condition: str = "short"

    def __post_init__(self) -> None:
        require_id(self.provider, "provider")
        require_id(self.model, "model")
        if not isinstance(self.parameters, dict):
            raise ValidationError("parameters must be an object")
        require_text(self.context_condition, "context_condition")


@dataclass(frozen=True)
class Budget:
    max_cases: int | None = None
    max_requests: int | None = None
    max_runtime_seconds: float | None = None
    max_cost_minor: int | None = None
    currency: str | None = None

    def __post_init__(self) -> None:
        for name in ("max_cases", "max_requests", "max_cost_minor"):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, int) or value < 0):
                raise ValidationError(f"{name} must be a non-negative integer or null")
        if self.max_runtime_seconds is not None and self.max_runtime_seconds < 0:
            raise ValidationError("max_runtime_seconds must be non-negative or null")
        if self.max_cost_minor is not None and not self.currency:
            raise ValidationError("currency is required when max_cost_minor is set")


@dataclass(frozen=True)
class Run:
    run_id: str
    suite_version: str
    case_ids: tuple[str, ...]
    model_config: ModelConfig
    seed: int | None
    budget: Budget
    started_at: str
    status: str = "created"
    environment: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        require_id(self.run_id, "run_id")
        require_text(self.suite_version, "suite_version")
        if not self.case_ids:
            raise ValidationError("run must contain cases")
        if self.status not in {"created", "running", "completed", "partial", "failed", "cancelled"}:
            raise ValidationError(f"invalid run status: {self.status}")


@dataclass(frozen=True)
class Attempt:
    attempt_id: str
    run_id: str
    logical_request_id: str
    case_id: str
    model_config: ModelConfig
    prompt_hash: str
    response_text: str | None
    status: AttemptStatus
    started_at: str
    completed_at: str | None = None
    finish_reason: str | None = None
    error: str | None = None
    first_token_latency_ms: float | None = None
    completion_latency_ms: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_minor: int | None = None
    currency: str | None = None
    metric_kinds: dict[str, MetricKind] = field(default_factory=dict)
    raw_metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in ("attempt_id", "run_id", "logical_request_id", "case_id", "prompt_hash"):
            require_id(getattr(self, name), name)
        if self.response_text is not None and not isinstance(self.response_text, str):
            raise ValidationError("response_text must be text or null")
        for name in ("first_token_latency_ms", "completion_latency_ms"):
            value = getattr(self, name)
            if value is not None and value < 0:
                raise ValidationError(f"{name} must be non-negative or null")
        for name in ("input_tokens", "output_tokens", "cost_minor"):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, int) or value < 0):
                raise ValidationError(f"{name} must be a non-negative integer or null")
        if self.cost_minor is not None and not self.currency:
            raise ValidationError("currency is required with cost_minor")
        if not isinstance(self.raw_metadata, dict):
            raise ValidationError("raw_metadata must be an object")


@dataclass(frozen=True)
class Grade:
    grade_id: str
    attempt_id: str
    grader_id: str
    grader_version: str
    method: str
    passed: bool | None
    score: float | None
    failure_reason: str | None
    evidence: dict[str, Any]
    created_at: str

    def __post_init__(self) -> None:
        for name in ("grade_id", "attempt_id", "grader_id", "grader_version"):
            require_id(getattr(self, name), name)
        if self.method not in EVALUATION_METHODS | {"human", "model_judge"}:
            raise ValidationError(f"unsupported grade method: {self.method}")
        if self.score is not None and not 0 <= self.score <= 1:
            raise ValidationError("grade score must be between 0 and 1")
        if self.passed is None and self.score is None:
            if not self.failure_reason:
                raise ValidationError("abstained grade needs a reason")
        if not isinstance(self.evidence, dict):
            raise ValidationError("grade evidence must be an object")


@dataclass(frozen=True)
class HumanReview:
    review_id: str
    run_id: str
    case_id: str
    blind_label: str
    reviewer_pseudonym: str
    decision: str
    score: float | None
    notes: str | None
    confidence: float | None
    created_at: str

    def __post_init__(self) -> None:
        for name in ("review_id", "run_id", "case_id", "blind_label", "reviewer_pseudonym"):
            require_id(getattr(self, name), name)
        if self.decision not in {"accept", "reject", "tie", "abstain"}:
            raise ValidationError("invalid human review decision")
        for name in ("score", "confidence"):
            value = getattr(self, name)
            if value is not None and not 0 <= value <= 1:
                raise ValidationError(f"{name} must be between 0 and 1")


@dataclass(frozen=True)
class ProvenanceRecord:
    record_id: str
    source_type: str
    source_label: str
    source_hash: str
    imported_at: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in ("record_id", "source_type", "source_label", "source_hash"):
            require_id(getattr(self, name), name)


def to_dict(value: Any) -> dict[str, Any] | list[Any] | Any:
    return _plain(value)


def canonical_record(value: Any) -> str:
    return stable_json(_plain(value))

