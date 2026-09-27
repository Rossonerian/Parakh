"""Karmi-side reference loader for PolicyBundleV1 (stdlib only, imports nothing from Parakh).

This is the executable form of the contract Karmi must implement (plan K7/K12/K13):
verify signature -> checksums -> schemas -> feature schema -> model ids ->
version -> self-test -> load into a *candidate slot*. The active policy is never
touched by loading; ``PolicySlots.promote`` is an explicit operator action that
Parakh never calls. Parakh's tests use this module as the "Karmi fixture loader".
"""

from __future__ import annotations

import hashlib
import json
import math
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

try:  # package import (tests) or script-relative import (Karmi vendoring)
    from . import ed25519
except ImportError:  # pragma: no cover
    import ed25519  # type: ignore[no-redef]

SUPPORTED_ARTIFACT_MAJOR = "1"
SUPPORTED_POLICY_SCHEMAS = {"linucb.v1"}
REQUIRED_FILES = ("manifest.json", "routing_policy.json", "feature_schema.json", "eligibility_constraints.json",
                  "evaluation.json", "provenance.json")


class BundleRejected(Exception):
    """Invalid artifact: reject, keep the current policy, emit an ops event."""


def _version(value: str) -> tuple[int, ...]:
    return tuple(int(part) for part in value.split("."))


def _apply(spec: Mapping[str, Any], context: Mapping[str, Any]) -> float:
    kind = spec["transform"]
    if kind == "constant":
        return float(spec["value"])
    value = context.get(spec["source"])
    if kind == "present":
        return 0.0 if value is None else 1.0
    if value is None:
        if spec["source"] == "latency_slo_ms":
            return 0.0
        raise ValueError(f"missing feature source {spec['source']}")
    if kind == "equals":
        return 1.0 if value == spec["value"] else 0.0
    if kind == "not_in":
        return 0.0 if value in spec["values"] else 1.0
    if kind == "bool":
        if not isinstance(value, bool):
            raise ValueError(f"{spec['source']} must be boolean")
        return 1.0 if value else 0.0
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{spec['source']} must be numeric")
    if kind == "clip01":
        return min(1.0, max(0.0, float(value)))
    if kind == "capped_ratio":
        return min(1.0, max(0.0, float(value) / float(spec["cap"])))
    if kind == "log1p_scaled":
        return min(1.0, math.log1p(max(0.0, float(value))) / math.log1p(float(spec["scale"])))
    raise ValueError(f"unknown transform {kind}")


@dataclass
class LoadedPolicy:
    manifest: dict[str, Any]
    policy: dict[str, Any]
    feature_schema: dict[str, Any]

    @property
    def version(self) -> str:
        return self.manifest["artifact_version"]

    def features(self, context: Mapping[str, Any]) -> list[float]:
        return [_apply(spec, context) for spec in self.feature_schema["features"]]

    def _scores(self, x: Sequence[float], eligible: Iterable[str]) -> dict[str, float]:
        scores = {}
        for action in sorted(set(eligible) & set(self.policy["actions"])):
            params = self.policy["parameters"][action]
            mean = sum(t * v for t, v in zip(params["theta"], x, strict=True))
            a_inv = params["a_inv"]
            variance = sum(x[i] * sum(a_inv[i][j] * x[j] for j in range(len(x))) for i in range(len(x)))
            scores[action] = mean + self.policy["alpha"] * math.sqrt(max(0.0, variance))
        return scores

    def probabilities(self, context: Mapping[str, Any], eligible: Sequence[str], *, explore: bool = False) -> dict[str, float]:
        """Distribution over ELIGIBLE known actions only; {} means 'fall back to static'."""
        scores = self._scores(self.features(context), eligible)
        if not scores:
            return {}
        best = max(scores.values())
        greedy = min(a for a, s in scores.items() if s == best)
        epsilon = self.policy["exploration"]["epsilon"] if explore and self.policy["exploration"]["mode"] == "epsilon_greedy" else 0.0
        k = len(scores)
        return {a: (1 - epsilon + epsilon / k) if a == greedy else epsilon / k for a in scores}

    def select(self, context: Mapping[str, Any], eligible: Sequence[str], rng: random.Random, *, shadow: bool, explore: bool = False) -> dict[str, Any] | None:
        """A RoutingDecision dict with its exact selection probability, or None (use static)."""
        try:
            distribution = self.probabilities(context, eligible, explore=explore)
        except ValueError:
            return None
        if not distribution:
            return None
        actions = sorted(distribution)
        draw, cumulative, chosen = rng.random(), 0.0, actions[-1]
        for action in actions:
            cumulative += distribution[action]
            if draw < cumulative:
                chosen = action
                break
        greedy = max(actions, key=distribution.__getitem__)  # unique maximum whenever k > 1
        return {"selected_action": chosen, "selection_probability": distribution[chosen], "exploration": chosen != greedy,
                "policy_version": self.version, "eligible_models": list(eligible), "shadow": shadow,
                "feature_schema_version": self.feature_schema["feature_schema_version"]}


