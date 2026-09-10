"""Stable exceptions used at ModelLab boundaries."""


class ModelLabError(Exception):
    """Base error for expected user-facing failures."""


class ValidationError(ModelLabError):
    """Input failed schema or semantic validation."""


class IntegrityError(ModelLabError):
    """An immutable or consistency invariant was violated."""


class NotFoundError(ModelLabError):
    """A referenced durable record does not exist."""


class BudgetExceededError(ModelLabError):
    """A run cannot dispatch because a finite budget is exhausted."""

