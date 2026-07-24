"""Slim AgentHarness: 模型-角色注册表 (deep 图复用).

ReAct-Based 原本没有 harness —— per-node 模型选择内联在各节点读
`settings.agent_*_model or <fallback>`. 但 fork 的 deep 图 (4 个专家 + RCAJudge)
调 `harness.executor_model()` / `harness.report_model()`, 故这里提供最小实现:
只做模型名解析, 指向 ReAct-Based 已有的 settings 字段, 不引入 fork harness 的
预算 / token 跟踪 / wiki 写钩子 (那些依赖 HarnessUsageStats + 预算配置 + wiki,
属 fork 的 orchestration 层, 阶段 3 再视需要移植).

路径与接口与 fork 的 app/runtime/agent_harness.py 对齐 (get_agent_harness + 模型方法),
方便以后扩或同步 —— 缺的方法 (build_*_messages / evaluate_budget 等) 真用到再补.
"""

from __future__ import annotations

from functools import lru_cache

from app.config import settings


class AgentHarness:
    """模型-角色注册表 (slim 版, 仅模型名解析).

    档位约定与 ReAct-Based 既有 per-node 选择一致:
      - flash 档: deepseek_router_model (Router / Planner / Replanner / RAG rewrite)
      - pro   档: deepseek_chat_model (Executor fallback / Report / RAG chat)
      - per-node 覆盖: agent_executor_model / agent_report_model / agent_planner_model
    """

    # —— flash 档 ——
    def router_model(self) -> str:
        return settings.deepseek_router_model

    def planner_model(self) -> str:
        return settings.agent_planner_model or settings.deepseek_router_model

    def replanner_model(self) -> str:
        return settings.agent_planner_model or settings.deepseek_router_model

    def report_decision_model(self) -> str:
        # Replanner 决策步 (与 fork 一致, 走 planner/flash 档)
        return settings.agent_planner_model or settings.deepseek_router_model

    # —— pro 档 ——
    def executor_model(self) -> str:
        return settings.agent_executor_model or settings.deepseek_chat_model

    def report_model(self) -> str:
        return settings.agent_report_model or settings.deepseek_chat_model

    def rag_chat_model(self) -> str:
        return settings.deepseek_chat_model

    def rag_rewrite_model(self) -> str:
        return settings.deepseek_router_model

    def rag_compact_model(self) -> str:
        return settings.deepseek_chat_model

    # —— 图运行参数 ——
    def graph_recursion_limit(self) -> int:
        # 与 aiops_service 的 fast 图一致; deep 图也复用同一上限.
        return settings.agent_max_steps * 3 + 5


@lru_cache(maxsize=1)
def get_agent_harness() -> AgentHarness:
    """进程级单例 harness."""
    return AgentHarness()
