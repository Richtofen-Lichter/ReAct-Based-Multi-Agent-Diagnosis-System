"""AIOps 多智能体诊断服务.

把 LangGraph 图的 astream 输出包装成统一格式的 SSE 事件流, 供前端消费.

按 diagnosis_mode 派发到两张图之一 (effective_mode 由 resolve_effective_mode +
settings.deep_diagnosis_enabled 决定):
  - fast (默认): build_aiops_graph() —— SkillRouter→Planner→Executor⇄Replanner→Report
  - deep:        build_deep_graph()   —— IncidentManager→CorrelationContext→EvidencePlan
                →[4 专家并行]→EvidenceReducer→RCAJudge→RemediationPlanner→Report
                (deep 图懒构建, 仅 deep 模式真跑时才 import + 编译, 不影响 fast / 启动)

事件类型 (fast 与 deep 共用同一词表, 见 schemas/aiops.py EventType):
  fast:  start / mode_selected / skill_selected / plan / step_*/replan / report / complete / error
  deep:  额外 evidence_plan / evidence / candidates / rca / remediation (按 node_name 分发)

设计要点:
  - 全程结构化事件 (字典), 由 API 层统一 JSON 编码
  - 异常被 try/except 捕获后转为 error 事件, 不让流中断
  - 单实例 graph: 模块级缓存, 避免每次请求重新编译 (fast/deep 各一份)
"""

import asyncio
from typing import Any, AsyncIterator, Dict

from loguru import logger

from app.agents import build_aiops_graph
from app.agents.stream_sink import set_sink
from app.config import settings
from app.incidents.models import DiagnosisMode
from app.orchestration.diagnosis_mode import resolve_effective_mode
import app.services.chat_memory as chat_memory

# 模块级单例 (图编译有开销, 不要每次请求都建)
_graph = None
_deep_graph = None
_agent_semaphore = asyncio.Semaphore(settings.agent_max_concurrency)


def _get_graph():
    global _graph
    if _graph is None:
        _graph = build_aiops_graph()
    return _graph


def _get_deep_graph():
    """懒构建 deep 诊断图 (独立于 fast)。仅在 deep 模式真要跑时才 import + 编译,
    故 deep 图的任何依赖/错误都不会拖垮 fast 路径或应用启动。"""
    global _deep_graph
    if _deep_graph is None:
        from app.diagnosis_graphs import build_deep_graph

        _deep_graph = build_deep_graph()
    return _deep_graph


def _make_event(
    event_type: str, stage: str, message: str = "", **data: Any
) -> Dict[str, Any]:
    """构造统一格式的 SSE 事件."""
    return {"type": event_type, "stage": stage, "message": message, "data": data}


