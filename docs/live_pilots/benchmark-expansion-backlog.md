# Benchmark expansion backlog

The current 60 seed cases / 15 independent families validate laboratory
mechanics and provide an initial comparison frame. They do not establish a
production routing policy. Before a routing candidate can be considered for
staging, add independently authored families to train, calibration, and
holdout splits; derived paraphrases, translations, numeric edits, and
long-context variants retain their parent family and split.

Priority backlog:

- Context-limit families: realistic supplied-material sizes, exact token-fit
  failures, competing evidence chunks, and honest deferral when key evidence
  cannot fit.
- Evidence-conflict families: contradictory notes, stale summaries, changing
  authoritative records, provenance citations, and required clarification.
- Action-uncertainty families: tool permission denial, timeout-after-success,
  idempotency, reconciliation, cancellation, and safe unresolved states.
- Document/file families: extraction from supplied files, tables, malformed
  content, retention/deletion propagation, and no fabricated file facts.
- Bilingual workflow families: Hindi/English and other approved launch-language
  workflows, mixed-script constraints, translation ambiguity, and equal safety
  checks across languages.
- Recovery-failure families: provider outage, malformed output, repair and
  escalation ceilings, budget exhaustion, fallback eligibility, and terminal
  `ASK_USER`, `SAFE_STOP`, or `DEFERRED` behavior.

Every added family needs authored provenance, candidate-only projection tests,
protected oracle records, explicit critical failures, split/family leakage
tests, and human-review calibration where deterministic grading cannot decide.
