# Developer Specification

## 目录

- 1. 项目概述
- 2. 核心特点
- 3. 技术选型
  - 3.1 多智能体诊断架构
  - 3.2 RAG 检索流水线
  - 3.3 MCP 工具生态集成
  - 3.4 Skill 技能系统
  - 3.5 API 接口设计
  - 3.6 权限与安全模型
  - 3.7 流式响应与可观测性
- 4. 测试方案
- 5. 系统架构与模块设计
- 6. 项目排期
- 7. 可扩展性与未来展望

---

## 1. 项目概述

### 项目定位

**MultiAgentAIOps** — 企业级多智能体智能运维诊断平台，基于 LangGraph + RAG + MCP 技术栈构建。

本项目是一个面向 SRE 运维场景的 AI Agent 系统：接收告警描述或故障现象，自动检索知识库、调用 MCP 诊断工具收集实时数据，经多智能体协作推理后产出结构化的诊断报告，全程流式反馈到前端。

### 核心使命

> 从"告警驱动"到"证据驱动诊断" — 让 AI Agent 完成从 Skill 选择 → 计划制定 → 工具取证 → 评估调整 → 报告输出的完整闭环。

### 设计理念

- **多智能体协作**：Skill Router / Planner / Executor / Replanner 四节点接力，各司其职、可独立替换
- **证据驱动决策**：每个诊断结论都必须引用工具返回的真实数据（指标、日志、SOP），杜绝 LLM 凭空编造
- **弹性降级优先**：每一层（LLM、Vector Store、MCP Reranker）都有独立的降级策略，单点故障不阻断整体流程
- **流式可观测**：诊断全过程的每个决策点都通过 SSE 实时推送到前端，形成结构化时间线

### 技术栈概要

| 层级 | 技术选型 |
|------|---------|
| Agent 编排 | LangGraph (StateGraph + Plan-Execute-Replan) |
| LLM Provider | DeepSeek (默认) + DashScope 千问 (备选) + Ollama 本地 (兜底) |
| Embedding | BAAI/bge-small-zh (512d, 本地 CPU) |
| 向量数据库 | Milvus (HNSW + COSINE) |
| 混合检索 | BM25 (rank_bm25) + Dense Vector + RRF 融合 |
| 重排序 | BAAI/bge-reranker-base (CrossEncoder, 本地) |
| MCP 工具 | langchain-mcp-adapters MultiServerMCPClient |
| API 框架 | FastAPI + SSE (sse-starlette) |
| 会话记忆 | Redis (多轮对话 + 摘要压缩) |
| 前端 | Vite + 原生 JS (SSE EventSource 消费) |

---

## 2. 核心特点

### 2.1 多智能体协作架构

摒弃单 Agent ReAct 循环，采用 LangGraph 有向图编排的多智能体协作模式：

```
[START] → SkillRouter → Planner → Executor → Replanner → [END]
                         ↑            │           │
                         └── reroute ──┘           │
                                                   └── continue
```

- **SkillRouter**：LLM 结构化路由 + 关键词规则二维兜底，从 Skill 矩阵中选择最匹配的诊断方向
- **Planner**：基于选中 Skill 的标准 Playbook，用快模型 (flash) 生成 2-3 步诊断计划
- **Executor**：执行 plan[0]，按 ToolMeta.concurrency_safe 切批实现 read-only 工具并行编排（cc-haha §3 借鉴）
- **Replanner**：评估证据充分性 → 四向决策（继续 / 调计划 / 切 Skill / 出报告）

### 2.2 混合检索 + 精排 RAG

```
用户 query → Vector top-20 → [Hybrid: BM25 + RRF] → [Rerank: CrossEncoder] → top-3 → LLM
```

每一层均可通过 `.env` 配置独立开关，任一环节故障自动降级到上一层结果：

- **粗排 (Vector + BM25)**：BGE Embedding 语义向量 + rank_bm25 关键词匹配，两路 top-20 经 RRF (k=60) 融合
- **精排 (Rerank)**：BGE CrossEncoder 逐对打分（50-200ms/对），把 20 份候选压缩到 3 份精品
- **自动降级链**：Rerank 不可用 → 纯 Hybrid；Hybrid 不可用 → 纯 Vector；Vector 异常 → 返回空

### 2.3 MCP 协议工具生态集成

对接 5 个 MCP Server 提供的诊断工具（system / websearch / winlog / network / docker），通过 langchain-mcp-adapters 统一加载。Graceful degradation：任意一个 Server 握手失败不影响其余工具的加载与使用。

### 2.4 SSE 流式诊断实时反馈

AIOps 诊断不等待全量结果，而是通过 SSE 将 8 种事件类型（start / skill_selected / plan / step_start / step_complete / replan / report / complete）逐步推送到前端。用户可在几秒内看到 Skill 选择结果，随后逐步看到工具调用进度和最终报告。

### 2.5 三层权限防御模型

借鉴 cc-haha 设计思路，实现"Skill 白名单 → PermissionMode 限制 → Guardrails 黑名单"三层防御。支持 4 种运行时模式（READ_ONLY / NORMAL / ASK_DESTRUCTIVE / BYPASS），工具权限支持输入感知（如 Bash(ls) 只读、Bash(rm) 不只读）。

### 2.6 Alertmanager Webhook 自动触发

对接 Prometheus Alertmanager v4 Webhook，接收 `firing` 告警后立即返回 200 ACK，后台异步启动完整 AIOps 诊断流程，诊断报告写入 `data/alert_history.jsonl`，支持历史回溯。

