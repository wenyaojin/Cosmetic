# Diagnosis prompt ablation — A (naive baseline) vs C (production few-shot)

Evaluates whether the production diagnosis prompt path (`backend/app/prompts/`
+ 2-shot doctor cases) produces materially better output than a naive
domain-agnostic prompt against the same VLM (`qwen-vl-max`) and same sample
photos.

## What it measures

Both conditions run on the same image, at the same temperature/top_p, against
the same model. Only the **prompt strategy** differs:

- **A** — a single user turn with a Chinese "面部美容顾问" prompt (see
  `prompts.py::NAIVE_PROMPT`). No system prompt, no few-shot.
- **C** — the production pipeline in
  `backend/app/services/dashscope_diagnosis.py`, which uses the 27-zone system
  prompt + 2 doctor-reviewed few-shot cases.

Outputs are compared on accuracy (does the diagnosis match what's visible?),
coverage (are real problems captured, non-existent ones avoided?), and
downstream usability (doctor / patient / image-edit model).

## Layout

```
diagnosis_prompt_ablation/
├── run.py             Runner: reads sample sheet, calls A + C per sample
├── build_report.py    Post-processor: renders side-by-side HTML for advisor review
├── prompts.py         The A-condition naive prompt
├── samples/           Sample sheets — see samples/README.md
│   ├── default.json   Frozen reference set for cross-run comparability
│   └── README.md
└── results/           Per-run outputs (gitignored — regenerable)
    └── <sheet_stem>_<timestamp>/
        ├── manifest.json
        ├── <patient_id>_A.json
        ├── <patient_id>_C.json
        └── ablation_report.html
```

## Prerequisites

1. `DASHSCOPE_API_KEY` set in the environment.
2. Patient dataset available locally. `run.py` and `build_report.py` glob for
   images under `COSMETIC_DATA_ROOT/**/images_by_patient/<patient_id>/`.
   Defaults to `<repo>/downloads/`. Set `COSMETIC_DATA_ROOT` if yours is
   elsewhere. Patient images are gitignored for privacy reasons — anyone
   reproducing this needs to supply their own dataset in that layout.
3. Backend dependencies installed (`cd backend && uv sync` or equivalent) — the
   C-condition path imports from `app.services.dashscope_diagnosis`.

## Running

```bash
# Default sample sheet
python run.py

# Custom sample sheet
python run.py --samples samples/freckle_focus.json

# Smoke test with 1 sample
python run.py --limit 1

# Build the side-by-side HTML report from a run directory
python build_report.py --run-dir results/default_2026-07-29T170000/
```

Each `python run.py` invocation creates a fresh timestamped run directory, so
concurrent runs never overwrite each other.

## Cost / latency notes

C condition is ~15x more expensive per call than A (roughly ¥0.66 vs ¥0.04)
because the 25k-token system prompt is billed on every request. Latency is
comparable (~20-30s each). The default sheet has 3 samples × 2 conditions =
6 VLM calls, so a full baseline run costs ~¥2 and takes 2-3 minutes.
