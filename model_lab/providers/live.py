from __future__ import annotations

import os

from .base import ProviderCapabilities, ProviderConfigurationError, ProviderRequest, ProviderResponse


class _CredentialedStub:
    env_var: str
    name: str

    def __init__(self, model: str, *, env: dict[str, str] | None = None) -> None:
        self.model = model
        self._env = os.environ if env is None else env
        self.capabilities = ProviderCapabilities(self.name, model, pricing_known=False)

    def _require_credentials(self) -> None:
        if not self._env.get(self.env_var):
            raise ProviderConfigurationError(f"{self.name} disabled: missing {self.env_var}")

    def generate(self, request: ProviderRequest) -> ProviderResponse:
        self._require_credentials()
        raise ProviderConfigurationError(f"{self.name} adapter is intentionally fail-closed until its official client is configured")


class OllamaProvider(_CredentialedStub):
    name = "ollama"
    env_var = "MODELLAB_OLLAMA_ENDPOINT"


class OpenRouterProvider(_CredentialedStub):
    name = "openrouter"
    env_var = "OPENROUTER_API_KEY"