### 2.7 多 LLM Provider 可插拔

通过 `get_chat_llm()` 工厂函数实现：模型名以 `qwen` 开头自动切 DashScope；`local_llm_force=True` 强制走本地 Ollama；主 LLM 不可达时自动探活并降级到本地模型。

### 2.8 多轮对话会话记忆

Redis 存储会话摘要 + 最近消息，支持多轮指代消歧（query rewrite）、自动摘要压缩（compact）和 TTL 自动过期。RAG Chat 可跨会话读取最近的 AIOps 诊断报告，实现"刚才那个 vmmem 是什么"的指代追问。

---

## 3. 技术选型

### 3.1 多智能体诊断架构

#### 3.1.1 编排引擎：LangGraph StateGraph

选定 LangGraph 而非自研 DAG 引擎的理由：

- **原生 conditional edge 支持**：Replanner → Executor / Planner / END 三向路由，天然匹配诊断流程的不确定性
- **TypedDict State**：`PlanExecuteState` 定义清晰，所有字段可追溯
- **operator.add reducer**：`past_steps` 和 `transition_history` 自动累加，无需手动合并

核心文件：`app/agents/graph.py` — `build_aiops_graph()` 函数

```python
workflow = StateGraph(PlanExecuteState)
workflow.add_node("skill_router", skill_router_node)
workflow.add_node("planner", plan_node)
workflow.add_node("executor", execute_node)
workflow.add_node("replanner", replan_node)
workflow.add_node("fork_skill", fork_skill_node)  # §4 cc-haha

workflow.add_conditional_edges("replanner", should_end, {
    "executor": "executor",
    "planner": "planner",   # Skill reroute
    END: END,
})
```

#### 3.1.2 状态设计

`PlanExecuteState` (TypedDict, `app/agents/state.py`):

| 字段 | 类型 | Reducer | 说明 |
|------|------|---------|------|
| input | str | 覆盖 | 用户原始问题 |
| selected_skill | str | 覆盖 | Router 选中的 Skill name |
| plan | List[str] | 覆盖 | 待执行步骤列表 (Replanner 更新) |
| past_steps | List[Tuple] | operator.add | 已执行 (步骤, 结果) 累加 |
| response | str | 覆盖 | 最终报告 (非空触发 END) |
| iteration | int | 覆盖 | 当前步数 (防死循环) |
| transition_history | List | operator.add | 结构化时间线 (cc-haha §6) |
| tried_skills | List | operator.add | 已试 Skill + 失败原因 (NeurIPS 2025) |
| pending_reroute | bool | 覆盖 | 临时标记，带回 Planner |

#### 3.1.3 结构化输出

Planner 产出的 `Plan` 和 Replanner 产出的 `Act` 均使用 Pydantic BaseModel + `with_structured_output()` 保证类型安全，不依赖脆弱的 JSON 解析。

`Act` 模型 (Replanner 决策) 采用单一 schema + bool discriminator 设计：

```python
class Act(BaseModel):
    is_finished: bool         # True → 发报告, False → 继续/reroute
    plan: List[str]           # 剩余步骤
    response: str             # 最终报告 Markdown
    should_reroute: bool      # 是否提议切 Skill
    new_skill: str            # 要切到的 Skill name
    reroute_reason: str       # 证据+原因
```

**设计原因**：原始 LangGraph Plan-Execute 教程使用 `Union[Response, Plan]`，但部分模型（通义千问）对 Union 兼容不佳（返回字符串而非对象），改用单一 schema + bool discriminator 解决。

#### 3.1.4 防死循环机制

三层防护：

1. **Prompt 层**：要求单次诊断控制在 3 步以内收尾
2. **代码层**：`iteration > settings.agent_max_steps` (默认 5) 强制终止
3. **兜底层**：LLM 结构化输出失败 → `_force_summary()` 模板生成报告

#### 3.1.5 Skill Reroute（Supervisor + Handoff 保守版）

Replanner 可在证据表明"当前 Skill 方向错了"时提议切换 Skill，切换到 Planner 重新出计划。

代码层校验门槛（`_validate_reroute`）：

1. `past_steps >= agent_reroute_min_past_steps`（默认 2 步，证据不足不允许切）
2. `reroute_count < agent_max_reroutes`（默认 1 次，防止反复横跳）
3. new_skill 不等于当前 skill（防自循环）
4. new_skill 不在 tried_skills 黑名单（防回环）
5. new_skill 在 SkillRegistry 中真实存在

参考：LangGraph Supervisor + Handoff + NeurIPS 2025 "failure memory"

#### 3.1.6 快路径优化 (Fast Path)

`agent_replanner_fast_path_threshold` (默认 2)：当计划还剩 ≥2 步且上一步未失败时，跳过 Replanner LLM 调用，直接进入下一步。因为计划设计时已留冗余，中间步骤没必要每步都 re-evaluate；Replanner 一次 LLM 调用约 1-3s，跳过可显著缩短诊断延迟。

#### 3.1.7 模型分层策略

不同节点使用不同模型，兼顾质量与延迟：

| 节点 | 模型 | 配置项 | 理由 |
|------|------|--------|------|
| SkillRouter | deepseek_router_model (flash) | — | 选 Skill 不需要深度推理 |
| Planner | agent_planner_model (flash) | — | 结构化输出 (Plan)，快模型即可 |
| Executor | agent_executor_model (flash) | 推荐配 flash | 每步都调 LLM，是延迟瓶颈，压到 1-2s |
| Replanner | agent_planner_model (flash) | — | 决策只看进度，不需要 pro 推理力 |
| 报告合成 | agent_report_model (pro) | 默认 deepseek_chat_model | 唯一需要高质量输出的环节 |

