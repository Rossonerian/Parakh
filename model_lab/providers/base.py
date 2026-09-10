from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from ..isolation import CandidateInput


class ProviderError(Exception):
    """Base provider failure."""


class ProviderConfigurationError(ProviderError):
    """Provider cannot run safely with the supplied configuration."""


class ProviderRuntimeError(ProviderError):
    """Provider failed during a request."""


@dataclass(frozen=True)
class ProviderCapabilities:
    provider: str
    model: str
    supports_streaming: bool = False
    supports_tools: bool = False
    context_window: int | None = None
    pricing_known: bool = False


@dataclass(frozen=True)
class ProviderRequest:
    candidate: CandidateInput
    model: str
    parameters: dict[str, object] = field(default_factory=dict)
    timeout_seconds: float | None = None
    seed: int | None = None


@dataclass(frozen=True)
class ProviderResponse:
    text: str | None
    finish_reason: str | None = "stop"
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_minor: int | None = None
    currency: str | None = None
    first_token_latency_ms: float | None = None
    completion_latency_ms: float | None = None
    metadata: dict[str, object] = field(default_factory=dict)


class Provider(Protocol):
    name: str
    capabilities: ProviderCapabilities

    def generate(self, request: ProviderRequest) -> ProviderResponse:
        ...
