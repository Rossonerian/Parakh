# Post-pilot gates

This document describes the offline, reviewable gates prepared for a live
development pilot. The helpers in `model_lab/post_pilot.py` consume persisted
attempts and imported evidence only. They do not call providers, write billing
ledgers, select production models, or change application configuration.

## Usage and cost reconciliation

`reconcile_provider_usage(attempts, provider_usage)` matches provider usage
records by immutable `attempt_id`. Missing attempts, missing provider costs,
invalid records, duplicate records, and mixed currencies are reported. Totals
and deltas are `null` whenever the evidence is incomplete or currencies are not
consistent. The helper does not estimate tokens or cost and does not merge the
customer-usage ledger with the provider-expense ledger.

## Protected critical-failure report

`critical_failure_report(cases, attempts, grades)` reports observable failed
statuses and deterministic failed grades by case, family, domain, complexity,
and attempt. It intentionally excludes reference answers, rubrics, and other
protected oracle material. Semantic severity remains a human-review question.

## Blind calibration review

`export_stratified_calibration_review` selects only `split=calibration` cases,
round-robin across domain and complexity strata, and delegates to the existing
blind export. Provider/model identity, cost, latency, and ranking metadata do
not cross the boundary. If calibration attempts are not available, the result
is explicitly blocked; train or holdout attempts are never substituted.

`calibration_selection_report` records candidate policy IDs and review evidence
but never silently chooses a model or policy. The owner must record an explicit
selection after reviewing the blind evidence.

## Holdout lock

`consume_holdout_evaluation` is a one-time filesystem gate. It rejects tuning,
requires a frozen policy hash and configuration hash, records the exact
holdout IDs, and refuses a second consumption even when hashes match. The
record is an evaluation lock, not a tuning dataset or production approval.

## Router replay/shadow

`router_replay_shadow` produces a deterministic evidence artifact containing
recommendations and observed case IDs. It records matching application-config
hashes and explicit `activation_performed=false`; it never mutates or writes
application routing configuration. Any recommendation remains draft evidence
until the separate product-policy gates are satisfied.

These are prepared gates, not pilot results. Actual provider reconciliation,
human review, calibration selection, and holdout evaluation require a valid
operator-authorized pilot and remain unperformed until that gate is opened.