设计要点：Replanner 用 flash 做快速决策 → `is_finished=True` → 单独调 `_synthesize_final_report()` 用 pro 写 5 段报告。质量/速度两头兼顾。

#### 3.1.8 Fork 模式（cc-haha §4 借鉴）

部分 Skill 标记 `context=fork`（如写长报告、联网研究），走独立子图隔离执行，避免污染主线上下文。入口节点 `fork_skill_node` → 内部再跑完整的 `build_aiops_graph()` 子图 → 只回传最终报告。

### 3.2 RAG 检索流水线

#### 3.2.1 文档摄取

**入口**：`POST /api/v1/documents/upload`

**流程**：

```
Markdown/Text 文件 → H1/H2/H3 标题分块 → 字符子分块 (chunk_size=800, overlap=100)
→ BGE Embedding (512d) → Milvus upsert
```

- **分块策略**：`app/utils/splitter.py` 使用标题层级分块 + 字符二级分块，而非纯定长切分。按 H1/H2/H3 标题先拆大块，再在每块内按 `rag_chunk_size` 做字符子切（保留 `rag_chunk_overlap` 重叠），确保每个 Chunk 是自包含的语义单元
- **文档删除**：按 `source` 字段从 Milvus 中删全部 chunks + 触发 BM25 索引重建

#### 3.2.2 Embedding 方案

**选型**：BAAI/bge-small-zh (512 维)，本地 CPU 推理

| 考量 | 决策 |
|------|------|
| 为什么本地 | 零 API 成本、无网络依赖、离线可用 |
| 为什么 BGE | 中文语义理解优秀、社区活跃、与 bge-reranker 同家族 |
| 为什么 small (512d) | 开发期够用，显存/磁盘占用小，后续可平滑升级到 large (1024d) |
| Query/Doc 编码差异 | BGE 要求 query 侧加 instruction prefix `"为这个句子生成表示以用于检索相关文章："`，doc 侧不加 |

核心实现：`app/core/embedding.py` — `_BGEEmbeddings` 类，实现 LangChain `Embeddings` 接口

#### 3.2.3 向量存储：Milvus

选择 Milvus 而非 Chroma/Pinecone 的理由：

- 生产级 HNSW 索引，支持百万级向量
- 原生支持多字段 payload（content + source + chapter）
- Docker 部署简单，与项目运维场景契合
- `langchain-milvus` 提供 LangChain VectorStore 标准接口

配置字段：`MILVUS_HOST`, `MILVUS_PORT=19530`, `MILVUS_COLLECTION=multi_agent_kb`

索引参数：HNSW + COSINE，`M=8, efConstruction=64, ef=32`

**双 API 兼容**：`langchain-milvus 0.3+` 用 `MilvusClient` (新 API)，底层 `_extract_fields()` 又用了 `pymilvus.orm.Collection` (旧 API)。当前通过把同一 alias 同时注册到两个连接注册表解决。

#### 3.2.4 Hybrid Search：BM25 + Vector + RRF

**设计动机**（`app/core/hybrid_retriever.py` docstring）：

- 纯向量检索对精确 token 匹配会失效（如 `ERR_CONN_REFUSED`、`redis.exception.TimeoutError`）
- BM25 不依赖语义，对固定字符串/错误码/服务名精确命中
- 两者互补，RRF 融合后 recall 通常提升 5-15%（bswen 2026 / Anthropic 实测）

**实现要点**：

| 组件 | 实现 |
|------|------|
| 分词 | 自定义轻量分词：英文/数字按 token 切（保留 dot/dash/underscore），中文按单字。无需 jieba |
| BM25 算法 | rank_bm25 库（BM25Okapi） |
| 融合算法 | RRF (k=60, TREC 经典值)，`Score = Σ weight_i / (60 + rank_i)` |
| BM25 权重 | `rag_hybrid_bm25_weight=0.4`（语义 0.6, 关键词 0.4） |
| 索引 | 纯内存构建（从 Milvus 拉全量 chunks），上传/删除后自动刷新 |

**中文不用 jieba 分词的理由**：向量检索已覆盖中文语义，BM25 的核心价值是"捕获向量漏掉的精确 token"（基本都是英文/数字/错误码）。按字切 + 英文按空格切已够用。省掉 jieba 依赖（几 MB + 词典加载耗时）。

#### 3.2.5 Rerank：CrossEncoder 精排

**选型**：BAAI/bge-reranker-base (CrossEncoder)，本地 CPU 推理

工作流程：
1. 加载 CrossEncoder 模型（首次加载 ~1GB，后续走 `lru_cache` 单例）
2. 构造 (query, doc) 对
3. 逐对打分 → 按分数降序排列
4. 为每个 doc 附加 `metadata["rerank_score"]`

**降级策略**：模型加载失败 / 推理异常 / 解析异常 → 直接返回原始 docs 的 top_n 项，不抛异常。

**为什么是 CrossEncoder 而非 LLM Rerank**：
- 本地推理零 API 成本
- 延迟可控（50-200ms/对 × 20 对 = 1-4s）
- 与 BGE Embedding 同家族，语义空间对齐

#### 3.2.6 高级检索流水线

`app/core/vector_store.py` — `advanced_search()` 函数：

