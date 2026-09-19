import json

import pytest

from model_lab.isolation import candidate_input
from model_lab.providers import OllamaProvider, OpenRouterProvider, ProviderConfigurationError, ProviderRequest, ProviderRuntimeError
from model_lab.benchmark import load_suite


ROOT = __import__("pathlib").Path(__file__).parents[1]


def test_live_providers_fail_closed_without_credentials():
    case = load_suite(ROOT / "benchmarks/seed_cases.jsonl").cases[0]
    request = ProviderRequest(candidate_input(case), "openai/gpt-4.1", timeout_seconds=1)
    with pytest.raises(ProviderConfigurationError):
        OllamaProvider("llama3", env={}).generate(request)
    with pytest.raises(ProviderConfigurationError):
        OpenRouterProvider("openai/gpt-4.1", env={}).generate(request)


def test_model_namespaces_are_validated_without_being_local_ids():
    case = load_suite(ROOT / "benchmarks/seed_cases.jsonl").cases[0]
    request = ProviderRequest(candidate_input(case), "openai/gpt-4.1", timeout_seconds=1)
    assert request.model == "openai/gpt-4.1"


def test_live_providers_reject_invalid_url_schemes():
    case = load_suite(ROOT / "benchmarks/seed_cases.jsonl").cases[0]
    request = ProviderRequest(candidate_input(case), "ollama/llama3", timeout_seconds=1)
    ollama = OllamaProvider("llama3", env={"MODELLAB_OLLAMA_ENDPOINT": "file:///etc/passwd"})
    with pytest.raises(ProviderRuntimeError, match="unsupported or invalid URL scheme 'file'"):
        ollama.generate(request)

    openrouter = OpenRouterProvider("openai/gpt-4.1", env={"OPENROUTER_API_KEY": "test-key", "MODELLAB_OPENROUTER_ENDPOINT": "ftp://example.com/api"})
    with pytest.raises(ProviderRuntimeError, match="unsupported or invalid URL scheme 'ftp'"):
        openrouter.generate(request)
