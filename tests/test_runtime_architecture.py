import sys

from model_lab.application.execution import ExecutionEngine
from model_lab.cli import main
from model_lab.domain.isolation import AuthorizedLiveExecution, CandidateInput
from model_lab.storage import SQLiteStore


def test_runtime_ownership_is_canonical():
    assert main.__module__ == "model_lab.cli.commands"
    assert SQLiteStore.__module__ == "model_lab.storage.sqlite"
    assert ExecutionEngine.__module__ == "model_lab.application.execution"
    assert CandidateInput.__module__ == "model_lab.domain.isolation"
    assert AuthorizedLiveExecution.__module__ == "model_lab.domain.isolation"


def test_legacy_runtime_modules_are_not_loaded_normally():
    loaded = {name for name in sys.modules if name.startswith("model_lab._legacy_")}
    assert not loaded