```
advanced_search(query, k=3):
  1. Vector top-20 (rag_retrieve_k)
  2. [Hybrid] BM25 top-20 + RRF 融合 → top-20
  3. [Rerank] CrossEncoder 精排 → top-3
  每一步都可通过 settings 独立开关；失败自动降级到上一层
```

配置开关：

| 参数 | 默认 | 说明 |
|------|------|------|
| `rag_hybrid_enabled` | True | Hybrid Search 开关 |
| `rag_rerank_enabled` | True | Rerank 开关 |
| `rag_retrieve_k` | 20 | 送进 Reranker 前的候选数 |
| `rag_top_k` | 3 | 最终送给 LLM 的 top-k |
| `rag_hybrid_bm25_weight` | 0.4 | BM25 在 RRF 中的权重 |

### 3.3 MCP 工具生态集成

#### 3.3.1 架构设计

本项目作为 **MCP Client**（而非 Server），通过 `langchain-mcp-adapters` 的 `MultiServerMCPClient` 连接远程 MCP Server，获取诊断工具供 Agent Executor 调用。

5 个 MCP Server 的 transport 均为 `streamable-http`：

| Server | 用途 | 端口 |
|--------|------|------|
| system | 本机系统指标 (psutil: CPU/内存/进程/磁盘) | 8005 |
| websearch | 联网搜索补充 | 8006 |
| winlog | Windows 事件日志查询 | 8008 |
| network | 网络诊断 (ping/traceroute/端口检查) | 8009 |
| docker | Docker 容器管理 (list/logs/stats/restart) | 8011 |

#### 3.3.2 Graceful Degradation

启动时逐 server 加载工具，单点失败不影响其余：

```python
for name in servers.keys():
    tools = await _load_one(name, retries=1, retry_delay=0.5)
    if tools is None:
        failed.append(name)
    else:
        all_tools.extend(tools)
```

设置 `fail_silently=True`（默认）：MCP 初始化失败仅 warning，应用以无 MCP 工具模式继续运行。fail_silently=False 时抛异常阻止启动（生产推荐）。

#### 3.3.3 ExceptionGroup 展开

`langchain-mcp-adapters 0.2.x` 的 `get_tools()` 底层用 `anyio.TaskGroup` + `asyncio.gather`（无 `return_exceptions`），任意一个 server 失败会把整批拒绝，外层只能看到黑盒 `ExceptionGroup`。本项目通过 `_format_exc()` 递归展开 ExceptionGroup 叶子异常，逐行打印根因。

#### 3.3.4 Lazy Tools 模式（可选）

`mcp_lazy_tools_enabled=True` 时启用两阶段发现/执行：先用元工具 `mcp_search_tools` 浏览可用工具列表，再用 `mcp_execute_tool` 按需调具体工具。默认关闭（MCP 工具直接 bind 给 LLM，单轮即可调用，减少额外 LLM round）。

#### 3.3.5 工具元数据注册

`app/tools/meta.py` — `ToolMeta` 数据类 + `ToolRegistry` 全局注册表。每个工具登记：

| 字段 | 说明 |
|------|------|
| name | 工具名 |
| read_only | 是否只读 |
| concurrency_safe | 是否可并行调用 |
| destructive | 是否为破坏性写操作 |
| is_notification | 是否为通知类操作 |
| read_only_for_input | 哪些入参使工具表现为只读（如 Bash(ls) 只读） |

### 3.4 Skill 技能系统

#### 3.4.1 设计理念

Skill 是领域诊断知识的封装单元。每个 Skill 定义了一种故障类型的标准排查思路（Playbook），并声明了允许 Executor 使用的工具白名单。

#### 3.4.2 文件格式

`app/skills/definitions/<skill_name>/SKILL.md` — YAML frontmatter + Markdown body：

```markdown
---
name: host_resource_diagnosis
display_name: 主机资源诊断 (CPU/内存/磁盘)
description: 主机/容器 CPU 高、内存高/OOM、磁盘满、本机卡顿等资源类故障
triggers: [cpu 高, 内存高, 磁盘满, oom, 我电脑]
allowed_tools: [search_knowledge_base, get_local_cpu_memory, ...]
risk_level: low
context: inline
---

# CPU 高使用率排查
## 适用场景
...
## 推荐排查步骤
1. ...
## 输出格式
...
```

**Pydantic 模型**：`app/skills/models.py` — `Skill` BaseModel

| 字段 | 类型 | 说明 |
|------|------|------|
| name | str | snake_case 唯一标识 |
| display_name | str | 人类可读名称 |
| description | str | 适用场景一句话 |
| triggers | List[str] | 触发关键字（Router 提示用） |
| allowed_tools | List[str] | 工具白名单（硬墙） |
| risk_level | Literal["low","medium","high"] | 风险等级 |
| context | Literal["inline","fork"] | 执行模式 |
| fork_max_iters | int | fork 子图最大循环次数 |
| playbook | str | 完整 Markdown body |

#### 3.4.3 Skill Registry

`app/skills/registry.py` — `SkillRegistry` 类：

- 启动时扫描 `definitions/*/SKILL.md`，加载为 Skill 实例
- `lru_cache(maxsize=1)` 进程级单例
- 强制要求兜底 Skill `generic_oncall` 存在（Router 选不出来时回退）
- `to_router_menu()` 生成给 LLM 看的 Markdown 菜单

**已内置 4 个 Skill**：

