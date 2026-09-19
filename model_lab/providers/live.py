"""Optional HTTP adapters for Ollama and OpenRouter.

These adapters are never selected by the offline demo. They use the standard
library, require explicit environment configuration, bound request timeouts,
and preserve provider-reported usage without inventing pricing.
"""

from __future__ import annotations

import json
import os
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from .base import ProviderCapabilities, ProviderConfigurationError, ProviderRequest, ProviderResponse, ProviderRuntimeError


def _messages(request: ProviderRequest) -> list[dict[str, str]]:
    return [dict(message) for message in request.candidate.messages]


def _post_json(url: str, payload: Mapping[str, Any], headers: Mapping[str, str], timeout: float | None) -> dict[str, Any]:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ProviderRuntimeError(f"unsupported or invalid URL scheme '{parsed.scheme}': only http and https are allowed")
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    request = Request(url, data=body, headers={"Content-Type": "application/json", **headers}, method="POST")
    try:
        with urlopen(request, timeout=timeout or 60.0) as response:  # nosec B310 - endpoint is explicit operator configuration
            value = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise ProviderRuntimeError(f"provider HTTP error {exc.code}") from exc
    except (URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        raise ProviderRuntimeError(f"provider request failed: {exc.__class__.__name__}") from exc
    if not isinstance(value, dict):
        raise ProviderRuntimeError("provider returned a non-object JSON response")
    return value


class OllamaProvider:
    name = "ollama"

    def __init__(self, model: str, *, env: dict[str, str] | None = None) -> None:
        self.model = model
        self._env = os.environ if env is None else env
        self.endpoint = self._env.get("MODELLAB_OLLAMA_ENDPOINT", "").rstrip("/")
        self.capabilities = ProviderCapabilities(self.name, model, supports_streaming=False, supports_tools=False, context_window=None, pricing_known=False)

    def generate(self, request: ProviderRequest) -> ProviderResponse:
        if not self.endpoint:
            raise ProviderConfigurationError("ollama disabled: missing MODELLAB_OLLAMA_ENDPOINT")
        payload: dict[str, Any] = {"model": self.model, "messages": _messages(request), "stream": False}
        if request.parameters:
            payload["options"] = dict(request.parameters)
        response = _post_json(f"{self.endpoint}/api/chat", payload, {}, request.timeout_seconds)
        message = response.get("message")
        if not isinstance(message, dict) or not isinstance(message.get("content"), str):
            raise ProviderRuntimeError("ollama response is missing message.content")
        return ProviderResponse(
            text=message["content"], finish_reason=response.get("done_reason"),
            input_tokens=response.get("prompt_eval_count"), output_tokens=response.get("eval_count"),
            metadata={"provider_reported": True, "done": response.get("done")},
        )


class OpenRouterProvider:
    name = "openrouter"

    def __init__(self, model: str, *, env: dict[str, str] | None = None) -> None:
        self.model = model
        self._env = os.environ if env is None else env
        self.endpoint = self._env.get("MODELLAB_OPENROUTER_ENDPOINT", "https://openrouter.ai/api/v1/chat/completions")
        self.capabilities = ProviderCapabilities(self.name, model, supports_streaming=False, supports_tools=False, context_window=None, pricing_known=False)

    def generate(self, request: ProviderRequest) -> ProviderResponse:
        key = self._env.get("OPENROUTER_API_KEY")
        if not key:
            raise ProviderConfigurationError("openrouter disabled: missing OPENROUTER_API_KEY")
        payload: dict[str, Any] = {"model": self.model, "messages": _messages(request)}
        payload.update(request.parameters)
        if request.seed is not None:
            payload.setdefault("seed", request.seed)
        headers = {"Authorization": f"Bearer {key}"}
        if self._env.get("MODELLAB_HTTP_REFERER"):
            headers["HTTP-Referer"] = self._env["MODELLAB_HTTP_REFERER"]
        if self._env.get("MODELLAB_APP_TITLE"):
            headers["X-Title"] = self._env["MODELLAB_APP_TITLE"]
        response = _post_json(self.endpoint, payload, headers, request.timeout_seconds)
        choices = response.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            raise ProviderRuntimeError("openrouter response is missing choices[0]")
        choice = choices[0]
        message = choice.get("message")
        if not isinstance(message, dict) or not isinstance(message.get("content"), str):
            raise ProviderRuntimeError("openrouter response is missing choices[0].message.content")
        usage = response.get("usage") if isinstance(response.get("usage"), dict) else {}
        return ProviderResponse(
            text=message["content"], finish_reason=choice.get("finish_reason"),
            input_tokens=usage.get("prompt_tokens"), output_tokens=usage.get("completion_tokens"),
            metadata={"provider_reported": True, "provider_usage": usage.get("cost") if "cost" in usage else None},
        )
