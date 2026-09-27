"""Reward engine contracts, configuration, and immutable record definitions.

Defines versioned multi-objective reward configurations, granular factual
reward components, and canonical reward records for telemetry and benchmark runs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from model_lab.schema_registry import REWARD_SCHEMA_VERSION
from model_lab.schemas import stable_hash, to_dict

DEFAULT_WEIGHTS = {
    "quality": 1.0,
    "cost": 0.2,
    "latency": 0.1,
    "tool_failure": 0.2,
    "retry": 0.1,
}

DEFAULT_QUALITY_WEIGHTS = {
    "deterministic": 0.6,
    "rubric": 0.25,
    "user": 0.15,
}

DEFAULT_COST_ENVELOPE_PER_REQUEST = {
    "ananta": 0.002,
    "yanta": 0.01,
    "trika": 0.05,
    "part": 0.10,
    "default": 0.01,
}


@dataclass(frozen=True)
class RewardConfig:
    """Frozen configuration for multi-objective reward calculations."""

    weights: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_WEIGHTS))
    quality_weights: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_QUALITY_WEIGHTS))
    cost_envelope_per_request: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_COST_ENVELOPE_PER_REQUEST))
    default_latency_slo_ms: int = 8000
    cost_cap: float = 1.5
    latency_cap: float = 1.5
    critical_failure_reward: float = -1.0
    provisional: bool = True
    note: str = "tier envelopes are placeholders until Tier_Entitlements prices are measured"

    def to_dict(self) -> dict[str, Any]:
        return {
            "weights": dict(self.weights),
            "quality_weights": dict(self.quality_weights),
            "cost_envelope_per_request": dict(self.cost_envelope_per_request),
            "default_latency_slo_ms": self.default_latency_slo_ms,
            "cost_cap": self.cost_cap,
            "latency_cap": self.latency_cap,
            "critical_failure_reward": self.critical_failure_reward,
            "provisional": self.provisional,
            "note": self.note,
        }

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> RewardConfig:
        weights = dict(DEFAULT_WEIGHTS)
        if "weights" in d and isinstance(d["weights"], Mapping):
            weights.update(d["weights"])
        quality_weights = dict(DEFAULT_QUALITY_WEIGHTS)
        if "quality_weights" in d and isinstance(d["quality_weights"], Mapping):
            quality_weights.update(d["quality_weights"])
        cost_envelope = dict(DEFAULT_COST_ENVELOPE_PER_REQUEST)
        if "cost_envelope_per_request" in d and isinstance(d["cost_envelope_per_request"], Mapping):
            cost_envelope.update(d["cost_envelope_per_request"])

        return cls(
            weights=weights,
            quality_weights=quality_weights,
            cost_envelope_per_request=cost_envelope,
            default_latency_slo_ms=d.get("default_latency_slo_ms", 8000),
            cost_cap=float(d.get("cost_cap", 1.5)),
            latency_cap=float(d.get("latency_cap", 1.5)),
            critical_failure_reward=float(d.get("critical_failure_reward", -1.0)),
            provisional=bool(d.get("provisional", True)),
            note=str(d.get("note", "tier envelopes are placeholders until Tier_Entitlements prices are measured")),
        )

    def config_hash(self) -> str:
        return stable_hash(self.to_dict())


@dataclass(frozen=True)
class RewardComponents:
    """Granular factual components decomposing the scalar reward."""

    deterministic: float | None = None
    schema_correct: float | None = None
    tool_correct: float | None = None
    task_completed: float | None = None
    rubric: float | None = None
    user_signal: float | None = None
    cost_raw: float | None = None
    currency: str | None = None
    cost_normalized: float | None = None
    latency_ms: float | None = None
    latency_normalized: float | None = None
    tool_failure_penalty: float | None = None
    retry_penalty: float | None = None
    recovery_success: bool | None = None
    safety_violation: bool = False
    confidence: dict[str, float] = field(default_factory=dict)
    signal_strength: dict[str, str | None] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "deterministic": self.deterministic,
            "schema_correct": self.schema_correct,
            "tool_correct": self.tool_correct,
            "task_completed": self.task_completed,
            "rubric": self.rubric,
            "user_signal": self.user_signal,
            "cost_raw": self.cost_raw,
            "currency": self.currency,
            "cost_normalized": self.cost_normalized,
            "latency_ms": self.latency_ms,
            "latency_normalized": self.latency_normalized,
            "tool_failure_penalty": self.tool_failure_penalty,
            "retry_penalty": self.retry_penalty,
            "recovery_success": self.recovery_success,
            "safety_violation": self.safety_violation,
            "confidence": dict(self.confidence),
            "signal_strength": dict(self.signal_strength),
        }


@dataclass(frozen=True)
class RewardRecord:
    """Canonical reward record stored in optimization evidence."""

    reward_id: str
    subject_type: str
    subject_id: str
    schema_version: str = REWARD_SCHEMA_VERSION
    config_hash: str = ""
    components: RewardComponents = field(default_factory=RewardComponents)
    quality: float | None = None
    scalar: float | None = None
    confidence: float = 0.0
    excluded_reason: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "reward_id": self.reward_id,
            "subject_type": self.subject_type,
            "subject_id": self.subject_id,
            "schema_version": self.schema_version,
            "config_hash": self.config_hash,
            "components": self.components.to_dict() if isinstance(self.components, RewardComponents) else to_dict(self.components),
            "quality": self.quality,
            "scalar": self.scalar,
            "confidence": self.confidence,
            "excluded_reason": self.excluded_reason,
            "metadata": dict(self.metadata),
        }