| Skill | 场景 |
|-------|------|
| `container_diagnosis` | 容器/应用 高延迟、错误率、Pod 重启、镜像拉取失败 |
| `host_resource_diagnosis` | CPU/内存/磁盘/本机卡顿 |
| `network_diagnosis` | 网络连通性、DNS 解析、端口可达性、延迟抖动 |
| `generic_oncall` | 兜底，覆盖未被精确匹配的 OnCall 问题 |

#### 3.4.4 Skill Router 路由策略

`app/skills/router.py` — `skill_router_node()`：

两层路由机制：

1. **LLM structured output** (主)：用快模型 + `SkillChoice` schema 在 Registry 中选一个 name，输出置信度 + 一句话理由
2. **关键词规则兜底** (备)：LLM 调用失败时，基于 180+ 中文运维关键词 (`_ONCALL_KEYWORDS`) 和 15 个排除关键词 (`_OUT_OF_SCOPE_KEYWORDS`) 做规则判断

兜底原则：任何异常都不能阻塞流程，永远有一个可用的 Skill（回退到 `generic_oncall`）。

非 OnCall 输入（动漫、游戏、天气等）会被 Router 识别后直接结束，不浪费后续 Agent 资源。

### 3.5 API 接口设计

#### 3.5.1 整体设计

- 框架：FastAPI
- 版本前缀：`/api/v1`
- 响应格式：统一 `ApiResponse[T]` 泛型包装
- 流式：SSE (Server-Sent Events) via `sse-starlette`
- 文档：`/docs` (Swagger) + `/redoc` (ReDoc) + `/openapi.json`
- 端口：9900

#### 3.5.2 端点总览

| Method | Path | 说明 | 响应类型 |
|--------|------|------|----------|
| GET | `/api/v1/health` | K8s Liveness 探针 | ApiResponse |
| GET | `/api/v1/health/ready` | K8s Readiness 探针 (含 Milvus) | ApiResponse / 503 |
| POST | `/api/v1/chat/stream` | RAG 流式聊天 | SSE |
| GET | `/api/v1/chat/sessions/{id}/history` | 查看会话历史 | dict |
| DELETE | `/api/v1/chat/sessions/{id}` | 清空会话记忆 | dict |
| POST | `/api/v1/aiops/diagnose` | AIOps 多智能体诊断 | SSE |
| POST | `/api/v1/documents/upload` | 上传知识库文档 (需 Admin Token) | ApiResponse |
| GET | `/api/v1/documents` | 列出已索引文档 | ApiResponse |
| DELETE | `/api/v1/documents/{source}` | 删除指定文档 (需 Admin Token) | ApiResponse |
| GET | `/api/v1/skills` | 列出已注册 Skill | ApiResponse |
| POST | `/api/v1/webhook/alertmanager` | 接收 Alertmanager 告警 | dict |
| GET | `/api/v1/webhook/history` | 查看告警诊断历史 | dict |
| DELETE | `/api/v1/webhook/history` | 清空告警诊断历史 | dict |

#### 3.5.3 统一响应格式

```json
// 成功
{ "code": "SUCCESS", "message": "ok", "data": {...}, "request_id": "uuid" }

// 失败
{ "code": "ERROR_CODE", "message": "描述", "data": {"code": "...", "message": "...", "detail": ...}, "request_id": "uuid" }
```

`ApiResponse[T]` 泛型类 (`app/schemas/common.py`)：
- `ApiResponse.success(data, message)` — 工厂方法
- `ApiResponse.error(code, message, detail)` — 工厂方法

#### 3.5.4 全局异常处理

三层异常处理器（`app/main.py`）：

| 异常类型 | 状态码 | 说明 |
|----------|--------|------|
| AppException 及其子类 | 400/404/500/503 等 | 业务异常，code 和 detail 透传 |
| RequestValidationError | 422 | Pydantic 校验失败，detail 含具体字段 |
| Exception (兜底) | 500 | 未预料的内部错误，debug=True 时暴露详情 |

AppException 子类体系 (`app/exceptions.py`)：

```
AppException
├── BadRequestError (400)
├── NotFoundError (404)
│   └── DocumentNotFoundError (404)
├── UnsupportedFileTypeError (400)
├── ServiceError (500)
│   ├── VectorStoreError (500)
│   ├── EmbeddingError (500)
│   └── LLMError (500)
├── MCPConnectionError (503)
└── AgentExecutionError (500)
```

#### 3.5.5 中间件

`app/api/middleware.py`：

- **CORS**：`allow_origins=["*"]`, `allow_methods=["*"]`, `expose_headers=["X-Request-ID"]`
- **RequestIDMiddleware**：为每个请求注入 `X-Request-ID` UUID，设置到 `request.state` 和 Loguru 上下文
- **LoggingMiddleware**：记录 `{method} {path} -> {status_code} ({elapsed_ms}ms)`（跳过 `/static` 和 `/health`）

#### 3.5.6 SSE 事件体系

**RAG Chat** (`POST /api/v1/chat/stream`)：

| 事件类型 | 说明 |
|----------|------|
| progress | 阶段提示 (rewrite / retrieve / web / llm_start / tool_call / stats) |
| thinking | 推理链 token (DeepSeek/Qwen3 思考模式) |
| token | LLM 输出流式 token |
| error | 异常 |

**AIOps 诊断** (`POST /api/v1/aiops/diagnose`)：

