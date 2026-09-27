"""linucb.py: LinUCB trainer and serializer.

Implements Contextual Bandit LinUCB training with Sherman-Morrison updates
and exports policies to the standard schema.
"""

from dataclasses import dataclass
from typing import Any, Mapping, Sequence
import math

from model_lab.errors import ValidationError
from model_lab.schema_registry import ROUTER_MODEL_SCHEMA_VERSION
from model_lab.optimization.router.features import feature_schema

@dataclass(frozen=True)
class LinUCBModel:
    actions: tuple[str, ...]
    dimension: int
    alpha: float
    lambda_: float
    exploration: dict[str, Any]
    parameters: dict[str, dict[str, Any]]
    feature_schema_version: str

    def scores(self, x: Sequence[float], eligible: Sequence[str]) -> dict[str, float]:
        res = {}
        for a in eligible:
            if a in self.actions:
                p = self.parameters[a]
                theta = p["theta"]
                a_inv = p["a_inv"]
                
                # dot(theta, x)
                mean = sum(th * xi for th, xi in zip(theta, x, strict=False))
                
                # x^T A^{-1} x
                variance = 0.0
                for i in range(self.dimension):
                    row_i = 0.0
                    for j in range(self.dimension):
                        row_i += a_inv[i][j] * x[j]
                    variance += x[i] * row_i
                
                res[a] = mean + self.alpha * math.sqrt(max(0.0, variance))
        return res

    def greedy(self, x: Sequence[float], eligible: Sequence[str]) -> str:
        s = self.scores(x, eligible)
        if not s:
            raise ValueError("No eligible actions overlap with model actions")
        # argmax, ties -> lexicographically smallest
        return min(s.keys(), key=lambda a: (-s[a], a))

    def probabilities(self, x: Sequence[float], eligible: Sequence[str]) -> dict[str, float]:
        overlap = [a for a in eligible if a in self.actions]
        if not overlap:
            return {}
            
        scores = self.scores(x, overlap)
        best_action = min(overlap, key=lambda a: (-scores[a], a))
        
        mode = self.exploration.get("mode", "none")
        k = len(overlap)
        
        res = {}
        if mode == "none":
            res[best_action] = 1.0
        elif mode == "epsilon_greedy":
            eps = float(self.exploration.get("epsilon", 0.0))
            for a in overlap:
                res[a] = eps / k
            res[best_action] += (1.0 - eps)
        else:
            raise ValueError(f"Unknown exploration mode: {mode}")
            
        return res


def _dot(a: Sequence[float], b: Sequence[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=False))

def _mat_vec(m: Sequence[Sequence[float]], v: Sequence[float]) -> list[float]:
    return [_dot(row, v) for row in m]

def fit(
    examples: Sequence[Mapping[str, Any]],
    *,
    actions: Sequence[str],
    dimension: int,
    alpha: float = 0.5,
    lambda_: float = 1.0,
    importance_weighting: bool = True,
    weight_clip: float = 10.0,
    epsilon: float = 0.05,
) -> LinUCBModel:
    
    sorted_actions = tuple(sorted(actions))
    
    a_invs = {}
    bs = {}
    ns = {}
    weight_sums = {}
    
    for a in sorted_actions:
        a_inv = [[0.0] * dimension for _ in range(dimension)]
        for i in range(dimension):
            a_inv[i][i] = 1.0 / lambda_
        a_invs[a] = a_inv
        bs[a] = [0.0] * dimension
        ns[a] = 0
        weight_sums[a] = 0.0

    for ex in examples:
        action = ex["action"]
        if action not in a_invs:
            continue
            
        x = ex["features"]
        r = ex["reward"]
        prop = ex["propensity"]
        
        if importance_weighting:
            w = min(1.0 / prop, weight_clip)
        else:
            w = 1.0
            
        a_inv = a_invs[action]
        b = bs[action]
        
        v = _mat_vec(a_inv, x)
        denom = 1.0 + w * _dot(x, v)
        factor = w / denom
        
        for i in range(dimension):
            for j in range(dimension):
                a_inv[i][j] -= factor * v[i] * v[j]
                
        for i in range(dimension):
            b[i] += w * r * x[i]
            
        ns[action] += 1
        weight_sums[action] += w

    parameters = {}
    for a in sorted_actions:
        theta = _mat_vec(a_invs[a], bs[a])
        parameters[a] = {
            "theta": theta,
            "a_inv": a_invs[a],
            "n": ns[a],
            "weight_sum": weight_sums[a]
        }

    return LinUCBModel(
        actions=sorted_actions,
        dimension=dimension,
        alpha=alpha,
        lambda_=lambda_,
        exploration={"mode": "epsilon_greedy" if epsilon > 0 else "none", "epsilon": epsilon},
        parameters=parameters,
        feature_schema_version=feature_schema()["feature_schema_version"]
    )

def to_policy_document(model: LinUCBModel) -> dict:
    return {
        "algorithm": "linucb",
        "policy_schema_version": ROUTER_MODEL_SCHEMA_VERSION,
        "feature_schema_version": model.feature_schema_version,
        "feature_dimension": model.dimension,
        "actions": list(model.actions),
        "alpha": model.alpha,
        "exploration": model.exploration,
        "parameters": model.parameters,
        "selection": "score = theta.x + alpha*sqrt(x.A_inv.x) over eligible known actions; greedy = argmax, ties -> lexicographically smallest action; epsilon_greedy: greedy gets 1-eps+eps/k, others eps/k (k = eligible known actions)",
        "fallback": "static"
    }

def from_policy_document(doc: dict) -> LinUCBModel:
    if doc.get("algorithm") != "linucb":
        raise ValidationError("Not a linucb policy document")
    if doc.get("policy_schema_version") != ROUTER_MODEL_SCHEMA_VERSION:
        raise ValidationError("Schema version mismatch")
        
    dim = doc["feature_dimension"]
    params = doc["parameters"]
    
    for _a, p in params.items():
        if len(p["theta"]) != dim:
            raise ValidationError("theta dimension mismatch")
        if len(p["a_inv"]) != dim:
            raise ValidationError("a_inv row dimension mismatch")
        for row in p["a_inv"]:
            if len(row) != dim:
                raise ValidationError("a_inv col dimension mismatch")
            for v in row:
                if not math.isfinite(v):
                    raise ValidationError("a_inv contains non-finite numbers")
        for v in p["theta"]:
            if not math.isfinite(v):
                raise ValidationError("theta contains non-finite numbers")
                
    return LinUCBModel(
        actions=tuple(doc["actions"]),
        dimension=dim,
        alpha=doc["alpha"],
        lambda_=1.0,
        exploration=doc["exploration"],
        parameters=params,
        feature_schema_version=doc["feature_schema_version"]
    )
