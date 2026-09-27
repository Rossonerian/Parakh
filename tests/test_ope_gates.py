"""Paired bootstrap non-inferiority: the decision rule behind the verifier's OPE, segment and holdout gates."""

from __future__ import annotations

import random

from model_lab.optimization.router.off_policy import paired_difference


class Fixed:
    name = "fixed"

    def __init__(self, action: str) -> None:
        self.action = action

    def probabilities(self, example):
        return {self.action: 1.0} if self.action in example["eligible_actions"] else {}


def logged(n: int, *, good: float = 0.8, bad: float = 0.2, noise: float = 0.05, seed: int = 0) -> list[dict]:
    """Uniform logging over two actions with exact propensities."""
    rng = random.Random(seed)
    rows = []
    for _ in range(n):
        action = rng.choice(("good", "bad"))
        rows.append({"action": action, "propensity": 0.5, "eligible_actions": ["good", "bad"],
                     "reward": (good if action == "good" else bad) + rng.uniform(-noise, noise)})
    return rows


def test_clearly_better_policy_is_proven_non_inferior():
    result = paired_difference(Fixed("good"), logged(400), margin=0.05)
    assert result["verdict"] == "non_inferior"
    assert 0.25 < result["difference"] < 0.35 and result["ci"][0] > 0


def test_clearly_worse_policy_is_confidently_worse():
    result = paired_difference(Fixed("bad"), logged(400), margin=0.05)
    assert result["verdict"] == "worse" and result["ci"][1] < -0.05


def test_small_noisy_segment_is_inconclusive_never_a_pass():
    result = paired_difference(Fixed("good"), logged(12, good=0.5, bad=0.5, noise=0.5, seed=3), margin=0.05)
    assert result["verdict"] == "inconclusive"
    assert result["ci"][0] < -0.05 < result["ci"][1]


def test_policy_with_no_logged_support_is_inconclusive():
    result = paired_difference(Fixed("unlogged"), [{**row, "eligible_actions": ["good", "bad", "unlogged"]} for row in logged(100)], margin=0.05)
    assert result["verdict"] == "inconclusive" and result["difference"] is None


def test_same_inputs_same_interval():
    rows = logged(200, seed=9)
    assert paired_difference(Fixed("good"), rows, margin=0.05, seed=4) == paired_difference(Fixed("good"), rows, margin=0.05, seed=4)
