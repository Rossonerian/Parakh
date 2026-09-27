"""TelemetryBatchV1: the only shape in which Karmi evidence enters Parakh.

The published contract is ``contracts/telemetry_batch_v1.schema.json``; this
module is its authoritative parser. Batch-level problems reject the whole
batch (``TelemetryBatchError``). Run-level problems never coerce data: the run
is returned in ``ParsedBatch.invalid`` with machine-readable reason codes so the
importer can quarantine it with lineage.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping

from model_lab.errors import ValidationError
from model_lab.schema_registry import TELEMETRY_SCHEMA, TELEMETRY_SCHEMA_VERSION
from model_lab.schemas import ID_RE, stable_hash


class TelemetryBatchError(ValidationError):
    """The batch envelope itself is unusable; nothing from it is imported."""


CONTEXT_FIELDS: dict[str, type | tuple[type, ...]] = {
    "tier": str,
    "task_domain": str,
    "estimated_input_tokens": int,
    "context_utilization_ratio": (int, float),
    "tool_count": int,
    "requires_structured_output": bool,
    "requires_tools": bool,
    "requires_memory": bool,
    "requires_external_data": bool,
    "conversation_depth": int,
    "retry_number": int,
    "previous_tool_failure": bool,
}
OPTIONAL_CONTEXT_FIELDS: dict[str, type | tuple[type, ...]] = {
    "latency_slo_ms": int,
    "previous_structured_output_failure": bool,
}
OUTCOME_BOOL_FIELDS = ("completed", "first_shot_success", "structured_output_valid", "tool_success",
                       "user_retry_signal", "user_abandon_signal", "user_accept_signal", "user_correction_signal",
                       "critical_failure")
FEEDBACK_TYPES = {"edit", "correction", "rating", "retry", "abandon", "accept", "intent_change", "other"}


@dataclass(frozen=True)
class ModelInfo:
    provider: str
    model: str
    model_version: str | None
    max_context_tokens: int
    supports_tools: bool
    supports_structured_output: bool
    estimated_input_cost_per_token: float
    estimated_output_cost_per_token: float

    @property
    def action_id(self) -> str:
        return action_id(self.provider, self.model)


@dataclass(frozen=True)
class Decision:
    decision_id: str
    selected_provider: str
    selected_model: str
    policy_version: str
    selection_probability: float
    exploration: bool
    shadow: bool
    eligible_models: tuple[str, ...]
    feature_schema_version: str
    created_at: str

    @property
    def action(self) -> str:
        return action_id(self.selected_provider, self.selected_model)


@dataclass(frozen=True)
class RunRecord:
    """A validated run. ``raw`` is the exact source mapping (never mutated)."""

    run_id: str
    request_id: str
    session_id_hash: str | None
    started_at: str
    completed_at: str | None
    task_domain: str
    tier: str
    harness_version: str
    prompt_version: str
    policy_version: str
    feature_schema_version: str
    status: str
    routing_context: Mapping[str, Any]
    live_decision: Decision
    shadow_decisions: tuple[Decision, ...]
    attempts: tuple[Mapping[str, Any], ...]
    tool_events: tuple[Mapping[str, Any], ...]
    validation_events: tuple[Mapping[str, Any], ...]
    outcome: Mapping[str, Any]
    feedback: tuple[Mapping[str, Any], ...]
    raw: Mapping[str, Any] = field(repr=False)


@dataclass(frozen=True)
class InvalidRun:
    index: int
    run_id: str | None
    reasons: tuple[str, ...]
    raw: Any = field(repr=False)


@dataclass(frozen=True)
class ParsedBatch:
    batch_id: str
    schema_version: str
    generated_at: str
    producer_repo: str
    producer_version: str
    feature_schema_version: str
    window: Mapping[str, Any]
    model_registry: tuple[ModelInfo, ...]
    checksum: str
    valid: tuple[RunRecord, ...]
    invalid: tuple[InvalidRun, ...]
    raw: Mapping[str, Any] = field(repr=False)


def action_id(provider: str, model: str) -> str:
    """Stable action key shared with Karmi: ``provider/model``."""
    return f"{provider}/{model}"


def batch_checksum(batch: Mapping[str, Any]) -> str:
    return stable_hash(batch)


def _timestamp(value: Any) -> bool:
    if not isinstance(value, str) or not value:
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


def _is(value: Any, kind: type | tuple[type, ...]) -> bool:
    if isinstance(value, bool) and kind is not bool and (kind is int or (isinstance(kind, tuple) and bool not in kind)):
        return False
    if isinstance(value, float) and not math.isfinite(value):
        return False
    return isinstance(value, kind)


def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _model_info(raw: Any, index: int) -> ModelInfo:
    if not isinstance(raw, Mapping):
        raise TelemetryBatchError(f"model_registry[{index}] must be an object")
    try:
        info = ModelInfo(
            provider=raw["provider"], model=raw["model"], model_version=raw.get("model_version"),
            max_context_tokens=raw["max_context_tokens"], supports_tools=raw["supports_tools"],
            supports_structured_output=raw["supports_structured_output"],
            estimated_input_cost_per_token=raw["estimated_input_cost_per_token"],
            estimated_output_cost_per_token=raw["estimated_output_cost_per_token"],
        )
    except KeyError as exc:
        raise TelemetryBatchError(f"model_registry[{index}] missing {exc.args[0]}") from exc
    if not (_text(info.provider) and _text(info.model) and _is(info.max_context_tokens, int) and info.max_context_tokens > 0
            and _is(info.supports_tools, bool) and _is(info.supports_structured_output, bool)
            and all(_is(v, (int, float)) and v >= 0 for v in (info.estimated_input_cost_per_token, info.estimated_output_cost_per_token))):
        raise TelemetryBatchError(f"model_registry[{index}] has invalid field types")
    return info


def _decision(raw: Any, index: int, errors: list[str]) -> Decision | None:
    prefix = f"decisions[{index}]"
    if not isinstance(raw, Mapping):
        errors.append(f"{prefix}.not_object")
        return None
    missing = [k for k in ("decision_id", "selected_provider", "selected_model", "policy_version", "selection_probability",
                           "exploration", "shadow", "eligible_models", "feature_schema_version", "created_at") if k not in raw]
    if missing:
        errors.extend(f"{prefix}.missing_{k}" for k in missing)
        return None
    probability = raw["selection_probability"]
    if not _is(probability, (int, float)) or not 0 < probability <= 1:
        errors.append(f"{prefix}.invalid_selection_probability")
    eligible = raw["eligible_models"]
    if not isinstance(eligible, list) or not eligible or not all(_text(e) for e in eligible) or len(set(eligible)) != len(eligible):
        errors.append(f"{prefix}.invalid_eligible_models")
        eligible = []
    for name in ("decision_id", "selected_provider", "selected_model", "policy_version", "feature_schema_version"):
        if not _text(raw[name]):
            errors.append(f"{prefix}.invalid_{name}")
    for name in ("exploration", "shadow"):
        if not _is(raw[name], bool):
            errors.append(f"{prefix}.invalid_{name}")
    if not _timestamp(raw["created_at"]):
        errors.append(f"{prefix}.invalid_created_at")
    if errors:
        return None
    decision = Decision(raw["decision_id"], raw["selected_provider"], raw["selected_model"], raw["policy_version"],
                        float(probability), raw["exploration"], raw["shadow"], tuple(eligible),
                        raw["feature_schema_version"], raw["created_at"])
    if decision.action not in decision.eligible_models:
        errors.append(f"{prefix}.selected_not_eligible")
        return None
    return decision


def _objects(raw: Mapping[str, Any], name: str, errors: list[str], required: tuple[str, ...]) -> tuple[Mapping[str, Any], ...]:
    value = raw.get(name, [])
    if not isinstance(value, list) or not all(isinstance(item, Mapping) for item in value):
        errors.append(f"{name}.not_list_of_objects")
        return ()
    for i, item in enumerate(value):
        for key in required:
            if key not in item:
                errors.append(f"{name}[{i}].missing_{key}")
    return tuple(value)


def parse_run(raw: Any, index: int, batch_feature_schema: str) -> RunRecord | InvalidRun:
    errors: list[str] = []
    if not isinstance(raw, Mapping):
        return InvalidRun(index, None, ("run.not_object",), raw)
    run_id = raw.get("run_id")
    if not isinstance(run_id, str) or not ID_RE.fullmatch(run_id):
        errors.append("run.invalid_run_id")
        run_id = run_id if isinstance(run_id, str) else None
    for name in ("request_id", "task_domain", "tier", "harness_version", "prompt_version", "policy_version", "feature_schema_version", "status"):
        if not _text(raw.get(name)):
            errors.append(f"run.missing_{name}")
    if raw.get("feature_schema_version") not in (None, batch_feature_schema):
        errors.append("run.feature_schema_mismatch")
    if not _timestamp(raw.get("started_at")):
        errors.append("run.invalid_started_at")
    if raw.get("completed_at") is not None and not _timestamp(raw.get("completed_at")):
        errors.append("run.invalid_completed_at")

    context = raw.get("routing_context")
    if not isinstance(context, Mapping):
        errors.append("routing_context.missing")
        context = {}
    for name, kind in CONTEXT_FIELDS.items():
        if name not in context:
            errors.append(f"routing_context.missing_{name}")
        elif not _is(context[name], kind):
            errors.append(f"routing_context.invalid_{name}")
    for name, kind in OPTIONAL_CONTEXT_FIELDS.items():
        if context.get(name) is not None and not _is(context[name], kind):
            errors.append(f"routing_context.invalid_{name}")
    for name in ("estimated_input_tokens", "tool_count", "conversation_depth", "retry_number"):
        if _is(context.get(name), int) and context[name] < 0:
            errors.append(f"routing_context.negative_{name}")
    ratio = context.get("context_utilization_ratio")
    if _is(ratio, (int, float)) and not 0 <= ratio <= 1:
        errors.append("routing_context.ratio_out_of_range")
    if context and (context.get("tier") != raw.get("tier") or context.get("task_domain") != raw.get("task_domain")):
        errors.append("routing_context.run_mismatch")

    decisions_raw = raw.get("decisions")
    live: list[Decision] = []
    shadow: list[Decision] = []
    if not isinstance(decisions_raw, list) or not decisions_raw:
        errors.append("decisions.missing")
    else:
        for i, item in enumerate(decisions_raw):
            local: list[str] = []
            decision = _decision(item, i, local)
            errors.extend(local)
            if decision is not None:
                (shadow if decision.shadow else live).append(decision)
    if isinstance(decisions_raw, list) and decisions_raw and len(live) != 1 and not any(e.startswith("decisions[") for e in errors):
        errors.append("decisions.exactly_one_live_required")

    attempts = _objects(raw, "attempts", errors, ("attempt_id", "provider", "model", "success", "retry_number"))
    tool_events = _objects(raw, "tool_events", errors, ("event_id", "tool_name", "schema_valid", "execution_success"))
    validation_events = _objects(raw, "validation_events", errors, ("event_id", "validator", "passed"))
    feedback = _objects(raw, "feedback", errors, ("feedback_id", "feedback_type", "created_at"))
    for i, item in enumerate(feedback):
        if item.get("feedback_type") not in FEEDBACK_TYPES:
            errors.append(f"feedback[{i}].unknown_type")

    outcome = raw.get("outcome")
    if not isinstance(outcome, Mapping):
        errors.append("outcome.missing")
        outcome = {}
    for name in OUTCOME_BOOL_FIELDS:
        if outcome.get(name) is not None and not _is(outcome[name], bool):
            errors.append(f"outcome.invalid_{name}")
    for name in ("retry_count", "final_latency_ms"):
        value = outcome.get(name)
        if value is not None and (not _is(value, (int, float)) or value < 0):
            errors.append(f"outcome.invalid_{name}")
    cost = outcome.get("final_cost")
    if cost is not None and (not _is(cost, (int, float)) or cost < 0 or not _text(outcome.get("currency"))):
        errors.append("outcome.invalid_final_cost_or_currency")

    if errors:
        return InvalidRun(index, run_id, tuple(dict.fromkeys(errors)), raw)
    return RunRecord(
        run_id=run_id, request_id=raw["request_id"], session_id_hash=raw.get("session_id_hash"),
        started_at=raw["started_at"], completed_at=raw.get("completed_at"), task_domain=raw["task_domain"], tier=raw["tier"],
        harness_version=raw["harness_version"], prompt_version=raw["prompt_version"], policy_version=raw["policy_version"],
        feature_schema_version=raw["feature_schema_version"], status=raw["status"], routing_context=dict(context),
        live_decision=live[0], shadow_decisions=tuple(shadow), attempts=attempts, tool_events=tool_events,
        validation_events=validation_events, outcome=dict(outcome), feedback=feedback, raw=raw,
    )


def parse_batch(batch: Any) -> ParsedBatch:
    """Validate the envelope strictly, then each run independently."""
    if not isinstance(batch, Mapping):
        raise TelemetryBatchError("telemetry batch must be a JSON object")
    if batch.get("schema") != TELEMETRY_SCHEMA:
        raise TelemetryBatchError(f"unsupported schema {batch.get('schema')!r}; expected {TELEMETRY_SCHEMA}")
    version = batch.get("schema_version")
    if not isinstance(version, str) or version.split(".")[0] != TELEMETRY_SCHEMA_VERSION.split(".")[0]:
        raise TelemetryBatchError(f"unsupported schema_version {version!r}")
    batch_id = batch.get("batch_id")
    if not isinstance(batch_id, str) or not ID_RE.fullmatch(batch_id):
        raise TelemetryBatchError("batch_id must be a stable identifier")
    if not _timestamp(batch.get("generated_at")):
        raise TelemetryBatchError("generated_at must be an ISO timestamp")
    producer = batch.get("producer")
    if not isinstance(producer, Mapping) or not _text(producer.get("repo")) or not _text(producer.get("version")):
        raise TelemetryBatchError("producer.repo and producer.version are required")
    feature_schema = batch.get("feature_schema_version")
    if not _text(feature_schema):
        raise TelemetryBatchError("feature_schema_version is required")
    window = batch.get("window") or {}
    if not isinstance(window, Mapping):
        raise TelemetryBatchError("window must be an object")
    registry_raw = batch.get("model_registry")
    if not isinstance(registry_raw, list) or not registry_raw:
        raise TelemetryBatchError("model_registry must list the eligible model catalogue")
    registry = tuple(_model_info(item, i) for i, item in enumerate(registry_raw))
    if len({m.action_id for m in registry}) != len(registry):
        raise TelemetryBatchError("model_registry contains duplicate provider/model entries")
    runs = batch.get("runs")
    if not isinstance(runs, list):
        raise TelemetryBatchError("runs must be a list")
    valid: list[RunRecord] = []
    invalid: list[InvalidRun] = []
    seen: set[str] = set()
    known = {m.action_id for m in registry}
    for index, raw in enumerate(runs):
        parsed = parse_run(raw, index, feature_schema)
        if isinstance(parsed, RunRecord):
            unknown = [a for d in (parsed.live_decision, *parsed.shadow_decisions) for a in (*d.eligible_models, d.action) if a not in known]
            if unknown:
                parsed = InvalidRun(index, parsed.run_id, ("decisions.model_not_in_registry",), raw)
            elif parsed.run_id in seen:
                parsed = InvalidRun(index, parsed.run_id, ("run.duplicate_run_id_in_batch",), raw)
        if isinstance(parsed, RunRecord):
            seen.add(parsed.run_id)
            valid.append(parsed)
        else:
            invalid.append(parsed)
    return ParsedBatch(batch_id, version, batch["generated_at"], producer["repo"], producer["version"], feature_schema,
                       dict(window), registry, batch_checksum(batch), tuple(valid), tuple(invalid), batch)
