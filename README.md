# Reveal — A Multimodal AI Agent for Cosmetic-Medicine Consultation

A research sandbox for building a cosmetic-medicine consultation agent that
can both **look at a patient's face** and **retrieve grounded answers from a
domain knowledge base**. The two capabilities live side-by-side today: a
visual diagnosis pipeline that turns a front photo into a 27-zone diagnosis
plus a post-treatment simulation, and a retrieval-augmented consultation
agent that answers text questions with citations from a curated aesthetic-
medicine knowledge base.

The eventual product target is a session where these meet — the diagnosis
result becomes context that steers the consultation retrieval, so what the
agent *sees* on the face drives what it *says* about treatment options.
Wiring them together is the next research direction; each capability is
independently runnable today.

---

## Why this project

Most public LLM-agent demos collapse under contact with a real medical
domain: retrieval is brittle, image understanding is skin-deep, and the
outputs are neither trustworthy for a doctor nor safe for a patient. This
repo is a personal research sandbox to build both halves honestly:

1. A vision path that produces **doctor-audit-shaped** diagnoses instead
   of beauty-app template descriptions.
2. A retrieval path with observability first, so every citation is traceable.
3. A codebase where prompts, few-shot cases, and evaluation experiments are
   first-class artifacts (not scratchpad files), so results are reproducible
   from a fresh clone.

---

## Two capabilities today

### Capability 1 — Visual diagnosis pipeline

Endpoint: `POST /api/v1/treatment-preview` · UI: `/preview` route on the
Next.js frontend.

```
front photo (+ optional age/gender)
  → qwen-vl-max      : 27-zone facial diagnosis JSON (2-shot doctor cases)
  → qwen-image-edit  : per-zone post-treatment simulation image
  → renderer         : 5-page Markdown consultation report
```

The prompt strategy — a 25 KB system prompt + two doctor-reviewed few-shot
cases — is the load-bearing part. Ablation results in
[`evals/diagnosis_prompt_ablation/`](evals/diagnosis_prompt_ablation/):

| Question | A (naive prompt) | C (production few-shot) |
|---|---|---|
| Diagnosis grounded in the photo? | Template-driven; over-called "sagging / pigmentation" on faces that had neither | Confined to what's actually visible in all 3 held-out cases |
| Coverage of real issues | Missed the "round-face bone/fat" structural axis and the mature freckle case | Identified both, and flagged unseen zones as `pending_side_view` / `pending_dynamic_view` |
| Usable downstream? | Free-text only; can't drive per-zone image editing or per-part recommendations | JSON keyed by 27 zones with severity + problem-type codes → drives image-edit prompts and per-zone reports directly |

Same VLM, same photos, same sampling params — the prompt strategy is doing
the work. Full side-by-side with per-case verdicts is regenerable via
`python evals/diagnosis_prompt_ablation/run.py`.

A **fixture branch** (`use_fixture: "patient_dff3abf1"` in the request body,
served from `backend/app/fixtures/`) bypasses the ~200 s live path and
returns a canned response in ~50 ms — used for advisor demos and CI. It's
gated off in production (`APP_ENV=production` → 403).

### Capability 2 — RAG consultation agent

Endpoint: `POST /api/v1/agent/chat` (or `/chat/stream` for SSE) · UI: main
chat page on the Next.js frontend.

A 6-node LangGraph state machine grounds every reply in the aesthetic-
medicine knowledge base:

```
vision_extract → intake → safety_gate → retrieve → risk_assessment → recommend
```

The retrieval stage is a **custom hybrid pipeline** written directly against
`pgvector` and `BM25Okapi`, with four independently toggleable enhancements
for ablation studies (`use_query_rewrite`, `use_hyde`, `use_small_to_big`,
`use_structured_kb`). Every LLM call is traced end-to-end through Langfuse,
so citations, retrieved chunks, and generation prompts are inspectable.

---

## Tech stack

