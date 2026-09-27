"""Deterministic prompt-sensitive simulated provider and task builder.

This module provides a deterministic provider environment (labelled SIMULATED)
that tests whether harness candidate prompts contain required phrases for specific
tasks or domains.

Phrase Map Specification:
- Domain phrases take precedence for specific domains:
    - 'expenses' -> 'calculate financial amounts accurately'
    - 'document_extraction' -> 'extract structured data verbatim'
    - 'tabular_analysis' -> 'analyze tabular structures row by row'
    - 'task_planning' -> 'plan and order tasks sequentially'
- Evaluation method phrases apply as fallbacks:
    - 'exact_json' -> 'respond with only valid json'
    - 'exact_text' -> 'respond with exact concise text'
    - 'schema' -> 'adhere strictly to the requested schema'
- Rubric cases:
    - 'rubric' -> 'provide comprehensive and factual response'
      (deterministic graders abstain on rubric cases regardless of response).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Mapping

from model_lab.pipeline import _candidate_output
from model_lab.providers.base import ProviderCapabilities, ProviderRequest, ProviderResponse
from model_lab.schemas import Case

DOMAIN_PHRASES: dict[str, str] = {
    "expenses": "calculate financial amounts accurately",
    "document_extraction": "extract structured data verbatim",
    "tabular_analysis": "analyze tabular structures row by row",
    "task_planning": "plan and order tasks sequentially",
}

METHOD_PHRASES: dict[str, str] = {
    "exact_json": "respond with only valid json",
    "exact_text": "respond with exact concise text",
    "schema": "adhere strictly to the requested schema",
    "rubric": "provide comprehensive and factual response",
}


@dataclass
class PromptSensitiveProvider:
    """Deterministic simulated provider sensitive to harness prompt contents.

    Returns correct_text iff every required phrase in ``skills[case_id]``
    appears (case-insensitive) in the concatenated harness texts.
    Never sees or retains Case objects.
    """

    outputs: dict[str, tuple[str, str]]
    skills: dict[str, str]
    name: str = "prompt_sensitive"
    model: str = "simulated-v1"
    evidence_class: str = "SIMULATED"
    capabilities: ProviderCapabilities = field(init=False)

    def __post_init__(self) -> None:
        self.capabilities = ProviderCapabilities(
            provider=self.name,
            model=self.model,
            supports_streaming=False,
            supports_tools=False,
            context_window=32768,
            pricing_known=False,
        )

    def generate(self, request: ProviderRequest) -> ProviderResponse:
        case_id = request.candidate.case_id
        harness = request.parameters.get("harness", {})
        if not isinstance(harness, Mapping):
            harness = {}

        combined_text = " ".join(str(v) for v in harness.values()).casefold()

        required = self.skills.get(case_id, "")
        if isinstance(required, str):
            phrases = [required] if required else []
        else:
            phrases = list(required)

        matched = all(phrase.casefold() in combined_text for phrase in phrases) if phrases else True

        if case_id in self.outputs:
            correct_text, incorrect_text = self.outputs[case_id]
            chosen_text = correct_text if matched else incorrect_text
        else:
            chosen_text = "simulated correct response" if matched else "simulated incorrect response"

        return ProviderResponse(
            text=chosen_text,
            finish_reason="stop",
            input_tokens=len(request.candidate.messages),
            output_tokens=len(chosen_text.split()),
            metadata={"simulated": True, "evidence_class": self.evidence_class},
        )


def simulated_task(cases: Iterable[Case]) -> tuple[dict[str, tuple[str, str]], dict[str, str]]:
    """Build (outputs, skills) mappings for a case list without exposing cases to providers."""
    outputs: dict[str, tuple[str, str]] = {}
    skills: dict[str, str] = {}

    for case in cases:
        correct_text = _candidate_output(case, incorrect=False)
        incorrect_text = _candidate_output(case, incorrect=True)
        outputs[case.case_id] = (correct_text, incorrect_text)

        if case.domain in DOMAIN_PHRASES:
            phrase = DOMAIN_PHRASES[case.domain]
        elif case.evaluation.method in METHOD_PHRASES:
            phrase = METHOD_PHRASES[case.evaluation.method]
        else:
            phrase = "respond accurately according to instructions"
        skills[case.case_id] = phrase

    return outputs, skills
