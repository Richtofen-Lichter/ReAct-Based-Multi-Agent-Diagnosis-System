# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Common Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Start infrastructure (Milvus + Redis + etcd + MinIO + Attu)
docker compose up -d

# Ingest knowledge base into Milvus
python scripts/ingest_kb_corpus.py --dry-run     # preview chunks
python scripts/ingest_kb_corpus.py --reset       # full rebuild

# Start all services (MCP servers + FastAPI) on Windows
powershell -NoProfile -ExecutionPolicy Bypass -File .\run.ps1

# Start only FastAPI (if MCP servers already running)
uvicorn app.main:app --host 0.0.0.0 --port 9900 --reload --reload-dir app

# Stop everything
powershell -NoProfile -ExecutionPolicy Bypass -File .\run.ps1 -Stop

# Integration tests (needs real LLM + Milvus)
python scripts/ingest_kb_corpus.py --reset --batch 8
python scripts/integration_test.py

# Benchmark: retrieval R@K (fast, no LLM)
python benchmark/run_benchmark.py retrieval --k 3

# Benchmark: RAGAS end-to-end (calls LLM, slower)
python benchmark/run_benchmark.py ragas --limit 5
```

**Frontend** (`frontend/`):
```bash
cd frontend && npm install
npm run dev      # Vite dev server (proxies /api to localhost:8000)
npm run build    # output to frontend/dist/ — FastAPI serves this as static files
```

## Architecture

This is a **Skill-Priority Multi-Agent AIOps Platform** — LangGraph + RAG + MCP for SRE incident diagnosis.

Two independent API flows, both SSE-streamed:
- **RAG Chat** (left lane): knowledge base Q&A with multi-turn memory
- **AIOps Diagnose** (right lane): plan-execute-replan graph → structured incident report

### Agent Graph (AIOps flow)

`app/agents/graph.py` — `build_aiops_graph()` defines the LangGraph StateGraph:

```
START → SkillRouter → Planner → Executor ⇄ Replanner → END
```

- **SkillRouter** (`app/skills/router.py`): LLM classifies the alert into one of 4 Skills (container/host_resource/network/generic). Falls back to 180+ keyword rules if LLM fails. Non-OnCall inputs return early.
- **Planner** (`app/agents/planner.py`): Generates 2-3 step diagnostic plan from the selected Skill's SOP playbook, using a flash model.
- **Executor** (`app/agents/executor.py`): Runs plan[0], calls whitelisted MCP tools. Read-only tools run in parallel (up to `executor_max_parallel`), write tools serialized at the tail. Each step's result appended to `past_steps`.
- **Replanner** (`app/agents/replanner.py`): 4-way decision — continue (fast-path skips LLM if ≥2 steps remain and last step succeeded), replan, reroute to another Skill, or produce final report. 5 code-level guardrails prevent Skill hopping loops.
- **Fork** (`app/agents/fork_runner.py`): Skills marked `context=fork` run in an isolated sub-graph to avoid context pollution.

State is `PlanExecuteState` TypedDict (`app/agents/state.py`) with reducer-based accumulation for `past_steps`, `transition_history`, and `tried_skills`.

### Services layer

- `app/services/aiops_service.py` — Wraps the graph in SSE event streaming: `start → skill_selected → plan → step_start → step_complete → replan → report → complete`
- `app/services/rag_service.py` — RAG chat orchestration: query rewrite → KB retrieve + web search (parallel) → LLM with optional MCP tools → SSE token stream
- `app/services/chat_memory.py` — Redis-backed session memory with TTL, compact/summarize, and cross-session context injection
- `app/services/rag/` — Sub-modules: retrieval (advanced_search wrapper), memory (Redis ops), web_context, prompts, utils

### Core layer

- `app/core/llm.py` — `get_chat_llm()` factory: model name prefix `qwen` → DashScope, `local_llm_force` → Ollama, default → DeepSeek. Automatic fallback probing.
- `app/core/embedding.py` — BAAI/bge-small-zh local embedding (512d), implements LangChain Embeddings interface with query-side instruction prefix
- `app/core/vector_store.py` — Milvus connection manager + `advanced_search()` 3-stage pipeline
- `app/core/hybrid_retriever.py` — In-memory BM25 index + RRF fusion; no jieba (BM25 targets English error codes / service names)
- `app/core/reranker.py` — BAAI/bge-reranker-base CrossEncoder; graceful degradation on failure
- `app/core/mcp_client.py` — `MultiServerMCPClient` manager; per-server loading with silent failure, ExceptionGroup unwrapping
- `app/core/milvus.py` — Milvus connection manager (separate from vector_store)

### Skill system

Skills are defined as `SKILL.md` files in `app/skills/definitions/<skill_name>/SKILL.md` — YAML frontmatter (name, triggers, allowed_tools, risk_level, context) + Markdown playbook body. `SkillRegistry` (`app/skills/registry.py`) scans on startup, `generic_oncall` acts as mandatory fallback.

### Permission model

`app/runtime/permissions.py` — 3-layer defense: Skill tool whitelist → PermissionMode (READ_ONLY/NORMAL/ASK_DESTRUCTIVE/BYPASS) → static blacklist. `ToolMeta` (`app/tools/meta.py`) records read_only, concurrency_safe, destructive, and input-aware effective_read_only for each tool.

### Configuration

`app/config.py` — Single Pydantic Settings class (~40+ env vars), accessed via `lru_cache` singleton `settings`. All tunables live in `.env`. Runtime validation checks for valid API key on startup.

### MCP servers

`mcp_servers/` — 5 standalone FastMCP servers exposing OS-level diagnostic tools via `streamable-http`: system (psutil), websearch, winlog (Windows Event Log), network (ping/traceroute), docker (container management). Each runs on its own port.

### Frontend

`frontend/` — Vue 3 + Vite SPA with SSE EventSource consumers. Key components in `frontend/src/components/`: `AiopsTab.vue` (diagnosis timeline with step cards and report rendering), `ChatTab.vue` (chat interface), `DocumentsTab.vue` (knowledge base management). Markdown reports rendered client-side.

### Key data paths

- Knowledge corpus: `data/kb_corpus/`
- Benchmark datasets: `benchmark/ragas_qa_50.jsonl`, `benchmark/retrieval_rk_50.jsonl`
- Alert history: `data/alert_history.jsonl`
- SOP documents: `docs/sop/`
- Docker volumes: `volumes/` (etcd, milvus, minio, redis)
- Logs: `logs/`

### LLM routing

Model selection happens by node, not globally:
| Node | Config key | Default model |
|---|---|---|
| Router | `deepseek_router_model` | deepseek-v4-flash |
| Planner | `agent_planner_model` | (falls back to deepseek_router_model) |
| Executor | `agent_executor_model` | (falls back to deepseek_chat_model) |
| Replanner | `agent_planner_model` | (falls back to deepseek_router_model) |
| Report | `agent_report_model` | (falls back to deepseek_chat_model → pro) |

This stratification keeps the most frequent nodes (Executor, Replanner) on flash models and reserves pro only for the final report synthesis.
