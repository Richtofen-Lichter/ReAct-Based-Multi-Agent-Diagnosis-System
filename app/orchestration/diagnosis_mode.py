"""fast/deep 诊断模式的生效解析 (纯函数, 无重依赖).

被 schemas/aiops.py 的请求字段校验和 services/aiops_service.py 的图派发共用,
因此独立成模块 —— 避免 schema → service 的循环 import, 也让 webhook / Celery
(阶段 2) 能直接 import resolve_effective_mode 而不拖进整个 service.
"""

from __future__ import annotations

from app.incidents.models import DiagnosisMode, normalize_diagnosis_mode


def resolve_effective_mode(
    requested_mode: str | DiagnosisMode | None,
) -> tuple[DiagnosisMode, DiagnosisMode, bool]:
    """把"用户请求的模式"解析成"现在真能跑的模式"。

    受 settings.deep_diagnosis_enabled 开关控制:
      - fast 永远走 Plan-Execute-Replan 图.
      - deep 在开关开启时走独立 Deep Diagnosis 图; 开关关闭时回落到 fast,
        并通过 group_agent_reserved=True 标记本次回落 —— 前端据此提示"已降级"。

    Returns:
        (requested_mode, effective_mode, group_agent_reserved)
        - requested_mode:        归一化后的原始请求 (deep 被关闭时仍记 deep)
        - effective_mode:         实际将执行的图模式
        - group_agent_reserved:   True 表示 deep 被请求但降级到了 fast
    """
    from app.config import settings  # lazy import: 避免 config <-> 本模块加载顺序耦合

    requested = normalize_diagnosis_mode(requested_mode)
    if requested == DiagnosisMode.DEEP and settings.deep_diagnosis_enabled:
        return requested, DiagnosisMode.DEEP, False
    return requested, DiagnosisMode.FAST, requested == DiagnosisMode.DEEP
