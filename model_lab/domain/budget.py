"""Canonical budget ledger and reservation state transitions."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from model_lab.errors import BudgetExceededError, ValidationError
from model_lab.schemas import Budget, utc_now
from model_lab.storage.sqlite import SQLiteStore


@dataclass(frozen=True)
class Reservation:
    reservation_id: str
    run_id: str
    logical_request_id: str
    estimated_cost_minor: int | None


class BudgetLedger:
    def __init__(self, store: SQLiteStore) -> None:
        self.store = store

    def reserve(self, run_id: str, logical_request_id: str, budget: Budget, *, estimated_cost_minor: int | None = None) -> Reservation:
        if estimated_cost_minor is not None and estimated_cost_minor < 0:
            raise ValidationError("estimated cost must be non-negative")
        reservation_id = "res-" + hashlib.sha256(f"{run_id}:{logical_request_id}".encode()).hexdigest()[:32]
        try:
            self.store.reserve_budget(reservation_id, run_id, logical_request_id, budget.max_requests, budget.max_cost_minor, estimated_cost_minor, budget.currency, utc_now(), budget.max_cases)
        except ValidationError as exc:
            raise BudgetExceededError(str(exc)) from exc
        return Reservation(reservation_id, run_id, logical_request_id, estimated_cost_minor)

    def settle(self, reservation: Reservation, *, actual_cost_minor: int | None = None) -> None:
        if actual_cost_minor is not None and actual_cost_minor < 0:
            raise ValidationError("actual cost must be non-negative")
        self.store.settle_budget(reservation.reservation_id, actual_cost_minor, "settled" if actual_cost_minor is not None else "unknown")

    def release(self, reservation: Reservation) -> None:
        self.store.settle_budget(reservation.reservation_id, None, "released")
