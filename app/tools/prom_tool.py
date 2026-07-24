"""Prometheus 指标工具 (stub).

fork 的 metric_agent 调 get_prom_tools() 拿 Prometheus 只读查询工具。ReAct-Based
尚未接入 Prometheus, 这里给一个返回空列表的占位实现 —— metric_agent 会自动退化为
只用本机 system 工具 (get_local_* / list_top_processes), 不影响 deep 图跑通。

接入真 Prometheus / VictoriaMetrics 时, 在此实现 promql 查询 @tool 并登记 ToolMeta
(参考 app/tools/system_tool.py 的登记方式), 让 metric_agent 优先查真指标。
"""

from __future__ import annotations

from typing import Any


def get_prom_tools() -> list[Any]:
    """返回 Prometheus 工具列表。未接入时返回空, metric_agent 退化为纯本机指标。"""
    return []
