"""Controlled live-pilot planning and fail-closed dispatch authorization.

Planning is safe without credentials. Dispatch is deliberately not performed by
this preparation pass: a plan must contain operator-selected candidates, a
pricing snapshot, a positive spend ceiling, and an explicit authorization record
before any future runner may call a provider.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
from typing import Any, Iterable, Mapping

from .benchmark import load_suite, select_cases
from .errors import ModelLabError, ValidationError
from .schemas import Budget, ModelConfig, Run, canonical_record, stable_hash, utc_now


PILOT_PLAN_VERSION = "0.1.0"
DEVELOPMENT_SPLIT = "train"
DEVELOPMENT_CASE_COUNT = 36


class PilotBlockedError(ModelLabError):
    """A live pilot cannot dispatch under the current authorization state."""


def _file_sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


@dataclass(frozen=True)
class CandidateSpec:
    provider: str
    model: str
    revision: str | None = None

    def to_dict(self) -> dict[str, str | None]:
        return {"provider": self.provider, "model": self.model, "revision": self.revision}


def parse_candidate_spec(value: str) -> CandidateSpec:
    parts = value.split(":", 2)
    if len(parts) < 2 or not parts[0].strip() or not parts[1].strip():
        raise ValidationError("candidate must use provider:model[:revision]")
    return CandidateSpec(parts[0].strip(), parts[1].strip(), parts[2].strip() or None)


def build_pilot_plan(
    suite_path: str | Path,
    *,
    candidates: Iterable[CandidateSpec] = (),
    repeats: int = 1,
    temperature: float | None = 0.0,
    seed: int | None = 17,
    max_output_tokens: int = 1200,
    timeout_seconds: float = 60.0,
    concurrency: int = 1,
    max_retries: int = 0,
    max_spend_minor: int | None = None,
    currency: str = "USD",
    pricing_snapshot: Mapping[str, Any] | None = None,
    prompt_template_revision: str = "candidate-v1",
    source_manifest: str = "docs/product_sources/SOURCE_MANIFEST.json",
) -> dict[str, Any]:
    suite = load_suite(suite_path)
    selected = select_cases(suite, splits=[DEVELOPMENT_SPLIT])
    if len(selected) != DEVELOPMENT_CASE_COUNT:
        raise ValidationError(f"development pilot requires exactly {DEVELOPMENT_CASE_COUNT} train cases; found {len(selected)}")
    if repeats < 1 or concurrency < 1 or max_retries < 0:
        raise ValidationError("repeats/concurrency must be positive and max_retries non-negative")
    if max_output_tokens < 1 or timeout_seconds <= 0:
        raise ValidationError("output and timeout limits must be positive")
    if max_spend_minor is not None and max_spend_minor <= 0:
        raise ValidationError("max_spend_minor must be positive when supplied")
    if not currency or len(currency) != 3:
        raise ValidationError("currency must be a three-letter code")
    candidate_list = [candidate.to_dict() for candidate in candidates]
    frozen = {
        "prompt_template_revision": prompt_template_revision,
        "generation": {"temperature": temperature, "seed": seed, "max_output_tokens": max_output_tokens},
        "execution": {"timeout_seconds": timeout_seconds, "concurrency": concurrency, "repeats": repeats, "max_retries": max_retries},
    }
    plan: dict[str, Any] = {
        "plan_version": PILOT_PLAN_VERSION,
        "status": "awaiting_operator_selection",
        "suite_version": suite.suite_version,
        "suite_hash": suite.source_hash,
        "development_split": DEVELOPMENT_SPLIT,
        "case_count": len(selected),
        "case_ids": [case.case_id for case in selected],
        "family_count": len({case.family_id for case in selected}),
        "candidate_models": candidate_list,
        "frozen_configuration": frozen,
        "pricing_snapshot": dict(pricing_snapshot) if pricing_snapshot is not None else None,
        "budget": {"max_spend_minor": max_spend_minor, "currency": currency, "authorization_required": True},
        "authorization": {"paid_dispatch_allowed": False, "approved_by": None, "approved_at": None, "approved_max_spend_minor": None},
        "routing_constraints": {
            "recommendation_mode": "draft_only",
            "production_router_change": False,
            "subscription_ids": ["ananta", "yanta", "trika", "part"],
            "entitlements_are_not_model_ids": True,
            "no_universal_winner": True,
            "calibration_and_holdout_untouched": True,
            "product_source_manifest": source_manifest,
        },
        "provider_data_policy": {"customer_data": False, "synthetic_benchmark_only": False, "paid_calls_before_authorization": False},
    }
    blockers: list[str] = []
    if not candidate_list:
        blockers.append("operator_candidate_models_required")
    if max_spend_minor is None:
        blockers.append("approved_max_spend_required")
    if pricing_snapshot is None:
        blockers.append("pricing_snapshot_required")
    plan["blockers"] = blockers
    plan["ready_for_paid_dispatch"] = False
    plan_id_input = {key: value for key, value in plan.items() if key not in {"status", "blockers", "ready_for_paid_dispatch"}}
    plan["plan_id"] = "pilot-" + hashlib.sha256(canonical_record(plan_id_input).encode("utf-8")).hexdigest()[:24]
    return plan


def validate_pilot_plan(plan: Mapping[str, Any]) -> list[str]:
    if plan.get("immutable") is True:
        blockers: list[str] = []
        if plan.get("development_only") is not True:
            blockers.append("development_only_declaration_required")
        exclusions = plan.get("exclusions")
        if not isinstance(exclusions, Mapping) or any(exclusions.get(key) is not True for key in ("customer_data", "calibration_holdout", "production_router_changes", "external_actions")):
            blockers.append("development_only_exclusions_required")
        if len(plan.get("case_ids", [])) != DEVELOPMENT_CASE_COUNT:
            blockers.append("pilot_must_contain_exactly_36_development_cases")
        if not isinstance(plan.get("candidates"), list) or not 3 <= len(plan["candidates"]) <= 5:
            blockers.append("three_to_five_candidate_models_required")
        if not isinstance(plan.get("pricing_snapshot"), Mapping) or not plan.get("pricing_snapshot_hash"):
            blockers.append("pricing_snapshot_required")
        if not isinstance(plan.get("budget"), Mapping) or not plan["budget"].get("total_max_spend"):
            blockers.append("approved_max_spend_required")
        authorization = plan.get("authorization")
        if not isinstance(authorization, Mapping) or authorization.get("approved") is not True or not authorization.get("operator_identity") or not authorization.get("authorized_at"):
            blockers.append("explicit_paid_dispatch_authorization_required")
        for name in ("source_hash", "constraint_hash", "model_configuration_hash", "pricing_snapshot_hash", "case_set_hash", "plan_hash"):
            if not plan.get(name):
                blockers.append(f"{name}_required")
        return sorted(set(blockers))
    blockers = list(plan.get("blockers", []))
    if plan.get("development_split") != DEVELOPMENT_SPLIT:
        blockers.append("development_split_must_be_train")
    if plan.get("case_count") != DEVELOPMENT_CASE_COUNT or len(plan.get("case_ids", [])) != DEVELOPMENT_CASE_COUNT:
        blockers.append("pilot_must_contain_exactly_36_development_cases")
    if plan.get("budget", {}).get("max_spend_minor") is None:
        blockers.append("approved_max_spend_required")
    if plan.get("pricing_snapshot") is None:
        blockers.append("pricing_snapshot_required")
    if not plan.get("candidate_models"):
        blockers.append("operator_candidate_models_required")
    return sorted(set(blockers))


def authorize_dispatch(plan: Mapping[str, Any], *, approved_by: str, approved_max_spend_minor: int) -> dict[str, Any]:
    """Return an authorized copy only when an external operator explicitly supplies approval."""
    if not approved_by.strip() or approved_max_spend_minor <= 0:
        raise PilotBlockedError("operator identity and positive approved spend are required")
    result = dict(plan)
    budget = dict(result.get("budget", {}))
    planned = budget.get("max_spend_minor")
    if planned is None or approved_max_spend_minor > planned:
        raise PilotBlockedError("approved spend cannot exceed the displayed plan ceiling")
    authorization = dict(result.get("authorization", {}))
    authorization.update({"paid_dispatch_allowed": True, "approved_by": approved_by, "approved_max_spend_minor": approved_max_spend_minor})
    result["authorization"] = authorization
    result["ready_for_paid_dispatch"] = not validate_pilot_plan(result)
    result["blockers"] = validate_pilot_plan(result)
    return result


def verify_immutable_plan(plan: Mapping[str, Any], *, source_manifest_path: str | Path, constraint_map_path: str | Path) -> None:
    """Verify every frozen content and source binding before paid dispatch."""
    if plan.get("immutable") is not True or not isinstance(plan.get("plan_hash"), str):
        raise PilotBlockedError("paid pilot execution requires an immutable hashed plan")
    unsigned = dict(plan)
    plan_hash = unsigned.pop("plan_hash")
    if stable_hash(unsigned) != plan_hash:
        raise PilotBlockedError("immutable plan hash mismatch")
    expected = {
        "case_set_hash": stable_hash(plan.get("case_ids")),
        "model_configuration_hash": stable_hash({"candidates": plan.get("candidates"), "execution": plan.get("execution"), "prompt_template_revision": plan.get("prompt_template_revision")}),
        "pricing_snapshot_hash": stable_hash(plan.get("pricing_snapshot")),
        "source_hash": _file_sha256(source_manifest_path),
        "constraint_hash": _file_sha256(constraint_map_path),
    }
    for name, actual in expected.items():
        if plan.get(name) != actual:
            raise PilotBlockedError(f"immutable plan {name} mismatch")
    if plan.get("source_manifest_path") not in (None, str(source_manifest_path)):
        raise PilotBlockedError("immutable plan source manifest path mismatch")
    if plan.get("constraint_map_path") not in (None, str(constraint_map_path)):
        raise PilotBlockedError("immutable plan constraint map path mismatch")


def require_dispatch_authorization(plan: Mapping[str, Any], *, allow_paid: bool,
                                   source_manifest_path: str | Path | None = None,
                                   constraint_map_path: str | Path | None = None) -> None:
    blockers = validate_pilot_plan(plan)
    if not allow_paid:
        blockers.append("explicit_allow_paid_acknowledgement_required")
    if blockers:
        raise PilotBlockedError("live pilot blocked: " + ", ".join(sorted(set(blockers))))
    if plan.get("immutable") is True:
        if source_manifest_path is None or constraint_map_path is None:
            raise PilotBlockedError("immutable plan source and constraint paths are required")
        verify_immutable_plan(plan, source_manifest_path=source_manifest_path, constraint_map_path=constraint_map_path)


def dispatch_preview(plan: Mapping[str, Any]) -> dict[str, Any]:
    """Return the exact evidence displayed immediately before any dispatch."""
    immutable = plan.get("immutable") is True
    execution = plan.get("execution", {}) if immutable else plan.get("frozen_configuration", {}).get("execution", {})
    generation = plan.get("execution", {}) if immutable else plan.get("frozen_configuration", {}).get("generation", {})
    return {
        "dispatch_preview": True,
        "plan_hash": plan.get("plan_hash") or plan.get("plan_id"),
        "source_hash": plan.get("source_hash"),
        "constraint_hash": plan.get("constraint_hash"),
        "model_configuration_hash": plan.get("model_configuration_hash"),
        "pricing_snapshot_hash": plan.get("pricing_snapshot_hash"),
        "case_set_hash": plan.get("case_set_hash"),
        "case_ids": list(plan.get("case_ids", [])),
        "candidate_models": plan.get("candidates") if immutable else plan.get("candidate_models", []),
        "base_calls": plan.get("bounds", {}).get("base_calls"),
        "maximum_calls": plan.get("bounds", {}).get("maximum_calls"),
        "retry_limit": execution.get("retry_limit", execution.get("max_retries")),
        "repeats": execution.get("repeats"),
        "concurrency": execution.get("concurrency"),
        "timeout_seconds": execution.get("timeout_seconds"),
        "max_output_tokens": generation.get("max_output_tokens"),
        "judge_enabled": execution.get("judge_enabled", False),
        "red_team_enabled": execution.get("red_team_enabled", False),
        "budget": plan.get("budget"),
        "dispatch_performed": False,
    }


def _provider_for(candidate: Mapping[str, Any]):
    import os

    provider = candidate["provider"]
    model = candidate["model"]
    if provider == "ollama":
        if not os.environ.get("MODELLAB_OLLAMA_ENDPOINT"):
            raise PilotBlockedError("ollama disabled: missing MODELLAB_OLLAMA_ENDPOINT")
        from .providers.live import OllamaProvider
        return OllamaProvider(model)
    if provider == "openrouter":
        if not os.environ.get("OPENROUTER_API_KEY"):
            raise PilotBlockedError("openrouter disabled: missing OPENROUTER_API_KEY")
        from .providers.live import OpenRouterProvider
        return OpenRouterProvider(model)
    raise PilotBlockedError(f"unsupported pilot provider: {provider}")


def run_authorized_immutable_pilot(plan: Mapping[str, Any], *, suite_path: str | Path, output_dir: str | Path,
                                   source_manifest_path: str | Path, constraint_map_path: str | Path) -> dict[str, Any]:
    """Execute a validated, authorized development plan; never alters app routing.

    This path is intentionally unavailable to incomplete plans.  It is not used
    by fixture CI and is not invoked in this repository verification pass.
    """
    if plan.get("immutable") is not True:
        raise PilotBlockedError("paid pilot execution requires an immutable operator plan")
    require_dispatch_authorization(plan, allow_paid=True, source_manifest_path=source_manifest_path, constraint_map_path=constraint_map_path)
    execution = plan["execution"]
    if execution["concurrency"] != 1:
        raise PilotBlockedError("live pilot runner currently supports concurrency=1 only")
    if execution.get("judge_enabled") or execution.get("red_team_enabled"):
        raise PilotBlockedError("judge and red-team dispatch are disabled for the first development pilot")
    suite = load_suite(suite_path)
    if suite.suite_version != plan.get("suite_version") or suite.source_hash != plan.get("suite_hash"):
        raise PilotBlockedError("benchmark version/hash does not match frozen plan")
    case_ids = tuple(plan["case_ids"])
    if len(case_ids) != DEVELOPMENT_CASE_COUNT or any(case.split != DEVELOPMENT_SPLIT for case in select_cases(suite, case_ids=case_ids)):
        raise PilotBlockedError("frozen plan contains non-train cases")

    from .execution import ExecutionEngine
    from .storage import SQLiteStore

    destination = Path(output_dir)
    # Verify every provider configuration before persisting a run or issuing a
    # single paid request; no partial model set is an authorized experiment.
    providers = {candidate["identifier"]: _provider_for(candidate) for candidate in plan["candidates"]}
    store = SQLiteStore(destination / "model_lab.sqlite3")
    results: list[dict[str, Any]] = []
    try:
        for candidate_index, candidate in enumerate(plan["candidates"]):
            per_call = int(plan["bounds"]["per_call_bound_minor"][candidate["identifier"]])
            per_logical = per_call * (int(execution["retry_limit"]) + 1)
            for repeat_index in range(int(execution["repeats"])):
                run_id = "pilot-" + stable_hash({"plan": plan["plan_hash"], "candidate": candidate["identifier"], "repeat": repeat_index})[:24]
                parameters: dict[str, Any] = {"temperature": execution["temperature"], "max_tokens": execution["max_output_tokens"]}
                if candidate["provider"] == "ollama":
                    parameters["num_predict"] = execution["max_output_tokens"]
                run = Run(
                    run_id=run_id,
                    suite_version=suite.suite_version,
                    case_ids=case_ids,
                    model_config=ModelConfig(candidate["provider"], candidate["model"], revision=candidate.get("revision"), parameters=parameters),
                    seed=execution["seed"],
                    budget=Budget(max_cases=DEVELOPMENT_CASE_COUNT, max_requests=DEVELOPMENT_CASE_COUNT,
                                  max_runtime_seconds=float(execution["timeout_seconds"]) * DEVELOPMENT_CASE_COUNT * (int(execution["retry_limit"]) + 1),
                                  max_cost_minor=per_logical * DEVELOPMENT_CASE_COUNT, currency=plan["budget"]["currency"]),
                    started_at=utc_now(),
                    environment={"mode": "development_live_authorized", "plan_hash": plan["plan_hash"], "source_hash": str(plan["source_hash"]), "constraint_hash": str(plan["constraint_hash"]), "customer_data": "false", "production_router_change": "false"},
                )
                engine = ExecutionEngine(store, providers[candidate["identifier"]], max_retries=int(execution["retry_limit"]),
                                         estimated_cost_minor_per_logical_request=per_logical,
                                         provider_timeout_seconds=float(execution["timeout_seconds"]))
                result = engine.execute(suite, run, case_ids=case_ids)
                results.append({"run_id": result.run_id, "candidate_index": candidate_index, "candidate": candidate["identifier"], "repeat": repeat_index + 1, "status": result.status, "attempts": len(result.attempts), "failures": result.failures})
    finally:
        store.close()
    return {"plan_hash": plan["plan_hash"], "results": results, "dispatch_performed": True, "production_config_changed": False, "customer_data_used": False}


def write_plan(plan: Mapping[str, Any], path: str | Path) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    import json
    destination.write_text(json.dumps(plan, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
