# Parakh ModelLab

Parakh ModelLab is an independent, Linux-friendly evaluation laboratory for the Daily AI Agent project. It measures controlled model/provider runs and produces reviewable evidence; it does not implement the consumer application, billing, WhatsApp, production routing, or live customer actions.

The default workflow is offline and uses the supplied 60-case benchmark plus deterministic fake providers. Raw attempts are retained, candidate requests are structurally separated from protected evaluation data, and unknown latency/token/cost values remain unknown. Optional Ollama and OpenRouter HTTP adapters are available behind explicit environment configuration and are never used by the offline workflow.

## Quick start

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python -m model_lab suite validate benchmarks/seed_cases.jsonl
.venv/bin/python -m pytest
```

For the complete offline lifecycle, see [MANUAL_TESTING.md](MANUAL_TESTING.md). The repository currently contains no live credentials and no paid provider calls are required.

## Scope and evidence

The benchmark is a controlled synthetic/authored fixture, not evidence of real-world model quality. Recommendations are drafts with coverage and limitations and never modify the Windows application repository. Live adapters remain optional and fail closed without an explicitly approved budget and credentials.

The referenced planning documents `PRD.md`, `Design.md`, and `Tier_Entitlements.md` were absent at intake; this implementation follows the available ModelLab-specific specifications and records that limitation in `Memory.md`.
