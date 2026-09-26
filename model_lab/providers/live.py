"""Optional HTTP adapters for Ollama and OpenRouter.

These adapters are never selected by the offline demo. They use the standard
library, require explicit environment configuration, bound request timeouts,
and preserve provider-reported usage without inventing pricing.
"""

from __future__ import annotations

import json
import math
import os
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .base import ProviderCapabilities, ProviderConfigurationError, ProviderRequest, ProviderResponse, ProviderRuntimeError


DEFAULT_TIMEOUT_SECONDS = 60.0
MAX_TIMEOUT_SECONDS = 120.0
MAX_RESPONSE_BYTES = 8 * 1024 * 1024
_PROTECTED_PARAMETERS = frozenset({"model", "messages", "stream", "prompt", "tools", "functions", "tool_choice", "plugins", "web_search_options"})
_OLLAMA_PARAMETERS = frozenset({"temperature", "top_p", "top_k", "num_predict", "seed", "stop", "repeat_penalty", "presence_penalty", "frequency_penalty"})
_OPENROUTER_PARAMETERS = frozenset({"temperature", "top_p", "top_k", "max_tokens", "max_completion_tokens", "frequency_penalty", "presence_penalty", "repetition_penalty", "stop", "response_format"})


class _RejectRedirects(HTTPRedirectHandler):
    def redirect_request(self, req: Request, fp: Any, code: int, msg: str, headers: Any, newurl: str) -> None:
        raise ProviderRuntimeError("provider redirect rejected; endpoint must be final", retryable=False)


def _messages(request: ProviderRequest) -> list[dict[str, str]]:
    return [dict(message) for message in request.candidate.messages]


def _timeout(value: float | None) -> float:
    if value is None:
        return DEFAULT_TIMEOUT_SECONDS
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        raise ProviderConfigurationError("provider timeout must be a finite positive number")
    if value > MAX_TIMEOUT_SECONDS:
        raise ProviderConfigurationError(f"provider timeout exceeds maximum of {MAX_TIMEOUT_SECONDS:g} seconds")
    return float(value)


def _validate_endpoint(url: str, *, provider: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ProviderRuntimeError(f"unsupported or invalid URL scheme '{parsed.scheme}': only http and https are allowed", retryable=False)
    if not parsed.hostname:
        raise ProviderConfigurationError("unsupported or invalid provider endpoint")
    if parsed.username or parsed.password:
        raise ProviderConfigurationError("provider endpoint must not contain embedded credentials")
    if parsed.fragment or parsed.query:
        raise ProviderConfigurationError("provider endpoint must not contain a query or fragment")
    # OpenRouter carries a bearer key and must always use encrypted transport.
    if provider == "openrouter" and parsed.scheme != "https":
        raise ProviderConfigurationError("openrouter endpoint must use https")
    return url.rstrip("/")


def _json_safe(value: Any, path: str = "parameters") -> Any:
    if value is None or isinstance(value, (bool, str, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ProviderConfigurationError(f"{path} must contain finite JSON numbers")
        return value
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item, f"{path}.{key}") for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item, f"{path}[{index}]") for index, item in enumerate(value)]
    raise ProviderConfigurationError(f"{path} contains unsupported JSON value")


def _safe_parameters(parameters: Mapping[str, Any], allowed: frozenset[str]) -> dict[str, Any]:
    forbidden = _PROTECTED_PARAMETERS.intersection(parameters)
    if forbidden:
        raise ProviderConfigurationError(f"provider parameters cannot override protected fields: {', '.join(sorted(forbidden))}")
    unknown = set(parameters).difference(allowed)
    if unknown:
        raise ProviderConfigurationError(f"unsupported provider parameters: {', '.join(sorted(unknown))}")
    checked = _json_safe(parameters)
    for key in ("num_predict", "max_tokens", "max_completion_tokens"):
        if key in checked and (isinstance(checked[key], bool) or not isinstance(checked[key], int) or checked[key] <= 0):
            raise ProviderConfigurationError(f"{key} must be a positive integer")
    return checked


