"""Parakh ModelLab: reproducible, offline-first model evaluation.

The package intentionally keeps a small layered structure:
CLI -> application -> domain -> storage/providers -> reporting.
Legacy flat modules remain as compatibility shims while the layered package
boundaries are defined explicitly for maintainability.
"""

__version__ = "0.1.0"