| 事件类型 | 说明 |
|----------|------|
| start | 流程启动 |
| skill_selected | Router 选定 Skill |
| plan | Planner 输出初始步骤 |
| step_start | Executor 开始执行某步 |
| step_complete | Executor 完成某步 |
| replan | Replanner 调整计划 |
| report | 最终诊断报告 (Markdown) |
| complete | 流程完成 |
| error | 异常 |

#### 3.5.7 并发控制

- AIOps 诊断：`asyncio.Semaphore(settings.agent_max_concurrency)` (默认 2)，防止多任务并发把 LLM API 额度打满
- RAG Chat：`settings.rag_max_concurrency=5`

### 3.6 权限与安全模型

#### 3.6.1 三层防御（cc-haha §1 借鉴）

`app/runtime/permissions.py` — `evaluate_permission()` 函数，短路返回策略：

```
Layer 0: Skill allowed_tools 白名单 (硬墙)
  → 只读查询工具豁免 (ToolMeta.read_only=True), 可跨 Skill 使用
  → 写/通知/高危工具严格限制

Layer 1: PermissionMode 限制
  → READ_ONLY   → 拒绝写工具
  → NORMAL      → 继续 Layer 2
  → ASK_DESTRUCTIVE → 写工具走审批 (MVP 转 deny)
  → BYPASS      → 跳过 (仅 dev)

Layer 2: 静态 Guardrails
  → 高危黑名单 (HIGH_RISK_TOOLS) 默认拦截
  → 通知黑名单 (NOTIFICATION_TOOLS) 默认拦截

Layer 3: (占位) 参数级规则
```

#### 3.6.2 输入感知权限 (effective_read_only)

部分工具（如 `Bash`）的只读性取决于入参：`Bash(ls)` 只读，`Bash(rm -rf /)` 不只读。`ToolMeta.effective_read_only(tool_input)` 方法基于 `read_only_for_input` 字段做判断。

#### 3.6.3 API 层鉴权

知识库写操作（upload / delete）要求 `X-KB-Admin-Token` Header 匹配 `settings.kb_admin_token`。

### 3.7 流式响应与可观测性

#### 3.7.1 双队列流式架构

AIOps 诊断的流式输出采用双队列模式：

```
LangGraph astream  ──▶ token_queue (asyncio.Queue)  ◀── Executor 的 emit()
         │                                                   │
         ▼                                                   ▼
  __node__ 事件 (graph 层面)               step_start / tool_call / token (Agent 层面)
         │                                                   │
         └──────────────────▶ 合并 ←─────────────────────────┘
                                     │
                                     ▼
                              SSE event_generator
```

核心机制：
- `set_sink(token_queue)` 设置当前 asyncio task 的 ContextVar
- Executor 内部的 `emit()` 把工具调用/LLM token 推入队列
- 主循环同时消费 graph `astream` 的节点事件和队列内的事件
- `create_task` 自动继承 ContextVar，无需全局变量

#### 3.7.2 Transition History（cc-haha §6 借鉴）

每个节点出口记录一条 `StateTransition`：

```python
make_transition("planner", PLANNER_OK, "skill=host_resource_diagnosis steps=3")
```

所有 transition 通过 `operator.add` 累加到 `state.transition_history`，前端收到 `transition` 类型 SSE 事件，渲染为结构化时间线。

Transition reason 枚举覆盖所有节点所有路（安全兜底 13 种）：

| 节点 | 可能 Transition |
|------|----------------|
| skill_router | OK / FALLBACK_GENERIC / OUT_OF_SCOPE / LLM_FAILED |
| planner | OK / LLM_FAILED / EMPTY_STEPS |
| executor | OK / TOOL_ERROR / MAX_STEPS |
| replanner | CONTINUE / FINISHED_OK / FINISHED_EMPTY / NOT_FINISHED_EMPTY / MAX_STEPS_FORCE / LLM_FAILED / REROUTE / REROUTE_BLOCKED |

#### 3.7.3 日志系统

- **框架**：Loguru（结构化控制台输出 + 文件轮转）
- **上下文注入**：通过 RequestIDMiddleware 把 `request_id` 注入 Loguru context
- **日志目录**：`LOG_DIR=logs`，`LOG_RETENTION_DAYS=14`
- **安全**：`app/logging_config.py` 通过 `patch_std_loggers()` + `sink` 避免 stdout/stderr 污染容器化日志（替代 `logging.basicConfig`）

#### 3.7.4 Alert History 持久化

Webhook 触发的后台诊断写入 `data/alert_history.jsonl`（JSON Lines 格式），每条记录包含 `session_id`, `ts`, `alertname`, `fingerprint`, `report`。前端通过 `/api/v1/webhook/history` 拉取并按时间倒序展示。

---

## 4. 测试方案

### 4.1 测试策略

当前阶段以**集成测试**和**端到端验证**为主，确保各子系统连通性正确。

### 4.2 集成测试

`scripts/integration_test.py` — 端到端验证脚本：

- 验证知识库检索连通性（Milvus Collection 存在 + 搜索返回结果）
- 验证 LLM 连通性（API Key 有效 + 可完成一次 chat completion）
- 验证 SSE 流式响应（HTTP 200 + event 类型正确）
- 验证 AIOps 诊断端到端（提交 query → 收到 complete 事件）
- 验证 Webhook 接收（POST Alertmanager payload → 返回 accepted）
- 验证负载测试（并发请求不发生 500/503）

### 4.3 迁移验证

`scripts/verify_migration.py` — 验证 Milvus Collection 字段迁移后数据完整性（pk/content/source/chapter 字段存在、向量维度匹配等）。