def _model_matches(request_model: str, provider: str, configured_model: str) -> bool:
    # ModelLab candidate identifiers commonly use provider:model while the
    # adapter receives the provider-native model id.
    return request_model in {configured_model, f"{provider}/{configured_model}"}


def _validated_seed(seed: int | None) -> int | None:
    if seed is None:
        return None
    if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
        raise ProviderConfigurationError("seed must be a nonnegative integer")
    return seed


def _nonnegative_int(value: Any, field: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ProviderRuntimeError(f"provider returned invalid numeric field: {field}", retryable=False)
    return value


def _reported_cost(value: Any) -> int | float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise ProviderRuntimeError("provider returned invalid numeric field: cost", retryable=False)
    return value


def _post_json(url: str, payload: Mapping[str, Any], headers: Mapping[str, str], timeout: float | None) -> dict[str, Any]:
    _validate_endpoint(url, provider="openrouter" if "Authorization" in headers else "ollama")
    bounded_timeout = _timeout(timeout)
    body = json.dumps(_json_safe(payload, "payload"), ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
    request = Request(url, data=body, headers={"Content-Type": "application/json", **headers}, method="POST")
    try:
        opener = build_opener(_RejectRedirects)
        with opener.open(request, timeout=bounded_timeout) as response:  # nosec B310 - endpoint is validated operator configuration
            raw = response.read(MAX_RESPONSE_BYTES + 1)
            if len(raw) > MAX_RESPONSE_BYTES:
                raise ProviderRuntimeError("provider response exceeds maximum size", retryable=False)
            value = json.loads(raw.decode("utf-8"))
    except HTTPError as exc:
        retryable = exc.code == 429 or 500 <= exc.code <= 599
        raise ProviderRuntimeError(f"provider HTTP error {exc.code}", retryable=retryable) from exc
    except ProviderRuntimeError:
        raise
    except (URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        raise ProviderRuntimeError(f"provider request failed: {exc.__class__.__name__}") from exc
    if not isinstance(value, dict):
        raise ProviderRuntimeError("provider returned a non-object JSON response", retryable=False)
    return value


class OllamaProvider:
    name = "ollama"

    def __init__(self, model: str, *, env: dict[str, str] | None = None) -> None:
        self.model = model
        self._env = os.environ if env is None else env
        configured = self._env.get("MODELLAB_OLLAMA_ENDPOINT", "")
        self.endpoint = configured.rstrip("/")
        self.capabilities = ProviderCapabilities(self.name, model, supports_streaming=False, supports_tools=False, context_window=None, pricing_known=False)

    def generate(self, request: ProviderRequest) -> ProviderResponse:
        if not self.endpoint:
            raise ProviderConfigurationError("ollama disabled: missing MODELLAB_OLLAMA_ENDPOINT")
        _validate_endpoint(self.endpoint, provider=self.name)
        payload: dict[str, Any] = {"model": self.model, "messages": _messages(request), "stream": False}
        if not _model_matches(request.model, self.name, self.model):
            raise ProviderConfigurationError("request model does not match configured Ollama model")
        parameters = _safe_parameters(request.parameters, _OLLAMA_PARAMETERS)
        seed = _validated_seed(request.seed)
        if seed is not None:
            parameters.setdefault("seed", seed)
        if parameters:
            payload["options"] = parameters
        response = _post_json(f"{self.endpoint}/api/chat", payload, {}, request.timeout_seconds)
        message = response.get("message")
        if not isinstance(message, dict) or not isinstance(message.get("content"), str):
            raise ProviderRuntimeError("ollama response is missing message.content", retryable=False)
        if response.get("done") is not True:
            raise ProviderRuntimeError("ollama response is not complete", retryable=False)
        if response.get("done_reason") in {"length", "limit"}:
            raise ProviderRuntimeError("ollama response was truncated", retryable=False)
        return ProviderResponse(
            text=message["content"], finish_reason=response.get("done_reason"),
            input_tokens=_nonnegative_int(response.get("prompt_eval_count"), "prompt_eval_count"),
            output_tokens=_nonnegative_int(response.get("eval_count"), "eval_count"),
            metadata={"provider": self.name, "model": self.model, "request_model": request.model, "provider_model": response.get("model"), "provider_response_id": response.get("id"), "provider_reported": True, "done": response.get("done"), "done_reason": response.get("done_reason"), "request_parameters": parameters},
        )


class OpenRouterProvider:
    name = "openrouter"

    def __init__(self, model: str, *, env: dict[str, str] | None = None) -> None:
        self.model = model
        self._env = os.environ if env is None else env
        configured = self._env.get("MODELLAB_OPENROUTER_ENDPOINT", "https://openrouter.ai/api/v1/chat/completions")
        self.endpoint = configured.rstrip("/")
        self.capabilities = ProviderCapabilities(self.name, model, supports_streaming=False, supports_tools=False, context_window=None, pricing_known=False)

    def generate(self, request: ProviderRequest) -> ProviderResponse:
        key = self._env.get("OPENROUTER_API_KEY")
        if not key:
            raise ProviderConfigurationError("openrouter disabled: missing OPENROUTER_API_KEY")
        _validate_endpoint(self.endpoint, provider=self.name)
        if not _model_matches(request.model, self.name, self.model):
            raise ProviderConfigurationError("request model does not match configured OpenRouter model")
        payload: dict[str, Any] = {"model": self.model, "messages": _messages(request)}
        parameters = _safe_parameters(request.parameters, _OPENROUTER_PARAMETERS)
        payload.update(parameters)
        seed = _validated_seed(request.seed)
        if seed is not None:
            payload.setdefault("seed", seed)
        headers = {"Authorization": f"Bearer {key}"}
        if self._env.get("MODELLAB_HTTP_REFERER"):
            headers["HTTP-Referer"] = self._env["MODELLAB_HTTP_REFERER"]
        if self._env.get("MODELLAB_APP_TITLE"):
            headers["X-Title"] = self._env["MODELLAB_APP_TITLE"]
        response = _post_json(self.endpoint, payload, headers, request.timeout_seconds)
        choices = response.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            raise ProviderRuntimeError("openrouter response is missing choices[0]", retryable=False)
        choice = choices[0]
        message = choice.get("message")
        if not isinstance(message, dict) or not isinstance(message.get("content"), str):
            raise ProviderRuntimeError("openrouter response is missing choices[0].message.content", retryable=False)
        finish_reason = choice.get("finish_reason")
        if not isinstance(finish_reason, str) or not finish_reason:
            raise ProviderRuntimeError("openrouter response is missing finish_reason", retryable=False)
        if finish_reason in {"length", "max_tokens"}:
            raise ProviderRuntimeError("openrouter response was truncated", retryable=False)
        raw_usage = response.get("usage")
        if raw_usage is not None and not isinstance(raw_usage, dict):
            raise ProviderRuntimeError("openrouter response usage must be an object", retryable=False)
        usage = raw_usage or {}
        return ProviderResponse(
            text=message["content"], finish_reason=finish_reason,
            input_tokens=_nonnegative_int(usage.get("prompt_tokens"), "prompt_tokens"),
            output_tokens=_nonnegative_int(usage.get("completion_tokens"), "completion_tokens"),
            metadata={"provider": self.name, "model": self.model, "request_model": request.model, "provider_model": response.get("model"), "provider_response_id": response.get("id"), "request_id": response.get("id"), "system_fingerprint": response.get("system_fingerprint"), "provider_reported": True, "provider_usage": dict(usage), "provider_cost": _reported_cost(usage.get("cost")), "request_parameters": {**parameters, **({"seed": seed} if seed is not None else {})}},
        )
