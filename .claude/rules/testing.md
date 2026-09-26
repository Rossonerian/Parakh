---
paths:
  - "tests/**/*.py"
  - "model_lab/**/*.py"
---

# Testing conventions

- Run with `.venv/bin/python -m pytest -q` (system `python3` lacks pytest).
- Tests are fixture-only: `providers/fake.py`, never `providers/live.py`.
  Nothing in the suite makes a real network call.
- One test file per behavior area, named `test_<area>.py`, mirroring the
  module(s) it covers — follow the existing mapping (e.g.
  `tests/test_review_integrity.py` ↔ `model_lab/review.py`) rather than
  adding a new catch-all file.
- When a public function's contract changes (new required kwarg, new
  validation), grep for every existing caller/test importing it before
  editing — `model_lab` has several call sites per shared symbol
  (`model_lab/cli/commands.py` plus multiple `tests/test_*.py`). A stale
  caller is a real regression, not a false positive.
- Don't weaken an assertion or hardcode an expected value to make a test
  pass; if the test's premise is now wrong, say so and fix the premise.
- Full-suite check before calling anything done: `.venv/bin/python -m pytest -q`
  should show `N passed` with zero failures/errors.
