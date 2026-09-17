"""CLI package exposing the existing command surface as a thin orchestration layer."""

from importlib import util
import sys
from pathlib import Path

_legacy_path = Path(__file__).resolve().parents[1] / "cli.py"
_spec = util.spec_from_file_location("model_lab._legacy_cli", _legacy_path)
if _spec is None or _spec.loader is None:
    raise ImportError(f"unable to load legacy CLI module from {_legacy_path}")
_legacy_module = util.module_from_spec(_spec)
sys.modules.setdefault("model_lab._legacy_cli", _legacy_module)
_spec.loader.exec_module(_legacy_module)

build_parser = _legacy_module.build_parser
main = _legacy_module.main

__all__ = ["build_parser", "main"]