async def stream_diagnose(
    query: str,
    *,
    session_id: str = "default",
    diagnosis_mode: str | DiagnosisMode = DiagnosisMode.FAST,
) -> AsyncIterator[Dict[str, Any]]:
    """流式诊断, yield 一系列结构化事件.

    Args:
        query:          用户输入 (告警描述 / 故障现象)
        session_id:     会话 ID, 用于日志关联
        diagnosis_mode:  诊断模式 (fast / deep). deep 在 settings.deep_diagnosis_enabled
                        开启时走独立 Deep Diagnosis 图 (阶段 1 接入), 否则回落 fast.

    Yields:
        Dict[str, Any]: SSE 事件字典
    """
    requested_mode, effective_mode, group_agent_reserved = resolve_effective_mode(
        diagnosis_mode
    )
    # deep 图已接入 (build_deep_graph). 不再做 phase 0 的强制降级 ——
    # effective_mode 由 settings.deep_diagnosis_enabled 决定, 关闭时 resolve 已回落 fast.
    async with _agent_semaphore:
        logger.info(
            f"[aiops] session={session_id} | requested={requested_mode.value} | "
            f"effective={effective_mode.value} | query={query[:100]}..."
        )

        yield _make_event(
            "start",
            "diagnosis_init",
            message="开始故障诊断",
            query=query,
            session_id=session_id,
            requested_mode=requested_mode.value,
            effective_mode=effective_mode.value,
        )

        # mode_selected: 告诉前端"最终跑哪个图"以及"deep 是否被降级".
        if effective_mode == DiagnosisMode.DEEP:
            mode_message = "深度诊断图: 多 Agent 取证与 RCA"
        elif group_agent_reserved:
            mode_message = "deep 模式未启用, 本次回落到 fast Plan-Execute-Replan"
        else:
            mode_message = "fast 模式: Plan-Execute-Replan 诊断"
        yield _make_event(
            "mode_selected",
            "diagnosis_mode",
            message=mode_message,
            requested_mode=requested_mode.value,
            effective_mode=effective_mode.value,
            group_agent_reserved=group_agent_reserved,
        )

        # 按 effective_mode 选图: deep 启用且请求 deep -> 独立深度图; 否则 fast.
        # 两图 graph_input 共用 input/diagnosis_mode/requested_diagnosis_mode 这几个字段.
        graph = _get_deep_graph() if effective_mode == DiagnosisMode.DEEP else _get_graph()

        # Executor 里 tool_runner 走 astream 的 token 会被 emit_stream 推到这个队列,
        # 主循环和 graph.astream 节点事件合并 yield, 让前端边跑边看.
        token_queue: asyncio.Queue[Dict[str, Any]] = asyncio.Queue(maxsize=2048)
        set_sink(token_queue)  # 当前 context 设置, create_task 会复制这份 context
        done_sentinel: Dict[str, Any] = {"__done__": True}

        async def _graph_runner() -> None:
            try:
                async for event in graph.astream(
                    {
                        "input": query,
                        "diagnosis_mode": effective_mode.value,
                        "requested_diagnosis_mode": requested_mode.value,
                    },
                    config={"recursion_limit": settings.agent_max_steps * 3 + 5},
                ):
                    await token_queue.put({"__node__": event})
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                await token_queue.put({"__error__": exc})
            finally:
                await token_queue.put(done_sentinel)

        runner_task = asyncio.create_task(_graph_runner())

        try:
            while True:
                item = await token_queue.get()
                if item is done_sentinel:
                    break
                if "__error__" in item:
                    exc = item["__error__"]
                    logger.exception(f"[aiops] session={session_id} | 诊断异常: {exc}")
                    yield _make_event(
                        "error", "diagnosis_failed",
                        message=f"诊断失败: {type(exc).__name__}: {exc}",
                        error_type=type(exc).__name__,
                    )
                    continue
                if "__node__" in item:
                    event = item["__node__"]
                    for node_name, node_output in event.items():
                        # §6 先发 transition_history, 再发常规节点事件
                        for tr in (node_output or {}).get("transition_history") or []:
                            yield _make_event(
                                "transition",
                                tr.get("reason", "unknown"),
                                message=tr.get("detail", ""),
                                node=tr.get("node", node_name),
                                ts=tr.get("ts", ""),
                                reason=tr.get("reason", ""),
                            )
                        async for sse_event in _convert_node_event(node_name, node_output):
                            if sse_event.get("type") == "report":
                                report_text = (sse_event.get("data") or {}).get("report") or ""
                                if report_text:
                                    try:
                                        await chat_memory.append_diagnosis_report(
                                            report_text, session_id=session_id
                                        )
                                    except Exception as exc:
                                        logger.warning(
                                            f"[aiops] 诊断报告缓存失败 session={session_id}: "
                                            f"{type(exc).__name__}: {exc}"
                                        )
                            yield sse_event
                    continue
                # 其他都是 Executor 推出来的 token/step_start/tool_call 事件, 直接转 SSE.
                etype = item.get("type", "token")
                payload = {k: v for k, v in item.items() if k != "type"}
                yield _make_event(etype, etype, message="", **payload)

            yield _make_event(
                "complete", "diagnosis_complete", message="诊断流程完成"
            )

        except asyncio.CancelledError:
            # 客户端断开连接, 不算错误, 静默处理
            logger.info(f"[aiops] session={session_id} | 客户端断开")
            runner_task.cancel()
            raise
        except Exception as e:
            logger.exception(f"[aiops] session={session_id} | 诊断异常: {e}")
            yield _make_event(
                "error",
                "diagnosis_failed",
                message=f"诊断失败: {type(e).__name__}: {e}",
                error_type=type(e).__name__,
            )
        finally:
            if not runner_task.done():
                runner_task.cancel()
                try:
                    await runner_task
                except (asyncio.CancelledError, Exception):
                    pass