- **Agent orchestration**: [LangGraph](https://github.com/langchain-ai/langgraph)
  (typed state machine, 6 nodes)
- **Retrieval**: custom hybrid pipeline over PostgreSQL +
  [pgvector](https://github.com/pgvector/pgvector), Chinese BM25 via jieba +
  `rank_bm25`, `bge-reranker-v2-m3` cross-encoder rerank
- **Vision**: DashScope `qwen-vl-max` (diagnosis) + `qwen-image-edit`
  (post-op simulation)
- **LLMs**: DeepSeek V4 (primary) and Qwen (secondary), behind a
  provider-agnostic client so the base model is a swappable variable
- **Observability**: [Langfuse](https://github.com/langfuse/langfuse)
- **Frontend**: Next.js 15 + shadcn/ui (chat page + `/preview` page)
- **Infra**: Docker Compose (Postgres + pgvector + Redis + Langfuse), one
  command to a reproducible local stack

---

## Status

- **Phase 0** — local infrastructure: complete
- **Phase 1** — RAG consultation pipeline: shipped, ablation-instrumented
- **Visual diagnosis PoC** (2026-07): E2E `/preview` flow shipped; A-vs-C
  prompt ablation validated
- **Next** — connecting the two: use the diagnosis result as retrieval
  context so the RAG agent can talk specifically about the zones the VLM
  flagged. Doctor-labeled cases are being collected to make this jump
  from "prompt-engineered PoC" to "trainable"; see `docs/roadmap.md`.

---

## Repo layout

```
Reveal/
├── backend/                   FastAPI, LangGraph agent, treatment-preview pipeline
│   ├── app/
│   │   ├── agent/             6-node LangGraph orchestration
│   │   ├── routers/           HTTP layer (chat, agent, diagnosis, treatment_preview, …)
│   │   ├── services/          RAG, VLM diagnosis, treatment preview, report renderer
│   │   ├── prompts/           Diagnosis system prompt + doctor-reviewed few-shot cases
│   │   ├── fixtures/          Canned responses for the demo backdoor
│   │   └── core/              Config, DB, LLM/embedding/reranker clients, observe
├── frontend/                  Next.js 15 (chat page + /preview page)
├── evals/                     Reproducible experiments
│   └── diagnosis_prompt_ablation/  A vs C prompt strategy ablation
├── infra/                     Postgres bootstrap + nginx config
├── knowledge/                 Curated aesthetic-medicine documents
├── docs/                      design.md, roadmap.md
├── docker-compose.yml
└── README.md
```

Patient photos and any downloaded datasets live under `downloads/` (git-
ignored for privacy). Point `COSMETIC_DATA_ROOT` at your own dataset if you
want to run the evals against a different set.

---

## Quick start

### 1. Bring up the local infrastructure

```bash
cp .env.example .env          # optionally edit passwords / ports
docker compose up -d
docker compose ps             # confirm postgres, redis, langfuse are up
```

Endpoints when up:

| Service | Address |
|---|---|
| PostgreSQL | `localhost:5432` |
| Redis | `localhost:6379` |
| Langfuse UI | http://localhost:3000 |

### 2. Run backend + frontend

```bash
cd backend  && uv sync && uvicorn app.main:app --reload
cd frontend && bun install && bun dev
```

### 3. Try each capability

- **Visual diagnosis** — open the frontend `/preview` page, check
  "使用预置样例" (fixture backdoor) → returns in ~2 s with a full before/
  after + diagnosis + report. Uncheck it and upload a photo for the ~200 s
  live path (requires `DASHSCOPE_API_KEY`).
- **RAG consultation** — main chat page, ask an aesthetic-medicine question.
  Every reply carries citations back to the underlying knowledge chunks.

### 4. Reproduce the diagnosis-prompt ablation

```bash
export DASHSCOPE_API_KEY=...
cd evals/diagnosis_prompt_ablation
python run.py                                       # runs default 3-sample sheet
python build_report.py --run-dir results/default_*/ # renders side-by-side HTML
```

Full write-up in [`evals/diagnosis_prompt_ablation/README.md`](evals/diagnosis_prompt_ablation/README.md).

---

## Author

Wenyao Jin — [github.com/wenyaojin](https://github.com/wenyaojin) ·
jinwenyao2014@gmail.com

Independent PhD-preparation research program, informally mentored by
Prof. Ling Shao. Collaborators: *(to be added)*

## License

To be added.
