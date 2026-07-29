# Few-shot cases for facial diagnosis

These are the in-context learning examples appended to every diagnosis request.
Each case is a `(image, doctor-reviewed diagnosis JSON)` pair — the model learns
"front photo of this age/skin → this 27-zone JSON" by imitation.

## Current roster

| File stem | Age | Gender | Case theme |
|---|---|---|---|
| `case_young_female_maintenance` | 25 | female | Young face, mostly maintenance-only, isolated undereye concern |
| `case_mature_female_multizone` | 54 | female | Skin-texture + pigmentation dominant, multi-zone mild-to-moderate |

Both cases are doctor-reviewed gold labels; the metadata inside each JSON
(`patient_id`, dates) is retained for internal traceability but is not part of
the prompt payload sent to the model.

## Why these two

Leave-one-out design over the doctor-reviewed pool: keeps the age-severity
gradient anchored (25F extreme + 54F extreme), leaves any 45F case available
for held-out evaluation without contaminating the shots.

## Adding a new case

Register in `backend/app/services/vllm_diagnosis.py::_FEW_SHOT_CASES` with the
stem, age, and gender. Both the `.json` and `.png` are read by stem — keep the
names in sync.

Choose new cases to fill a *diagnostic gap* the current shots can't teach —
e.g. freckle-dominant pigmentation, structural aging with visible SAG, or a
male face. Adding a similar case to what already exists brings little value.
