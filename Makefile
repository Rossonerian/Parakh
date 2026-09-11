PYTHON ?= python3

.PHONY: doctor dev test-unit test-integration test-e2e test-smoke test-release demo

doctor:
	$(PYTHON) -m model_lab doctor

dev:
	@mkdir -p lab-data
	@dev_dir=$$(mktemp -d lab-data/dev.XXXXXX); echo "ModelLab dev output: $$dev_dir"; $(PYTHON) -m model_lab demo --suite benchmarks/seed_cases.jsonl --out "$$dev_dir"

test-unit:
	$(PYTHON) -m pytest -q

test-integration:
	$(PYTHON) -m pytest -q tests/test_storage_execution.py tests/test_ingestion_budget.py tests/test_offline_e2e.py

test-e2e:
	$(PYTHON) -m pytest -q tests/test_offline_e2e.py

test-smoke:
	$(PYTHON) -m model_lab suite validate benchmarks/seed_cases.jsonl

test-release: doctor test-unit test-e2e

demo:
	$(PYTHON) -m model_lab demo --suite benchmarks/seed_cases.jsonl --out lab-data/demo
