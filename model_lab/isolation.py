"""Compatibility shim for domain isolation contracts."""

from model_lab.domain.isolation import (
    AuthorizedLiveExecution,
    CandidateInput,
    HIDDEN_FIELDS,
    assert_candidate_safe,
    candidate_input,
)

__all__ = [
    "AuthorizedLiveExecution",
    "CandidateInput",
    "HIDDEN_FIELDS",
    "assert_candidate_safe",
    "candidate_input",
]
