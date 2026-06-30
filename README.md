# Cosmetic — A Retrieval-Augmented LLM Agent

An open-source LLM agent for domain knowledge-base consultation, currently using cosmetic / aesthetic-medicine as the working domain. The project is an actively-developed sandbox for studying retrieval-augmented agent design — how to combine LangGraph orchestration, LlamaIndex retrieval, vector storage, and observability into a coherent agent that can hold non-trivial multi-turn consultations grounded in a real, messy knowledge base.

> The cosmetic-consultation domain is the working setting; the framework itself — the orchestration, retrieval pipelines, and observability — is the focus of the work.

---

## Why this project

Most public LLM-agent demos collapse under contact with a real knowledge base: retrieval is brittle, multi-turn state is dropped, and there is no easy way to inspect what the agent actually saw or said. This repo is a personal research sandbox to:

1. Build a production-grade RAG agent stack that is honest about its behavior (observability first).
2. Iterate on retrieval strategies and agent orchestration patterns against a non-trivial domain knowledge base.
3. Treat base-model choice as a swappable variable, so the same agent can be exercised across multiple open-weight LLMs.

The design choices here are deliberately influenced by recent work on retrieval-augmented generation and agent systems, including LightRAG (graph-augmented retrieval), RAG-Anything (multimodal retrieval), AutoAgent (zero-code agent orchestration), and the broader LangGraph / LlamaIndex ecosystem.

---

## What's in the repo

| Component | Purpose |
|---|---|
| `backend/` | FastAPI service, LangGraph agent orchestration, LlamaIndex retrieval pipelines, Langfuse instrumentation |
| `frontend/` | Next.js 14 + Vercel AI SDK streaming UI |
| `infra/` | Docker Compose for PostgreSQL + pgvector + Redis + Langfuse |
| `docs/` | Design document and staged execution roadmap |

---

## Tech stack

- **Agent orchestration**: [LangGraph](https://github.com/langchain-ai/langgraph)
- **Retrieval**: [LlamaIndex](https://github.com/run-llama/llama_index) on PostgreSQL + [pgvector](https://github.com/pgvector/pgvector)
- **LLMs**: DeepSeek V4 (primary), Qwen2.5 (secondary) — behind a provider-agnostic abstraction so the base-model choice is swappable
- **Observability**: [Langfuse](https://github.com/langfuse/langfuse) for end-to-end LLM tracing
- **Cache / rate-limit**: Redis
- **Frontend**: Next.js 14 + Vercel AI SDK (streaming)
- **Infrastructure**: Docker Compose; Phase-0 setup is reproducible from a fresh machine

---

## Status

This project is **under active development**.

- **Phase 0 — local infrastructure**: complete (see setup section below)
- **Phase 1 — agent + RAG pipeline**: in progress
- Further phases planned in `docs/roadmap.md`

---

## Phase 0: Local infrastructure setup

### Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop) (with Docker Compose v2)
- ≥ 5 GB free disk
- On Windows: WSL2 enabled

### Quick start

```bash
# 1) Copy the example environment file
cp .env.example .env

# 2) (Optional) edit passwords / ports in .env

# 3) Bring up the full local stack
docker compose up -d

# 4) Check status
docker compose ps

# 5) Tail logs (example: Langfuse)
docker compose logs -f langfuse
```

### Service endpoints

| Service | Address | Purpose |
|---|---|---|
| PostgreSQL | `localhost:5432` | Application data + pgvector store |
| Redis | `localhost:6379` | Cache + rate-limit |
| Langfuse | http://localhost:3000 | LLM tracing UI (sign up on first visit) |

### Verify the install

```bash
# Postgres: confirm pgvector is enabled
docker exec -it cosmetic-postgres psql -U cosmetic -d cosmetic -c "\dx"

# Redis: ping
docker exec -it cosmetic-redis redis-cli ping
```

Expected:

- Postgres lists a `vector` extension
- Redis returns `PONG`
- http://localhost:3000 shows the Langfuse login page

### Tear down

```bash
docker compose stop          # stop containers, keep data
docker compose down          # remove containers, keep data volumes
docker compose down -v       # full wipe, including data volumes (careful)
```

---

## Project structure (top level)

```
Cosmetic/
├── backend/                # FastAPI + LangGraph + LlamaIndex
├── frontend/               # Next.js 14
├── infra/postgres/init/    # pgvector + schema bootstrap
├── docs/                   # design.md, roadmap.md
├── .env.example
├── docker-compose.yml
└── README.md
```

---

## Author

Wenyao Jin — [github.com/wenyaojin](https://github.com/wenyaojin) · jinwenyao2014@gmail.com

This work is part of an independent PhD-preparation research program, informally mentored by Prof. Ling Shao.

Collaborators: *(to be added)*

---

## License

To be added.
