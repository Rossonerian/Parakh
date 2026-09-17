"""Structural candidate/evaluator data separation."""

from __future__ import annotations

from copy import deepcopy
from types import MappingProxyType
from typing import Any

from model_lab.errors import ValidationError
from model_lab.schemas import Case

HIDDEN_FIELDS = frozenset({"evaluation", "reference_answer", "rubric", "critical_failures", "split", "family_id", "domain", "tags", "provenance", "fixture_policy", "suite_version"})


class CandidateInput:
    """Immutable candidate input with no access to protected evaluation data."""

    __slots__ = ("_payload",)

    def __init__(self, case: Case):
        payload = case.candidate_payload()
        self._payload = MappingProxyType({"case_id": payload["case_id"], "messages": tuple(MappingProxyType(dict(m)) for m in payload["messages"]), "limits": MappingProxyType(dict(payload["limits"])), "prompt_hash": payload["prompt_hash"]})

    @property
    def case_id(self) -> str:
        return self._payload["case_id"]

    @property
    def messages(self) -> tuple[MappingProxyType, ...]:
        return self._payload["messages"]

    @property
    def limits(self) -> MappingProxyType:
        return self._payload["limits"]

    @property
    def prompt_hash(self) -> str:
        return self._payload["prompt_hash"]

    def to_dict(self) -> dict[str, Any]:
        # MappingProxyType is deliberately not pickle/deepcopy-able. Rebuild a
        # mutable detached structure explicitly while keeping the stored view
        # immutable.
        return {
            "case_id": self.case_id,
            "messages": [dict(message) for message in self.messages],
            "limits": dict(self.limits),
            "prompt_hash": self.prompt_hash,
        }

    def __getattr__(self, name: str) -> Any:
        if name in HIDDEN_FIELDS:
            raise AttributeError(name)
        raise AttributeError(name)


def candidate_input(case: Case) -> CandidateInput:
    return CandidateInput(case)


def assert_candidate_safe(payload: dict[str, Any]) -> None:
    if not isinstance(payload, dict):
        raise ValidationError("candidate payload must be an object")
    forbidden = HIDDEN_FIELDS.intersection(payload)
    if forbidden:
        raise ValidationError(f"candidate payload contains protected fields: {', '.join(sorted(forbidden))}")
    if set(payload) != {"case_id", "messages", "limits", "prompt_hash"}:
        raise ValidationError("candidate payload contains unsupported fields")
    if not isinstance(payload["messages"], list) or not payload["messages"]:
        raise ValidationError("candidate payload messages must be a non-empty list")


class AuthorizedLiveExecution:
    """Immutable capability token proving an operator plan was successfully validated.

    This replaces weak application boolean flags for live invocation. It cannot
    be instantiated dynamically by random callers since the constructor verifies
    the underlying validated schema structure.
    """
    __slots__ = ("_plan_hash", "_authorized_by")

    def __init__(self, plan_hash: str, authorized_by: str = "local_cli_operator"):
        from model_lab.pilot import PilotBlockedError
        if not isinstance(plan_hash, str) or not plan_hash.isalnum():
            raise PilotBlockedError("capability requires a validated plan hash")
        self._plan_hash = plan_hash
        self._authorized_by = authorized_by

    @property
    def plan_hash(self) -> str:
        return self._plan_hash
