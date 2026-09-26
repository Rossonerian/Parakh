import json

import pytest

from model_lab.domain.isolation import candidate_input
from model_lab.providers import OpenRouterProvider, ProviderConfigurationError, ProviderRequest, ProviderRuntimeError
from model_lab.benchmark import load_suite


ROOT = __import__("pathlib").Path(__file__).parents[1]


class _Response:
    def __init__(self, value):
        self.body = json.dumps(value).encode()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self, limit=-1):
        return self.body if limit < 0 else self.body[:limit]


def _request(model="openai/gpt-4.1", **kwargs):
    case = load_suite(ROOT / "benchmarks/seed_cases.jsonl").cases[0]
    return ProviderRequest(candidate_input(case), model, **kwargs)


def test_openrouter_keeps_identity_and_rejects_protected_parameter_override(monkeypatch):
    provider = OpenRouterProvider("openai/gpt-4.1", env={"OPENROUTER_API_KEY": "secret"})
    with pytest.raises(ProviderConfigurationError, match="protected fields"):
        provider.generate(_request(parameters={"model": "other-model"}))


def test_openrouter_rejects_redirects_without_replaying_bearer(monkeypatch):
    provider = OpenRouterProvider("openai/gpt-4.1", env={"OPENROUTER_API_KEY": "secret"})

    def fake_open(self, request, timeout):
        assert request.get_header("Authorization") == "Bearer secret"
        raise ProviderRuntimeError("provider redirect rejected; endpoint must be final", retryable=False)

    monkeypatch.setattr("model_lab.providers.live._RejectRedirects.redirect_request", lambda *args: (_ for _ in ()).throw(ProviderRuntimeError("provider redirect rejected; endpoint must be final", retryable=False)))
    monkeypatch.setattr("model_lab.providers.live.build_opener", lambda *_: type("Opener", (), {"open": fake_open})())
    with pytest.raises(ProviderRuntimeError, match="redirect rejected") as error:
        provider.generate(_request(timeout_seconds=1))
    assert error.value.retryable is False


def test_openrouter_preserves_usage_and_rejects_malformed_numbers(monkeypatch):
    response = {"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}], "usage": {"prompt_tokens": 3, "completion_tokens": 2, "cost": 0.25}}
    monkeypatch.setattr("model_lab.providers.live.build_opener", lambda *_: type("Opener", (), {"open": lambda self, request, timeout: _Response(response)})())
    provider = OpenRouterProvider("openai/gpt-4.1", env={"OPENROUTER_API_KEY": "secret"})
    result = provider.generate(_request(timeout_seconds=1))
    assert (result.input_tokens, result.output_tokens) == (3, 2)
    assert result.metadata["provider"] == "openrouter"
    assert result.metadata["model"] == "openai/gpt-4.1"
    assert result.metadata["provider_usage"] == response["usage"]

    response["usage"]["prompt_tokens"] = -1
    with pytest.raises(ProviderRuntimeError, match="invalid numeric field") as error:
        provider.generate(_request(timeout_seconds=1))
    assert error.value.retryable is False


def test_timeout_is_bounded_before_transport(monkeypatch):
    provider = OpenRouterProvider("openai/gpt-4.1", env={"OPENROUTER_API_KEY": "secret"})
    with pytest.raises(ProviderConfigurationError, match="exceeds maximum"):
        provider.generate(_request(timeout_seconds=121))