async def _convert_node_event(
    node_name: str, node_output: Dict[str, Any]
) -> AsyncIterator[Dict[str, Any]]:
    """把 LangGraph 节点输出转成 SSE 事件."""
    if node_name == "skill_router":
        skill_name = node_output.get("selected_skill", "")
        reason = node_output.get("skill_reason", "")
        response = node_output.get("response", "")
        yield _make_event(
            "skill_selected",
            "skill_selected",
            message=f"已选定 Skill: {skill_name}",
            skill=skill_name,
            reason=reason,
        )
        if response:
            yield _make_event(
                "report",
                "report_generated",
                message="Router 已终止诊断",
                report=response,
            )

    elif node_name == "planner":
        plan = node_output.get("plan", [])
        yield _make_event(
            "plan",
            "plan_created",
            message=f"诊断计划已生成, 共 {len(plan)} 步",
            plan=plan,
        )

    elif node_name == "executor":
        past = node_output.get("past_steps", [])
        iteration = node_output.get("iteration", 0)
        if past:
            step, result = past[-1]
            preview = result[:200] + ("..." if len(result) > 200 else "")
            yield _make_event(
                "step_complete",
                "step_executed",
                message=f"完成第 {iteration} 步",
                iteration=iteration,
                step=step,
                result_preview=preview,
            )

    elif node_name == "replanner":
        response = node_output.get("response", "")
        new_plan = node_output.get("plan", [])
        if response:
            # Replanner 决定终止 + 给报告
            yield _make_event(
                "report",
                "report_generated",
                message="最终诊断报告已生成",
                report=response,
            )
        elif new_plan:
            # 还要继续
            yield _make_event(
                "replan",
                "plan_updated",
                message=f"调整计划, 剩余 {len(new_plan)} 步",
                plan=new_plan,
            )

    elif node_name == "fork_skill":
        # §4 cc-haha: fork 子图直接产出最终报告, 一步到位
        response = node_output.get("response", "")
        if response:
            yield _make_event(
                "report",
                "report_generated",
                message="Fork Skill 子图已产出最终报告",
                report=response,
                fork=True,
            )

    # ===== Deep Diagnosis 节点 =====
    # 节点名与 fast 互不重叠, 同一函数分发不影响 fast 行为.
    # 大量事件已由 transition_history -> "transition" SSE 自动产生; 这里只补
    # "前端要拿到结构化 payload" 的关键事件.
    elif node_name == "evidence_plan":
        plan = node_output.get("evidence_plan", {}) or {}
        agents = plan.get("agents", []) or []
        yield _make_event(
            "evidence_plan",
            "evidence_planned",
            message=f"取证计划: 派出 {len(agents)} 个专业 Agent",
            agents=agents,
            strategy=plan.get("strategy", ""),
        )

    elif node_name in {"log_agent", "metric_agent", "infra_agent", "runbook_agent"}:
        # 各专业 subagent 只回 Evidence; evidences 是 add 累加,
        # node_output 里只含本节点新增的那 (一或多) 条.
        new_evs = node_output.get("evidences", []) or []
        for ev in new_evs:
            yield _make_event(
                "evidence",
                f"{node_name}_evidence",
                message=str(ev.get("summary") or "")[:200],
                agent=node_name,
                source=str(ev.get("source", "")),
                evidence_type=str(ev.get("type", "")),
            )

    elif node_name == "evidence_reducer":
        cands = node_output.get("candidates", []) or []
        yield _make_event(
            "candidates",
            "candidates_reduced",
            message=f"归并得到 {len(cands)} 个候选根因",
            candidates=cands,
        )

    elif node_name == "rca_judge":
        rca = node_output.get("rca", {}) or {}
        if rca:
            yield _make_event(
                "rca",
                "rca_judged",
                message=str(rca.get("root_cause") or "")[:200],
                rca=rca,
            )

    elif node_name == "remediation_planner":
        rem = node_output.get("remediation", {}) or {}
        if rem:
            yield _make_event(
                "remediation",
                "remediation_planned",
                message=("处置建议待人工确认" if rem.get("requires_human_confirm") else "处置建议已生成"),
                remediation=rem,
            )

    elif node_name == "report":
        # deep graph 的最终 Report 节点; 复用 fast 的 type="report"
        # 让前端 SSE 同一套渲染逻辑能直接对接, 不必区分模式.
        response = node_output.get("response", "")
        if response:
            yield _make_event(
                "report",
                "report_generated",
                message="深度诊断报告已生成",
                report=response,
                deep=True,
            )

    # 其他未识别节点忽略 (例如内部节点)
