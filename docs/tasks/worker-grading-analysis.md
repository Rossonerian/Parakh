# Task ML-02 — grading, review, comparison, regression, routing

Base commit: `00fb5e3`
Requested role/model: Worker / `gpt-5.6-luna` / medium (report effective runtime identity)
Owner: Luna worker 2

## Exclusive ownership

Worker may add/edit only:

- `model_lab/grading.py`
- `model_lab/analysis.py`
- `model_lab/review.py`
- `model_lab/routing.py`
- `tests/test_grading_analysis.py`
- `tests/test_review_routing.py`
- `docs/handoffs/ML-02.md`

Do not edit schemas, benchmark, isolation, CLI, storage, providers, execution, pyproject, or Memory.md. Integrate around existing contracts; list any contract gap instead of editing shared files.

## Required behavior

Implement exact JSON/text/normalized/schema/arithmetic/required-field deterministic graders with explicit abstention and provenance, blind review export/import with anonymized labels, matched-case comparison by domain/workflow/complexity/split and family-aware summaries, regression comparisons without fabricated significance, and routing evidence drafts with eligibility, coverage, limitations, fallbacks, and evidence IDs. Unknown values stay null; synthetic runs are labeled.

## Targeted validation

Use `python3 -m compileall -q model_lab tests` plus focused tests or stdlib scripts if pytest is unavailable. Include exact commands/results in handoff. Commit all files on the worker branch before completion.