def load_bundle(path: str | Path, *, trusted_public_keys: Iterable[str], karmi_version: str, known_actions: Iterable[str],
                expected_feature_schema_version: str) -> LoadedPolicy:
    root = Path(path)
    if (root / "checksums.json").is_symlink() or (root / "signature.sig").is_symlink():
        raise BundleRejected("symlink in bundle metadata")
    try:
        checksums_bytes = (root / "checksums.json").read_bytes()
        signature = json.loads((root / "signature.sig").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise BundleRejected(f"unreadable bundle: {exc}") from exc
    if not isinstance(signature, dict):
        raise BundleRejected("malformed signature file")
    # 1. signature over checksums.json with a trusted key
    try:
        public, sig = bytes.fromhex(signature["public_key"]), bytes.fromhex(signature["signature"])
    except (KeyError, ValueError) as exc:
        raise BundleRejected("malformed signature file") from exc
    if signature.get("algorithm") != "ed25519" or signature["public_key"] not in set(trusted_public_keys):
        raise BundleRejected("untrusted or unsupported signing key")
    if not ed25519.verify(public, checksums_bytes, sig):
        raise BundleRejected("signature invalid")
    # 2. checksums of every file, and nothing extra
    checksums = json.loads(checksums_bytes)
    if not isinstance(checksums, dict) or not isinstance(checksums.get("files"), dict):
        raise BundleRejected("invalid checksums file")
    if any(not isinstance(name, str) or not isinstance(digest, str) for name, digest in checksums["files"].items()):
        raise BundleRejected("invalid checksums file")
    listed = checksums["files"]
    entries = list(root.rglob("*"))
    if any(p.is_symlink() for p in entries):
        raise BundleRejected("symlink in bundle")
    present = {str(p.relative_to(root)) for p in entries if p.is_file()} - {"checksums.json", "signature.sig"}
    if present != set(listed):
        raise BundleRejected(f"file set mismatch: {sorted(present ^ set(listed))}")
    resolved_root = root.resolve()
    for name, digest in listed.items():
        if (not isinstance(name, str) or not isinstance(digest, str) or not name or "\\" in name
                or Path(name).is_absolute() or ".." in Path(name).parts or not (root / name).resolve().is_relative_to(resolved_root)):
            raise BundleRejected(f"unsafe bundle path: {name}")
        try:
            if hashlib.sha256((root / name).read_bytes()).hexdigest() != digest:
                raise BundleRejected(f"checksum mismatch: {name}")
        except OSError as exc:
            raise BundleRejected(f"unreadable bundle file: {name}") from exc
    try:
        documents = {name: json.loads((root / name).read_text(encoding="utf-8")) for name in REQUIRED_FILES if name in listed}
    except (OSError, ValueError) as exc:
        raise BundleRejected("unreadable bundle document") from exc
    missing = [name for name in REQUIRED_FILES if name not in documents]
    if missing:
        raise BundleRejected(f"missing files: {missing}")
    manifest, policy, features = documents["manifest.json"], documents["routing_policy.json"], documents["feature_schema.json"]
    # 3. artifact schema recognised
    if manifest.get("schema") != "PolicyBundleV1" or str(manifest.get("schema_version", "")).split(".")[0] != SUPPORTED_ARTIFACT_MAJOR:
        raise BundleRejected("unrecognised artifact schema")
    if policy.get("policy_schema_version") not in SUPPORTED_POLICY_SCHEMAS or policy.get("algorithm") != "linucb":
        raise BundleRejected("unsupported policy schema")
    # 4. feature schema compatible
    if features.get("feature_schema_version") != expected_feature_schema_version or manifest.get("feature_schema_id") != features.get("schema_id"):
        raise BundleRejected("feature schema incompatible")
    if policy.get("feature_dimension") != len(features.get("features", [])):
        raise BundleRejected("policy dimension does not match feature schema")
    exploration = policy.get("exploration")
    epsilon = exploration.get("epsilon") if isinstance(exploration, dict) else None
    if (not isinstance(exploration, dict) or exploration.get("mode") not in ("none", "epsilon_greedy")
            or isinstance(epsilon, bool) or not isinstance(epsilon, (int, float))
            or not math.isfinite(epsilon) or not 0.0 <= epsilon <= 1.0):
        raise BundleRejected("invalid exploration probability")
    # 5. model ids exist in Karmi's registry
    unknown = set(policy.get("actions", [])) - set(known_actions)
    if unknown:
        raise BundleRejected(f"unknown models: {sorted(unknown)}")
    # 7. minimum Karmi version
    if _version(karmi_version) < _version(manifest["minimum_karmi_version"]):
        raise BundleRejected("Karmi too old for this bundle")
    loaded = LoadedPolicy(manifest, policy, features)
    # 8/9. self-test: every parameter finite and well-shaped, a decision can be produced
    d = policy["feature_dimension"]
    for action in policy["actions"]:
        params = policy["parameters"].get(action)
        if (params is None or len(params["theta"]) != d or len(params["a_inv"]) != d or any(len(row) != d for row in params["a_inv"])
                or not all(math.isfinite(v) for v in params["theta"]) or not all(math.isfinite(v) for row in params["a_inv"] for v in row)):
            raise BundleRejected(f"malformed parameters for {action}")
    probe: dict[str, Any] = {spec["source"]: None for spec in features["features"] if "source" in spec}
    probe.update({"tier": "probe", "task_domain": "probe", "estimated_input_tokens": 0, "context_utilization_ratio": 0.0, "tool_count": 0,
                  "requires_structured_output": False, "requires_tools": False, "requires_memory": False, "requires_external_data": False,
                  "conversation_depth": 0, "retry_number": 0, "previous_tool_failure": False})
    distribution = loaded.probabilities(probe, policy["actions"], explore=True)
    if not distribution or abs(sum(distribution.values()) - 1.0) > 1e-9:
        raise BundleRejected("self-test failed")
    return loaded


@dataclass
class PolicySlots:
    """Karmi's policy pointers. Loading only fills ``candidate``; the active policy changes only via promote()."""

    active: str = "static"
    previous: str | None = None
    last_known_good: str = "static"
    candidate: LoadedPolicy | None = None
    mode: str = "received"
    events: list[str] = field(default_factory=list)

    def stage(self, loaded: LoadedPolicy) -> None:
        self.candidate, self.mode = loaded, "staged"
        self.events.append(f"staged {loaded.version}")

    def shadow(self) -> None:
        if self.candidate is None:
            raise BundleRejected("nothing staged")
        self.mode = "shadow"
        self.events.append(f"shadow {self.candidate.version}")
