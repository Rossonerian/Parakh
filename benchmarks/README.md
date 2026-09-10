# Seed Benchmark Bank

`seed_cases.jsonl` is an authored starting bank, not evaluated model output.

- 60 distinct prompts, 15 per complexity level (1–4).
- 15 domains: communication, calendar, task planning, expenses, shopping, travel, document extraction, tabular analysis, support, source reasoning, privacy, conversation memory, multilingual work, automation and ambiguity.
- 36 train/development, 12 calibration, 12 holdout cases.
- 15 conservatively grouped workflow families, each with four complexity variants. Split by family: 9 development, 3 calibration, 3 holdout. These are not 60 independent families.
- Each line includes candidate messages, reference answer, rubric, critical failure conditions, family identity and provenance.
- No live calls, sends, bookings or private data are needed. The tool-workflow cases ask for proposed behavior from contained fixtures.

## Running fairly

Do not paste entire JSONL records into a candidate model. Export and send only `messages`, with shared evaluation system instructions if required and recorded. Answers and grading notes are protected evaluation data. Models that grade responses may see references; candidate models must not.

`evaluation.method=exact_json` means expected JSON structure/value equality can be automated. Other cases require explicit rubric grading, with deterministic subchecks where possible. Seed rubric criteria are binary initially; define normalization before a run and do not change grading to favor a model after seeing outputs. A whitespace/currency formatting difference is not automatically a semantic failure unless exact formatting is part of the prompt. Do not rely on substring checks to establish reasoning quality.

Some reference answers are compact oracle notes rather than polished user-facing responses. Grade equivalent correct answers fairly. Privacy cases may require separate user-response and backend-behavior sections; sensitive fixture values must not leak into the user-facing portion.

The 60 cases are short-context baseline coverage, not proof of long-context, voice, factual-world-knowledge or production performance. Add family-preserving paraphrases/context variants and newly authored task families. The current simple split does not cover every domain within each subset; ensure all release-critical domains appear in a sufficiently expanded calibration and holdout set before training or accepting a router.

## Family and holdout discipline

Assign all near-duplicate, translated, number-changed and context-expanded variants to their parent's family and split. Never move a failing holdout case to development to improve the reported score. If a holdout becomes part of prompt tuning, retire its benchmark role and author an unseen replacement. Keep a frozen suite version and hash with every experiment.

At least 3 repeats is a useful initial variability check for stochastic models if the budget permits, but does not make three observations independent tasks. More evidence is required for sparse categories, critical failures and small between-model differences. Report coverage and uncertainty; 60 prompts cannot justify a universal best-model claim.

## Validation performed for this deliverable

The authoring check verified JSONL parsing, 60 unique IDs, 60 unique prompt strings, four equally sized complexity levels, 15 domains and nonempty reference/rubric fields. This is dataset structure validation, not execution of any candidate model or an external expert audit of every rubric.

See `../Model_Testing_Spec.md` for implementation, billing, evaluation, visualization and acceptance requirements, and `../Testing_Lab_Prompt.md` for the coding-agent prompt.
