"""HarnessCandidate definition, hashing, and oracle-leak isolation checks.

Candidates assemble immutable prompt versions into a cohesive harness configuration
alongside a recovery policy. Candidates are content-addressed by their component mapping
and recovery policy.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from model_lab.errors import IntegrityError, ValidationError
from model_lab.schemas import Case, freeze_json, require_text, stable_hash, utc_now
from model_lab.optimization.harness.prompt_registry import PromptRegistry


def candidate_digest(components: Mapping[str, str], recovery_policy: Mapping[str, Any]) -> str:
    """Generate content-addressed identifier for a harness candidate."""
    payload = {
        "components": dict(components),
        "recovery_policy": dict(recovery_policy),
    }
    return "hc-" + stable_hash(payload)[:16]


@dataclass(frozen=True)
class HarnessCandidate:
    """Frozen, content-addressed harness candidate."""

    candidate_id: str
    parent_candidate_id: str | None
    components: dict[str, str]
    recovery_policy: dict[str, Any]
    generation_method: str
    training_case_ids: tuple[str, ...]
    created_at: str = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        require_text(self.generation_method, "generation_method")
        expected_id = candidate_digest(self.components, self.recovery_policy)
        if self.candidate_id != expected_id:
            object.__setattr__(self, "candidate_id", expected_id)
        object.__setattr__(self, "components", freeze_json(self.components))
        object.__setattr__(self, "recovery_policy", freeze_json(self.recovery_policy))
        object.__setattr__(self, "training_case_ids", tuple(self.training_case_ids))

    def texts(self, registry: PromptRegistry) -> dict[str, str]:
        """Fetch the prompt texts for each component in this candidate."""
        return {
            component: registry.get(prompt_id).text
            for component, prompt_id in sorted(self.components.items())
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "parent_candidate_id": self.parent_candidate_id,
            "components": dict(self.components),
            "recovery_policy": dict(self.recovery_policy),
            "generation_method": self.generation_method,
            "training_case_ids": list(self.training_case_ids),
            "created_at": self.created_at,
        }


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().casefold()


def _string_leaves(obj: Any, min_length: int = 8) -> list[str]:
    leaves: list[str] = []
    if isinstance(obj, str):
        if len(obj.strip()) >= min_length:
            leaves.append(obj)
    elif isinstance(obj, Mapping):
        for v in obj.values():
            leaves.extend(_string_leaves(v, min_length=min_length))
    elif isinstance(obj, (list, tuple)):
        for item in obj:
            leaves.extend(_string_leaves(item, min_length=min_length))
    return leaves


def assert_oracle_free(texts: Mapping[str, str], cases: Iterable[Case]) -> None:
    """Ensure no benchmark reference answers or rubric text leak into harness components.

    Raises IntegrityError if any case's reference answer (or string leaf of length >= 8)
    or rubric criterion text appears (case-insensitive, whitespace-normalized) in any
    component text.
    """
    if not isinstance(texts, Mapping):
        raise ValidationError("texts must be a mapping of component -> prompt text")

    normalized_components = {
        comp: _normalize(text)
        for comp, text in texts.items()
        if isinstance(text, str)
    }

    for case in cases:
        targets: list[str] = []
        ref = case.evaluation.reference_answer
        if isinstance(ref, str):
            if ref.strip():
                targets.append(ref)
        elif ref is not None:
            dumped = json.dumps(ref, sort_keys=True)
            if dumped.strip():
                targets.append(dumped)
            compact = json.dumps(ref, sort_keys=True, separators=(",", ":"))
            if compact.strip() and compact != dumped:
                targets.append(compact)
            targets.extend(_string_leaves(ref, min_length=8))

        for criterion in case.evaluation.rubric:
            crit_text = criterion.criterion.strip()
            if not crit_text:
                continue
            if case.evaluation.method != "rubric" and crit_text.casefold() in {
                "valid json",
                "valid exact json",
                "parses as json array",
            }:
                continue
            targets.append(crit_text)

        for target in targets:
            norm_target = _normalize(target)
            if not norm_target:
                continue
            for comp, norm_text in normalized_components.items():
                if norm_target in norm_text:
                    raise IntegrityError(
                        f"Oracle contamination detected in component '{comp}': "
                        f"found reference or rubric target {target!r} from case {case.case_id}"
                    )
