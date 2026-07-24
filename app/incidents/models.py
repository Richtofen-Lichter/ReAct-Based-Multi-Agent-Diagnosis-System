"""Fast / Deep 诊断模式契约.

本模块只放与 fast/deep 双模式直接相关的轻量类型, 不引入 fork 的 incidents 持久化层
(NormalizedAlert / DiagnosisTaskRecord / Postgres 等). 阶段 0 只需要 DiagnosisMode
枚举和它的别名归一函数 —— 这是请求 schema、state、runner 派发三处共用的单一事实源.

未来若要接入 fork 的 incidents 持久化 (阶段 3), 再把 NormalizedAlert / EvidenceSource /
DiagnosisTaskRecord 等迁到本文件, 保持路径与 fork 一致方便同步.
"""

from __future__ import annotations

from enum import StrEnum


class DiagnosisMode(StrEnum):
    """诊断模式.

    - FAST: 单图 Plan-Execute-Replan (SkillRouter→Planner→Executor⇄Replanner→Report),
            延迟低, 适合日常告警.
    - DEEP: 独立的多 Agent 取证图 (IncidentManager→CorrelationContext→EvidencePlan
            →4 专家 fan-out→EvidenceReducer→RCAJudge→RemediationPlanner→Report),
            延迟高但证据更全, 适合 critical / 影响面大的故障.
    """

    FAST = "fast"
    DEEP = "deep"


class EvidenceSource(StrEnum):
    """Deep 图专业 subagent 产出的 Evidence 来源类型.

    与 fork 的 app/incidents/models.py 对齐. evidences 列表里的每条 dict 用
    `source` 字段取这里的值, RCAJudge / EvidenceReducer 按来源归类.
    """

    ALERT = "alert"
    LOG = "log"
    METRIC = "metric"
    TRACE = "trace"
    RUNBOOK = "runbook"
    INCIDENT_HISTORY = "incident_history"
    RCA = "rca"
    MCP_TOOL_RESULT = "mcp_tool_result"
    HUMAN_FEEDBACK = "human_feedback"


# 外部输入 (HTTP body / Celery / 前端 toggle) 常见的中文/英文别名 → 内部枚举.
# schema 的 field_validator 和 runner 的 normalize_diagnosis_mode 共用这张表,
# 保证两端归一逻辑不会漂移.
_MODE_ALIASES: dict[str, DiagnosisMode] = {
    "daily": DiagnosisMode.FAST,
    "normal": DiagnosisMode.FAST,
    "routine": DiagnosisMode.FAST,
    "fast": DiagnosisMode.FAST,
    "日常": DiagnosisMode.FAST,
    "常规": DiagnosisMode.FAST,
    "deep": DiagnosisMode.DEEP,
    "depth": DiagnosisMode.DEEP,
    "group": DiagnosisMode.DEEP,
    "深度": DiagnosisMode.DEEP,
}


def normalize_diagnosis_mode(value: str | DiagnosisMode | None) -> DiagnosisMode:
    """把外部传入的模式字符串归一化成 DiagnosisMode.

    未知值 / None / 空串 一律回落到 FAST (保守: 不知意图就跑快的)。
    """
    if isinstance(value, DiagnosisMode):
        return value
    raw = str(value or DiagnosisMode.FAST.value).strip().lower()
    return _MODE_ALIASES.get(raw, DiagnosisMode.FAST)
