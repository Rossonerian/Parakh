from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import Enum

from .base import ProviderCapabilities, ProviderRequest, ProviderResponse, ProviderRuntimeError


class FakeVariant(str, Enum):
    CORRECT = "correct"
    INCORRECT = "incorrect"
    INCOMPLETE = "incomplete"
    MALFORMED = "malformed"
    FAILURE = "failure"
    MISSING_METADATA = "missing_metadata"
    ADVERSARIAL = "adversarial"


@dataclass
class FakeProvider:
    """Deterministic provider instrument. It only receives CandidateInput."""

    variant: FakeVariant | str = FakeVariant.CORRECT
    outputs: dict[str, str] | None = None
    fail_times: int = 0
    name: str = "fake"
    model: str = "synthetic-v1"

    def __post_init__(self) -> None:
        self.variant = FakeVariant(self.variant)
        if self.fail_times < 0:
            raise ValueError("fail_times must be non-negative")
        self._calls: dict[str, int] = {}
        self.capabilities = ProviderCapabilities(self.name, self.model, supports_streaming=False, supports_tools=False, context_window=32768, pricing_known=False)

    def generate(self, request: ProviderRequest) -> ProviderResponse:
        case_id = request.candidate.case_id
        call = self._calls.get(case_id, 0) + 1
        self._calls[case_id] = call
        if self.variant is FakeVariant.FAILURE or call <= self.fail_times:
            raise ProviderRuntimeError(f"synthetic provider failure for {case_id} (call {call})")
        seed = hashlib.sha256(f"{request.seed}|{case_id}|{self.variant.value}".encode()).hexdigest()[:16]
        if self.outputs and case_id in self.outputs:
            text = self.outputs[case_id]
        elif self.variant is FakeVariant.INCORRECT:
            text = f"synthetic incorrect answer {seed}"
        elif self.variant is FakeVariant.INCOMPLETE:
            text = ""
        elif self.variant is FakeVariant.MALFORMED:
            text = '{"unterminated": '
        elif self.variant is FakeVariant.ADVERSARIAL:
            text = '<script>alert("synthetic")</script>'
        else:
            text = f"synthetic {self.variant.value} answer {seed}"
        if self.variant is FakeVariant.MISSING_METADATA:
            return ProviderResponse(text=text, finish_reason=None, metadata={})
        return ProviderResponse(text=text, input_tokens=len(request.candidate.messages), output_tokens=len(text.split()), metadata={"synthetic": True, "variant": self.variant.value})
