"""Versioned multi-objective reward engine and trajectory grading.

Provides reward configuration, deterministic and rubric quality signals,
calibrated user signal interpretation, composite multi-objective reward calculation,
and multi-step trajectory grading.
"""

from __future__ import annotations

from model_lab.rewards.composite import persist, reward_for_attempt, reward_for_run
from model_lab.rewards.deterministic import deterministic_from_grade, deterministic_from_run
from model_lab.rewards.normalize import normalize_cost, normalize_latency
from model_lab.rewards.rubric import rubric_for_run, rubric_from_reviews
from model_lab.rewards.schema import (
    RewardComponents,
    RewardConfig,
    RewardRecord,
)
from model_lab.rewards.trajectory import grade_trajectory, persist_trajectory_grade
from model_lab.rewards.user_signals import user_signal

__all__ = [
    "RewardComponents",
    "RewardConfig",
    "RewardRecord",
    "deterministic_from_grade",
    "deterministic_from_run",
    "grade_trajectory",
    "normalize_cost",
    "normalize_latency",
    "persist",
    "persist_trajectory_grade",
    "reward_for_attempt",
    "reward_for_run",
    "rubric_for_run",
    "rubric_from_reviews",
    "user_signal",
]
