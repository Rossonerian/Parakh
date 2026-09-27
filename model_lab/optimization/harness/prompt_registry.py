"""Immutable, content-addressed harness prompt versions and registry.

Prompt versions are content-addressed by their component, text, and parent_id,
and are stored in append-only evidence storage under the kind 'harness_prompts'.
There is no update, delete, or production-override API.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from model_lab.errors import ValidationError
from model_lab.schemas import freeze_json, require_text, stable_hash, utc_now
from model_lab.storage.evidence import EvidenceStore

COMPONENTS: tuple[str, ...] = (
    "system",
    "tool_description",
    "tool_selection",
    "context_compression",
    "recovery",
    "retry",
    "few_shot",
    "planning",
    "state_serialization",
)

DEFAULT_BASELINE_PATH = Path(__file__).resolve().parent / "baseline_harness.json"


def prompt_digest(component: str, text: str, parent_id: str | None) -> str:
    """Generate the content-addressed identifier for a prompt version."""
    payload = {"component": component, "parent_id": parent_id, "text": text}
    return "prm-" + stable_hash(payload)[:16]


@dataclass(frozen=True)
class PromptVersion:
    """Frozen, content-addressed prompt record."""

    prompt_id: str
    component: str
    text: str
    parent_id: str | None
    generation_method: str
    created_at: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.component not in COMPONENTS:
            raise ValidationError(f"unknown component: {self.component}; must be one of {COMPONENTS}")
        require_text(self.text, "prompt text")
        require_text(self.generation_method, "generation_method")
        require_text(self.created_at, "created_at")
        expected_id = prompt_digest(self.component, self.text, self.parent_id)
        if self.prompt_id != expected_id:
            object.__setattr__(self, "prompt_id", expected_id)
        object.__setattr__(self, "metadata", freeze_json(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        return {
            "prompt_id": self.prompt_id,
            "component": self.component,
            "text": self.text,
            "parent_id": self.parent_id,
            "generation_method": self.generation_method,
            "created_at": self.created_at,
            "metadata": dict(self.metadata),
        }


class PromptRegistry:
    """Append-only registry for immutable prompt versions over an EvidenceStore."""

    def __init__(self, evidence: EvidenceStore) -> None:
        self.evidence = evidence

    def register(
        self,
        component: str,
        text: str,
        *,
        parent_id: str | None = None,
        generation_method: str = "manual",
        metadata: Mapping[str, Any] | None = None,
    ) -> PromptVersion:
        """Register a prompt version. Idempotent on identical content."""
        if component not in COMPONENTS:
            raise ValidationError(f"unknown component: {component}; must be one of {COMPONENTS}")
        require_text(text, "prompt text")
        p_id = prompt_digest(component, text, parent_id)
        meta_dict = dict(metadata or {})

        if self.evidence.exists("harness_prompts", p_id):
            existing = self.evidence.get("harness_prompts", p_id)
            return self._from_record(existing)

        now = utc_now()
        record = {
            "prompt_id": p_id,
            "component": component,
            "text": text,
            "parent_id": parent_id,
            "generation_method": generation_method,
            "created_at": now,
            "metadata": meta_dict,
        }
        self.evidence.append("harness_prompts", p_id, record, created_at=now)
        return self._from_record(record)

    def get(self, prompt_id: str) -> PromptVersion:
        """Retrieve a prompt version by its ID."""
        record = self.evidence.get("harness_prompts", prompt_id)
        return self._from_record(record)

    def lineage(self, prompt_id: str) -> list[PromptVersion]:
        """Return the ancestor chain of prompt versions, root first."""
        chain: list[PromptVersion] = []
        current_id: str | None = prompt_id
        seen: set[str] = set()

        while current_id is not None:
            if current_id in seen:
                break
            seen.add(current_id)
            version = self.get(current_id)
            chain.append(version)
            current_id = version.parent_id

        chain.reverse()
        return chain

    def load_baseline(self, path: str | Path | None = None) -> dict[str, PromptVersion]:
        """Register baseline components from baseline_harness.json."""
        target_path = Path(path) if path is not None else DEFAULT_BASELINE_PATH
        data = json.loads(target_path.read_text(encoding="utf-8"))
        components = data.get("components", {})
        registered: dict[str, PromptVersion] = {}
        for comp, text in components.items():
            version = self.register(comp, text, parent_id=None, generation_method="baseline")
            registered[comp] = version
        return registered

    @staticmethod
    def _from_record(record: Mapping[str, Any]) -> PromptVersion:
        return PromptVersion(
            prompt_id=record["prompt_id"],
            component=record["component"],
            text=record["text"],
            parent_id=record.get("parent_id"),
            generation_method=record.get("generation_method", "manual"),
            created_at=record.get("created_at", utc_now()),
            metadata=dict(record.get("metadata", {})),
        )
