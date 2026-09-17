"""Versioned Promptfoo boundary for candidate-only offline fixtures.

The adapter never invokes Promptfoo implicitly.  Exported manifests contain only
candidate data; imported artifacts are checked against that manifest before they
can become normalized attempts.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from .isolation import AuthorizedLiveExecution
from pathlib import Path
import re
from typing import Any, Callable, Iterable, Mapping

from .isolation import assert_candidate_safe
from .schemas import canonical_record

MANIFEST_TYPE = "model_lab.promptfoo_manifest"
RESULT_TYPE = "model_lab.promptfoo_result"
ARTIFACT_VERSION = 1
_SAFE_FILENAME = re.compile(r"[^A-Za-z0-9_.-]+")


class PromptfooImportError(ValueError):
    """Raised when a fixture cannot be reconciled to an exported manifest."""


def _hash(value: Any) -> str:
    return hashlib.sha256(canonical_record(value).encode("utf-8")).hexdigest()


def _candidate(value: Any) -> dict[str, Any]:
    if hasattr(value, "candidate_payload"):
        payload = value.candidate_payload()
    elif hasattr(value, "to_dict") and not isinstance(value, Mapping):
        payload = value.to_dict()
    else:
        payload = dict(value)
    assert_candidate_safe(payload)
    return {
        "case_id": payload["case_id"],
        "messages": [dict(message) for message in payload["messages"]],
        "limits": dict(payload["limits"]),
        "prompt_hash": payload["prompt_hash"],
    }


def export_promptfoo_manifest(candidate_cases: Iterable[Any], *, run_id: str, provider: str | None = None, model: str | None = None) -> dict[str, Any]:
    """Create a stable Promptfoo-shaped manifest from candidate projections."""
    cases = sorted((_candidate(item) for item in candidate_cases), key=lambda item: item["case_id"])
    ids = [item["case_id"] for item in cases]
    if len(ids) != len(set(ids)):
        raise PromptfooImportError("duplicate case IDs in candidate manifest")
    tests = [
        {
            "vars": {
                "case_id": item["case_id"],
                "messages_json": json.dumps(item["messages"], ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                "limits": item["limits"],
            },
            "metadata": {"case_id": item["case_id"], "prompt_hash": item["prompt_hash"]},
        }
        for item in cases
    ]
    manifest = {
        "artifact_type": MANIFEST_TYPE,
        "artifact_version": ARTIFACT_VERSION,
        "run_id": run_id,
        "prompt_hash_algorithm": "sha256",
        "prompts": ["{{messages_json}}"],
        "tests": tests,
    }
    if provider is not None or model is not None:
        manifest["candidate"] = {key: value for key, value in (("provider", provider), ("model", model)) if value is not None}
    manifest["manifest_hash"] = _hash(manifest)
    return manifest


def _manifest_cases(manifest: Mapping[str, Any]) -> dict[str, dict[str, str]]:
    if manifest.get("artifact_type") != MANIFEST_TYPE or manifest.get("artifact_version") != ARTIFACT_VERSION:
        raise PromptfooImportError("unsupported or malformed Promptfoo manifest")
    expected_hash = manifest.get("manifest_hash")
    without_hash = {key: value for key, value in manifest.items() if key != "manifest_hash"}
    if not isinstance(expected_hash, str) or expected_hash != _hash(without_hash):
        raise PromptfooImportError("manifest hash mismatch")
    tests = manifest.get("tests")
    if not isinstance(tests, list) or not tests:
        raise PromptfooImportError("manifest tests must be a non-empty list")
    cases: dict[str, dict[str, str]] = {}
    for item in tests:
        if not isinstance(item, Mapping) or not isinstance(item.get("metadata"), Mapping):
            raise PromptfooImportError("manifest test metadata is invalid")
        metadata = item["metadata"]
        case_id, prompt_hash = metadata.get("case_id"), metadata.get("prompt_hash")
        if not isinstance(case_id, str) or not isinstance(prompt_hash, str) or case_id in cases:
            raise PromptfooImportError("manifest contains invalid or duplicate case metadata")
        cases[case_id] = {"prompt_hash": prompt_hash}
    return cases


@dataclass(frozen=True)
class PromptfooImportResult:
    accepted: bool
    attempts: tuple[dict[str, Any], ...]
    errors: tuple[str, ...]
    source_hash: str
    quarantine_path: Path | None = None


def _load_artifact(source: Mapping[str, Any] | str | Path) -> tuple[dict[str, Any], str, str | None]:
    if isinstance(source, Mapping):
        value = dict(source)
        raw = canonical_record(value)
        return value, hashlib.sha256(raw.encode("utf-8")).hexdigest(), None
    path = Path(source)
    try:
        raw_text = path.read_text(encoding="utf-8")
        value = json.loads(raw_text)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PromptfooImportError(f"cannot read Promptfoo fixture: {exc}") from exc
    if not isinstance(value, dict):
        raise PromptfooImportError("Promptfoo fixture must be a JSON object")
    return value, hashlib.sha256(raw_text.encode("utf-8")).hexdigest(), str(path)


def _quarantine(value: Mapping[str, Any], source_hash: str, quarantine_dir: str | Path | None) -> Path | None:
    if quarantine_dir is None:
        return None
    directory = Path(quarantine_dir)
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / f"promptfoo-{_SAFE_FILENAME.sub('_', source_hash)}.json"
    if not destination.exists():
        destination.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return destination


def import_promptfoo_fixture(source: Mapping[str, Any] | str | Path, manifest: Mapping[str, Any], *, quarantine_dir: str | Path | None = None) -> PromptfooImportResult:
    """Validate and normalize a versioned local fixture; quarantine failures."""
    expected_cases = _manifest_cases(manifest)
    value, source_hash, source_path = _load_artifact(source)
    errors: list[str] = []
    if value.get("artifact_type") != RESULT_TYPE:
        errors.append("unsupported Promptfoo result artifact type")
    if value.get("artifact_version") != ARTIFACT_VERSION:
        errors.append("unsupported Promptfoo result artifact version")
    if value.get("manifest_hash") != manifest.get("manifest_hash"):
        errors.append("result manifest hash mismatch")
    results = value.get("results")
    if not isinstance(results, list):
        errors.append("result artifact results must be a list")
        results = []
    seen: set[str] = set()
    attempts: list[dict[str, Any]] = []
    for index, result in enumerate(results):
        if not isinstance(result, Mapping):
            errors.append(f"result {index} is not an object")
            continue
        case_id, prompt_hash = result.get("case_id"), result.get("prompt_hash")
        if not isinstance(case_id, str):
            errors.append(f"result {index} has no case_id")
            continue
        if case_id not in expected_cases:
            errors.append(f"unknown case ID: {case_id}")
            continue
        if case_id in seen:
            errors.append(f"duplicate case ID: {case_id}")
            continue
        seen.add(case_id)
        if prompt_hash != expected_cases[case_id]["prompt_hash"]:
            errors.append(f"prompt hash mismatch: {case_id}")
            continue
        output = result.get("output", result.get("response_text"))
        if output is not None and not isinstance(output, str):
            errors.append(f"output must be text or null: {case_id}")
            continue
        attempts.append({
            "attempt_id": f"promptfoo-{source_hash[:16]}-{case_id}",
            "logical_request_id": case_id,
            "case_id": case_id,
            "prompt_hash": prompt_hash,
            "response_text": output,
            "status": result.get("status", "success"),
            "provider": result.get("provider"),
            "model": result.get("model"),
            "latency_ms": result.get("latency_ms"),
            "input_tokens": result.get("input_tokens"),
            "output_tokens": result.get("output_tokens"),
            "cost_minor": result.get("cost_minor"),
            "raw_metadata": {"source_type": "promptfoo_fixture", "source_hash": source_hash, "source_path": source_path},
        })
    missing = sorted(set(expected_cases) - seen)
    errors.extend(f"missing result for case ID: {case_id}" for case_id in missing)
    if errors:
        quarantine_path = _quarantine(value, source_hash, quarantine_dir)
        return PromptfooImportResult(False, tuple(), tuple(errors), source_hash, quarantine_path)
    return PromptfooImportResult(True, tuple(attempts), tuple(), source_hash)


def invoke_promptfoo(manifest: Mapping[str, Any], *, capability: AuthorizedLiveExecution, runner: Callable[[Mapping[str, Any]], Any] | None = None) -> Any:
    """Invoke only through an explicitly approved, injected runner.

    This intentionally has no subprocess fallback: CI and offline operation must
    not be able to launch an unbudgeted live provider or Promptfoo command.
    """
    _manifest_cases(manifest)
    if not isinstance(capability, AuthorizedLiveExecution) or not capability._authorized_by:
        raise PromptfooImportError("live Promptfoo invocation requires an approved plan")
    if runner is None:
        raise PromptfooImportError("live Promptfoo invocation requires an approved runner")
    return runner(manifest)


export_manifest = export_promptfoo_manifest
import_fixture = import_promptfoo_fixture
