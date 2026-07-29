# Sample sheets

Each JSON file in this directory describes **one evaluation set** — a fixed
list of patients to run the A-vs-C diagnosis-prompt ablation on.

## default.json — the project baseline

`default.json` is the **reference sample sheet** used to compare prompt
strategies over time. Composition is deliberately frozen; do not edit it
lightly, and do not commit changes to it without a written justification in
the accompanying commit message (e.g. "add freckle case to widen coverage").
Silently swapping samples across runs would make historical A/C comparisons
meaningless.

## Writing your own sample sheet

Copy `default.json` to a new filename that describes the intent, e.g.:

- `freckle_focus.json` — for testing whether few-shot handles heavy pigmentation
- `male_only.json` — for probing coverage gaps in male faces
- `smoke.json` — one sample only, for iterating on the runner itself

Each sample entry must contain:

| field | meaning |
|---|---|
| `patient_id` | folder name under `COSMETIC_DATA_ROOT/**/images_by_patient/` |
| `date` | which day's `_pre.png` to use (patient may have multiple visits) |
| `user_inputs.age` | age passed to the VLM prompt (mirrors `/preview` request) |
| `user_inputs.gender` | `"female"` / `"male"` / `null` |
| `notes` | freeform justification — why this patient is in the set |

## Running an evaluation with your sheet

```bash
# baseline (default.json)
python run.py

# your own sheet
python run.py --samples samples/freckle_focus.json
```

Results land in `results/<sheet_stem>_<timestamp>/` so different sheets never
overwrite each other.
