"""Storage package boundary for SQLite persistence."""

from importlib import util
import sys
from pathlib import Path

_legacy_path = Path(__file__).resolve().parents[1] / "storage.py"
_spec = util.spec_from_file_location("model_lab._legacy_storage", _legacy_path)
if _spec is None or _spec.loader is None:
    raise ImportError(f"unable to load legacy storage module from {_legacy_path}")
_legacy_module = util.module_from_spec(_spec)
sys.modules.setdefault("model_lab._legacy_storage", _legacy_module)
_spec.loader.exec_module(_legacy_module)

SQLiteStore = _legacy_module.SQLiteStore
IntegrityError = _legacy_module.IntegrityError
NotFoundError = _legacy_module.NotFoundError
ValidationError = _legacy_module.ValidationError

__all__ = ["SQLiteStore", "IntegrityError", "NotFoundError", "ValidationError"]