### 4.4 测试分层

```
        /\
       /E2E\         ← 集成测试脚本 (integration_test.py)
      /------\
     /Component\     ← pending: 各模块独立可测性提升
    /------------\
   /  Unit Tests  \  ← pending: 单元测试覆盖核心函数
  /________________\
```

> **当前状态**：集成测试覆盖关键路径。单元测试和组件测试待补充——这是面试中可讨论的"如果再做一轮迭代会怎么做"话题。

---

## 5. 系统架构与模块设计

### 5.1 整体架构

```
┌─────────────────────────────────────────────────────────────┐
│                         Frontend                             │
│                  Vite + 原生 JS + SSE                        │
│           http://localhost:9900  (StaticFiles)               │
└──────────────────────────┬──────────────────────────────────┘
                           │ HTTP / SSE
┌──────────────────────────▼──────────────────────────────────┐
│                     FastAPI (app/main.py)                     │
│  ┌──────────────┬──────────────┬──────────────┬────────────┐ │
│  │  Middleware  │  Exception   │   Routers    │   Static   │ │
│  │  CORS/ReqID  │   Handlers   │   6 routers  │   Files    │ │
│  └──────────────┴──────────────┴──────────────┴────────────┘ │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│                    Services Layer                             │
│  ┌─────────────────────┐  ┌───────────────────────────────┐ │
│  │   aiops_service.py  │  │      rag_service.py           │ │
│  │ (LangGraph SSE wrap)│  │  (RAG chat SSE orchestration) │ │
│  └─────────┬───────────┘  └──────────────┬────────────────┘ │
└────────────┼──────────────────────────────┼──────────────────┘
             │                              │
┌────────────▼──────────────────────────────▼──────────────────┐
│                    Agents Layer                               │
│  ┌────────────┬──────────┬──────────┬──────────┬──────────┐ │
│  │SkillRouter │ Planner  │ Executor │Replanner │ForkRunner│ │
│  └────────────┴──────────┴──────────┴──────────┴──────────┘ │
│              LangGraph StateGraph (graph.py)                  │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│                   Core Infrastructure                         │
│  ┌──────────┬───────────┬───────────┬──────────┬──────────┐ │
│  │   LLM    │ Embedding │  Milvus   │MCP Client│ Reranker │ │
│  │ Factory  │   (BGE)   │ VectorStore│         │  (BGE)   │ │
│  └──────────┴───────────┴───────────┴──────────┴──────────┘ │
│  ┌──────────────┬──────────────┬──────────────────────────┐ │
│  │HybridRetrieve│  Skill Reg.  │   Runtime (Permissions)  │ │
│  │(BM25+RRF)    │  (SKILL.md)  │   ToolFilter / Guardrails│ │
│  └──────────────┴──────────────┴──────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

### 5.2 模块分层

| 层 | 目录 | 职责 | 关键文件 |
|----|------|------|----------|
| 接口层 | `app/api/` | HTTP 路由 + 中间件 + 全局异常 | `v1/chat.py`, `v1/aiops.py`, `middleware.py` |
| 数据模型层 | `app/schemas/` | Pydantic Request/Response 定义 | `common.py`, `aiops.py`, `chat.py` |
| 业务服务层 | `app/services/` | SSE 流编排，子模块拼接 | `aiops_service.py`, `rag_service.py`, `chat_memory.py` |
| 智能体层 | `app/agents/` | LangGraph 图 + 4 节点 + State | `graph.py`, `state.py`, `prompts.py` |
| Skill 系统层 | `app/skills/` | 技能注册/路由/加载/Prompt | `registry.py`, `router.py`, `models.py`, `loader.py` |
| 工具层 | `app/tools/` | MCP 工具加载 + 元数据注册 | `mcp_loader.py`, `meta.py`, `lazy_mcp_tools.py` |
| 运行时层 | `app/runtime/` | 权限决策 + 工具过滤 + Transition | `permissions.py`, `tool_filter.py`, `tool_runner.py` |
| 基础设施层 | `app/core/` | LLM/Embedding/Milvus/MCP/Reranker | `llm.py`, `embedding.py`, `vector_store.py`, `mcp_client.py`, `reranker.py` |
| RAG 子模块 | `app/services/rag/` | 检索/记忆/联网/Prompt | `retrieval.py`, `memory.py`, `web_context.py` |
| 配置 | `app/config.py` | Pydantic Settings (所有可变配置) | 90+ 字段，40+ 环境变量映射 |

### 5.3 数据流

**AIOps 诊断流**：

```
用户 query
  → API (aiops.py POST /diagnose)
  → aiops_service.stream_diagnose()
  → graph.astream({"input": query})
  → SkillRouter → Planner → Executor (MCP tools) → Replanner
  → SSE events → Frontend
  → Redis (诊断报告缓存)
```

**RAG Chat 流**：

```
用户 question
  → API (chat.py POST /stream)
  → rag_service.stream_chat()
  → Query Rewrite (多轮) → KB Retrieve + Web Search (并行)
  → LLM (with MCP tools) → SSE tokens → Frontend
  → Redis (会话写入 + compact)
```

**Alertmanager Webhook 流**：

```
Alertmanager POST → API (webhook.py)
  → 200 ACK (立即)
  → BackgroundTasks: stream_diagnose()
  → 收集所有 SSE → 写入 data/alert_history.jsonl
