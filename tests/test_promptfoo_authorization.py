import pytest
from model_lab.promptfoo import invoke_promptfoo, PromptfooImportError, export_promptfoo_manifest
from model_lab.isolation import AuthorizedLiveExecution
from model_lab.benchmark import load_suite

def dummy_runner(manifest):
    return "done"

suite = load_suite("benchmarks/seed_cases.jsonl")
candidates = [case.candidate_payload() for case in suite.cases[:1]]
valid_manifest = export_promptfoo_manifest(candidates, run_id="r")

def test_promptfoo_no_authorization():
    with pytest.raises(TypeError):
        invoke_promptfoo(valid_manifest, runner=dummy_runner)

def test_promptfoo_forged_boolean():
    with pytest.raises(TypeError):
        # We can't even pass approved_plan anymore, it throws TypeError
        invoke_promptfoo(valid_manifest, approved_plan=True, runner=dummy_runner)
        
    with pytest.raises(PromptfooImportError, match="requires an approved plan"):
        # We try to forge the capability argument with a bool instead of object
        invoke_promptfoo(valid_manifest, capability=True, runner=dummy_runner)

def test_promptfoo_invalid_artifact():
    from model_lab.pilot import require_dispatch_authorization, PilotBlockedError
    plan = {"immutable": True, "execution": {"concurrency": 2}}
    with pytest.raises(PilotBlockedError):
        require_dispatch_authorization(plan, allow_paid=True)

def test_promptfoo_valid_capability():
    cap = AuthorizedLiveExecution("hashvalue", "cli_user")
    result = invoke_promptfoo(valid_manifest, capability=cap, runner=dummy_runner)
    assert result == "done"

def test_fake_to_live_prevention():
    from model_lab.pilot import require_dispatch_authorization, PilotBlockedError
    plan = {"immutable": False, "candidates": [{"provider": "fake", "model": "m", "identifier": "fake:m"}]}
    
    with pytest.raises(PilotBlockedError):
        require_dispatch_authorization(plan, allow_paid=True)

def test_direct_helper_invocation():
    # Direct runner is required to take the manifest, but you still need the capability
    with pytest.raises(TypeError):
        invoke_promptfoo(valid_manifest, runner=dummy_runner)

