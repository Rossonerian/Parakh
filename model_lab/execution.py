"""Bounded candidate execution with durable attempts and recovery state."""

from __future__ import annotations

import hashlib
import threading
import time
from dataclasses import dataclass
from typing import Iterable

from .benchmark import select_cases
from .budget import BudgetLedger
from .errors import BudgetExceededError, ValidationError
from .isolation import candidate_input
from .providers.base import Provider, ProviderRequest, ProviderRuntimeError
from .schemas import Attempt, AttemptStatus, Case, Run, Suite, utc_now
from .storage import SQLiteStore


@dataclass(frozen=True)
class ExecutionResult:
    run_id: str
    status: str
    attempts: tuple[Attempt, ...]
    failures: int


def _id(prefix: str, *parts: str) -> str:
    return f"{prefix}-" + hashlib.sha256(":".join(parts).encode()).hexdigest()[:32]


class ExecutionEngine:
    def __init__(self, store: SQLiteStore, provider: Provider, *, max_retries: int = 0, retry_delay_seconds: float = 0.0) -> None:
        if max_retries < 0:
            raise ValidationError("max_retries must be non-negative")
        self.store, self.provider = store, provider
        self.max_retries, self.retry_delay_seconds = max_retries, retry_delay_seconds
        self.budgets = BudgetLedger(store)

    def execute(self, suite: Suite, run: Run, *, case_ids: Iterable[str] | None = None, splits: Iterable[str] | None = None, domains: Iterable[str] | None = None, workflows: Iterable[str] | None = None, complexity_levels: Iterable[int] | None = None, cancel_event: threading.Event | None = None) -> ExecutionResult:
        selected = select_cases(suite, case_ids=case_ids or run.case_ids, splits=splits, domains=domains, workflows=workflows, complexity_levels=complexity_levels)
        selected_ids = {case.case_id for case in selected}
        if not selected_ids.issubset(set(run.case_ids)):
            raise ValidationError("selection contains cases outside the run")
        try:
            self.store.get_run(run.run_id)
        except Exception:
            self.store.create_run(run)
        self.store.update_run_status(run.run_id, "running")
        failures = 0
        produced: list[Attempt] = []
        run_started = time.monotonic()
        for case in selected:
            if cancel_event and cancel_event.is_set():
                self.store.update_run_status(run.run_id, "cancelled")
                break
            if run.budget.max_runtime_seconds is not None and time.monotonic() - run_started >= run.budget.max_runtime_seconds:
                self.store.update_run_status(run.run_id, "partial")
                break
            logical = _id("req", run.run_id, case.case_id)
            try:
                reservation = self.budgets.reserve(run.run_id, logical, run.budget, estimated_cost_minor=None if run.budget.max_cost_minor is None else 0)
            except BudgetExceededError:
                failures += 1
                self.store.update_run_status(run.run_id, "partial")
                break
            for retry in range(self.max_retries + 1):
                attempt_id = _id("att", run.run_id, case.case_id, str(retry))
                started = utc_now()
                status = AttemptStatus.SUCCESS
                response_text = None
                error = None
                finish_reason = None
                metadata: dict[str, object] = {}
                input_tokens = output_tokens = cost_minor = None
                currency = first_latency = completion_latency = None
                try:
                    response = self.provider.generate(ProviderRequest(candidate_input(case), run.model_config.model, run.model_config.parameters, run.budget.max_runtime_seconds, run.seed))
                    response_text, finish_reason = response.text, response.finish_reason
                    input_tokens, output_tokens, cost_minor, currency = response.input_tokens, response.output_tokens, response.cost_minor, response.currency
                    first_latency, completion_latency, metadata = response.first_token_latency_ms, response.completion_latency_ms, dict(response.metadata)
                    if response_text is None:
                        status = AttemptStatus.INVALID_PROVIDER_RESPONSE
                        error = "provider returned no response text"
                    elif response_text == "":
                        status = AttemptStatus.MALFORMED_OUTPUT
                        error = "provider returned empty output"
                except TimeoutError as exc:
                    status, error = AttemptStatus.TIMEOUT, str(exc)
                except ProviderRuntimeError as exc:
                    status, error = AttemptStatus.PROVIDER_FAILURE, str(exc)
                except Exception as exc:
                    status, error = AttemptStatus.INFRASTRUCTURE_FAILURE, str(exc)
                completed = utc_now()
                attempt = Attempt(attempt_id=attempt_id, run_id=run.run_id, logical_request_id=logical, case_id=case.case_id, model_config=run.model_config, prompt_hash=case.prompt_hash, response_text=response_text, status=status, started_at=started, completed_at=completed, finish_reason=finish_reason, error=error, first_token_latency_ms=first_latency, completion_latency_ms=completion_latency, input_tokens=input_tokens, output_tokens=output_tokens, cost_minor=cost_minor, currency=currency, raw_metadata=metadata)
                self.store.add_attempt(attempt)
                produced.append(attempt)
                if status is AttemptStatus.SUCCESS or status not in {AttemptStatus.PROVIDER_FAILURE, AttemptStatus.TIMEOUT} or retry == self.max_retries:
                    if status is not AttemptStatus.SUCCESS:
                        failures += 1
                    break
                if self.retry_delay_seconds:
                    time.sleep(self.retry_delay_seconds)
            self.budgets.settle(reservation, actual_cost_minor=produced[-1].cost_minor)
        current = self.store.get_run(run.run_id)
        if current.status == "running":
            self.store.update_run_status(run.run_id, "partial" if failures else "completed")
        return ExecutionResult(run.run_id, self.store.get_run(run.run_id).status, tuple(produced), failures)
