# Evaluations

Reproducible experiments comparing product design choices — prompt strategies,
model versions, retrieval configs — against fixed baselines.

Each subdirectory is one self-contained experiment: runner script, sample
sheet, and a README explaining what it's testing and how to reproduce.

## Ground rules

- **Sample sheets are frozen defaults, not code** — the `samples/default.json`
  in each experiment is the reference baseline used for cross-run comparison.
  Don't edit it silently. To probe a different question, add a new sheet.
- **Results are gitignored, scripts and sheets are tracked** — the point is
  that anyone can reproduce the run given the same inputs and code. Committing
  large output artifacts (JSON dumps, generated HTML) would defeat that.
- **Patient data lives outside the repo** — under `COSMETIC_DATA_ROOT`
  (default: `<repo>/downloads/`), which is gitignored for privacy.

## Current experiments

| Directory | Question |
|---|---|
| [`diagnosis_prompt_ablation/`](diagnosis_prompt_ablation/) | Does the production few-shot pipeline (system prompt + 2 doctor-reviewed cases) actually outperform a naive prompt on the same VLM? |
