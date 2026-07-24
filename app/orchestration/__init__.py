"""诊断编排层: fast/deep 双模式的派发与生效解析入口."""

from app.orchestration.diagnosis_mode import (
    normalize_diagnosis_mode,
    resolve_effective_mode,
)

__all__ = ["normalize_diagnosis_mode", "resolve_effective_mode"]