```

---

## 6. 项目排期

> 以下为逆向推断的实际开发阶段，基于代码结构和 git 历史还原。

### Phase 1: 基础设施搭建 (Week 1-2)
- FastAPI 项目骨架 (`main.py`, config, 异常处理, 中间件)
- Milvus 向量数据库连接 (`core/milvus.py`)
- BGE Embedding 本地加载 (`core/embedding.py`)
- LLM 工厂 (DeepSeek + DashScope + Ollama) (`core/llm.py`)
- 统一响应格式 `ApiResponse[T]` + 全局异常处理器

### Phase 2: RAG 检索链路 (Week 2-3)
- 文档分块 + Embedding + Milvus upsert (`utils/splitter.py`, 摄取脚本)
- Vector 检索 (`core/vector_store.py` - `safe_similarity_search`)
- Hybrid Search (BM25 + RRF) (`core/hybrid_retriever.py`)
- Reranker 集成 (BGE CrossEncoder) (`core/reranker.py`)
- 高级检索流水线 (`advanced_search`)
- 知识库文档管理 API (`/documents`)

### Phase 3: RAG Chat (Week 3-4)
- RAG Chat SSE 流式服务 (`services/rag_service.py`)
- 多轮对话记忆 (Redis + query rewrite + compact)
- 联网搜索补充 (`services/rag/web_context.py`)
- 工具增强路径 (MCP tools 注入 RAG Chat)

### Phase 4: Agent 多智能体 (Week 4-5)
- LangGraph StateGraph 编排 (`agents/graph.py`)
- Planner / Executor / Replanner 三节点
- 结构化输出 (Plan / Act)
- 防死循环机制 + 快路径优化
- Fork 子图模式

### Phase 5: Skill 系统 (Week 5-6)
- Skill 数据模型 + Loader (`skills/models.py`, `loader.py`)
- SkillRegistry 单例 (`skills/registry.py`)
- Skill Router (LLM + 关键词兜底) (`skills/router.py`)
- 4 个内置 Skill 定义 (container / host / network / generic)
- Skill reroute (Supervisor + Handoff)

### Phase 6: 权限与运行时 (Week 6)
- PermissionMode 四模式 (`runtime/permissions.py`)
- ToolMeta + ToolRegistry (`tools/meta.py`)
- Tool filter (Skill 白名单 + Guardrails)
- run_parallel_agent (read-only 并行编排) (`runtime/tool_runner.py`)
- Transition history 结构化时间线 (`runtime/transitions.py`)

### Phase 7: MCP 集成 (Week 6-7)
- MCPClientManager 单例 (`core/mcp_client.py`)
- 5 个 MCP Server 配置 + 逐 server 加载
- ExceptionGroup 展开 + 单次重试
- Lazy tools 两阶段模式（可选）
- 工具排除集 (RAG Chat 不暴露诊断专用工具)

### Phase 8: Webhook + 前端 (Week 7-8)
- Alertmanager Webhook 接收 + 后台诊断 (`api/v1/webhook.py`)
- Alert history JSONL 持久化 + API
- Vite 前端：聊天气泡式 SSE 消费 + Markdown 渲染
- AIOps 诊断页面：步骤卡片 + 工具调用进度 + 报告展示

---

## 7. 可扩展性

### 7.1 可插拔架构

系统在设计上已预留了以下可插拔替换点：

| 组件 | 当前实现 | 替换方式 | 配置项 |
|------|---------|---------|--------|
| LLM | DeepSeek V4 | DashScope / Ollama / 任意 OpenAI 兼容 API | `deepseek_*` / `dashscope_*` / `local_llm_*` |
| Embedding | BGE-small-zh (512d) | BGE-large (1024d) / OpenAI text-embedding-3 | `local_embedding_model` |
| VectorStore | Milvus | Qdrant / Elasticsearch | `app/core/vector_store.py` |
| Reranker | BGE-reranker-base | DashScope gte-rerank / Cohere Rerank | `rag_rerank_model` |
| 会话记忆 | Redis | PostgreSQL / 纯内存 | `redis_url` |
| Web Search | mock / tavily / ddgs | 任意搜索 API | `web_search_provider` |
| MCP Tools | 5 个 streamable-http Server | 任意 MCP Server (stdio/sse/http) | `mcp_*_url` |

### 7.2 Skill 生态扩展

Skill 系统采用文件驱动设计，新增 Skill 无需修改代码：在 `app/skills/definitions/<new_skill>/SKILL.md` 创建文件，重启后自动加载。可扩展方向：

- **业务 Skill**：MySQL 慢查询诊断、Redis 内存分析、K8s Pod 异常排查
- **工具链 Skill**：集成 Prometheus/Grafana/ELK/Jaeger 等常见运维工具
- **团队 Skill**：团队 SOP / Runbook / 内部知识沉淀

### 7.3 多模态支持

当前 RAG 链路仅处理文本。未来可通过以下路径增加多模态：

1. **Image Caption** → 摄取阶段用 Vision LLM 描述图表/截图 → 注入 Markdown 正文 → 复用纯文本检索
2. **图搜图** → 叠加 CLIP Embedding 实现跨模态向量检索


### 7.5 评估体系

当前缺少系统化的检索与生成质量评估。可集成：

- **Ragas**：RAG 专用评估（Faithfulness, Answer Relevancy, Context Precision）
- **自定义指标**：Hit Rate, MRR, Latency P99 等工程指标
- **A/B 对比**：同一 query 走不同策略（Vector-Only vs Hybrid vs Hybrid+Rerank），对比 recall/precision

