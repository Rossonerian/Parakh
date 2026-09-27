"""Offline candidate-based harness (prompt/instruction) optimization engine."""

from model_lab.optimization.harness.candidate import HarnessCandidate, assert_oracle_free
from model_lab.optimization.harness.exporter import bundle_files, export_bundle
from model_lab.optimization.harness.metric_adapter import HarnessEvaluation, evaluate, persist
from model_lab.optimization.harness.optimizer import (
    CandidateGenerator,
    FailureDrivenGenerator,
    FailureSummary,
    OptimizationResult,
    optimize,
)
from model_lab.optimization.harness.prompt_registry import (
    COMPONENTS,
    PromptRegistry,
    PromptVersion,
)
from model_lab.optimization.harness.simulated import PromptSensitiveProvider, simulated_task

__all__ = [
    "COMPONENTS",
    "CandidateGenerator",
    "FailureDrivenGenerator",
    "FailureSummary",
    "HarnessCandidate",
    "HarnessEvaluation",
    "OptimizationResult",
    "PromptRegistry",
    "PromptSensitiveProvider",
    "PromptVersion",
    "assert_oracle_free",
    "bundle_files",
    "evaluate",
    "export_bundle",
    "optimize",
    "persist",
    "simulated_task",
]
