"""告警 Webhook 接收接口 — 对接 Prometheus Alertmanager 标准协议.

这是 AIOps Agent 从 "演示模式" 升级为 "生产模式" 的关键接口:
  - 手动模式: 人在前端输入告警文本 → SSE 流出诊断报告
  - 自动模式 (本文档): Alertmanager POST 标准 JSON → Celery 入队 → Worker 异步诊断 → 写入 history

为什么不走 SSE?
  Alertmanager webhook 要求 5s 内返回 200, 然后调用方不再关心。
  AIOps 诊断一跑 30-90s, 必须后台异步跑, 结果落盘供后续查询。

Celery vs BackgroundTasks:
  当前使用 Celery (Redis broker), 支持:
  - 任务排队 (不丢告警)
  - Worker 独立进程 (重启不丢任务)
  - 失败自动重试 (3 次, 指数退避)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter
from loguru import logger
from pydantic import BaseModel, Field

from app.celery_tasks.diagnosis import run_webhook_diagnosis

router = APIRouter(prefix="/webhook", tags=["webhook"])


# ============================================================
# Alertmanager v4 webhook payload
#   规范: https://prometheus.io/docs/alerting/latest/configuration/#webhook_config
# ============================================================
class AlertmanagerAlert(BaseModel):
    """单条 firing/resolved 告警."""

    status: str = Field(default="firing", description="firing | resolved")
    labels: Dict[str, Any] = Field(
        default_factory=dict,
        description="告警标签 (alertname / severity / instance 等)",
    )
    annotations: Dict[str, Any] = Field(
        default_factory=dict,
        description="描述信息 (summary / description / runbook_url)",
    )
    startsAt: str = Field(default="", description="告警开始时间 ISO8601")
    endsAt: str = Field(default="", description="告警结束时间 (resolved 才有)")
    generatorURL: str = Field(default="", description="原始告警规则 URL")
    fingerprint: str = Field(default="", description="告警指纹 (用于去重)")


class AlertmanagerPayload(BaseModel):
    """Alertmanager v4 webhook 完整 payload."""

    version: str = Field(default="4")
    groupKey: str = Field(default="")
    truncatedAlerts: int = Field(default=0)
    status: str = Field(default="firing")
    receiver: str = Field(default="")
    groupLabels: Dict[str, Any] = Field(default_factory=dict)
    commonLabels: Dict[str, Any] = Field(default_factory=dict)
    commonAnnotations: Dict[str, Any] = Field(default_factory=dict)
    externalURL: str = Field(default="")
    alerts: List[AlertmanagerAlert] = Field(default_factory=list)


# ============================================================
# History 落盘 (GET/DELETE 端点只读，写入由 Celery task 负责)
# ============================================================
HISTORY_DIR = Path(__file__).resolve().parents[3] / "data"
HISTORY_FILE = HISTORY_DIR / "alert_history.jsonl"


# ============================================================
# 告警 → 自然语言 query (供 LangGraph 理解)
# ============================================================
def _format_alert_as_query(alert: AlertmanagerAlert) -> str:
    """把结构化告警渲染成一段人可读、LLM 可理解的描述."""
    name = alert.labels.get("alertname", "UnknownAlert")
    severity = alert.labels.get("severity", "warning")
    instance = alert.labels.get("instance", "")
    service = alert.labels.get("service", "")
    summary = alert.annotations.get("summary", "")
    description = alert.annotations.get("description", "")
    runbook = alert.annotations.get("runbook_url", "")

    instance_text = instance or "(未指定)"
    parts = [
        f"[{severity.upper()}] {name} 告警触发",
        f"实例: {instance_text}",
    ]
    if service:
        parts.append(f"服务: {service}")
    if summary:
        parts.append(f"摘要: {summary}")
    if description:
        parts.append(f"描述: {description}")
    if alert.startsAt:
        parts.append(f"开始时间: {alert.startsAt}")
    if runbook:
        parts.append(f"应急手册: {runbook}")
    parts.append("请你作为 OnCall 工程师, 诊断上述告警根因并给出处置建议.")
    return "\n".join(parts)


# ============================================================
# 路由
# ============================================================
@router.post(
    "/alertmanager",
    summary="Alertmanager 告警接收 (Celery 全自动模式)",
    description=(
        "接收 Prometheus Alertmanager 标准 webhook payload, "
        "通过 Celery 任务队列异步启动 AIOps 诊断。"
        "立即返回 200 (Alertmanager 要求 5s 内响应), "
        "Celery worker 独立进程跑诊断, 结果写入 data/alert_history.jsonl. "
        "可通过 GET /webhook/history 查看后台跑过的诊断."
    ),
)
async def alertmanager_webhook(payload: AlertmanagerPayload):
    triggered: List[Dict[str, str]] = []
    skipped: List[str] = []
    for idx, alert in enumerate(payload.alerts):
        if alert.status != "firing":
            skipped.append(alert.labels.get("alertname", f"unknown_{idx}"))
            continue

        alertname = alert.labels.get("alertname", f"alert_{idx}")
        instance = alert.labels.get("instance", "unknown")
        fingerprint = alert.fingerprint or f"{alertname}-{instance}-{alert.startsAt}"
        session_id = f"alertmanager-{alertname}-{fingerprint[:12]}"

        query = _format_alert_as_query(alert)
        alert_meta = {
            "alertname": alertname,
            "severity": alert.labels.get("severity", ""),
            "instance": instance,
            "summary": alert.annotations.get("summary", ""),
            "fingerprint": fingerprint,
            "startsAt": alert.startsAt,
        }
        task = run_webhook_diagnosis.delay(query, session_id, alert_meta)
        triggered.append({"session_id": session_id, "task_id": task.id})

    logger.info(
        f"[webhook] 收到 {len(payload.alerts)} 条 alert, "
        f"入队 {len(triggered)} 条 Celery 任务, 跳过 {len(skipped)} 条(non-firing)"
    )
    return {
        "status": "accepted",
        "received": len(payload.alerts),
        "triggered": triggered,
        "skipped": skipped,
    }


@router.get(
    "/history",
    summary="查看 webhook 后台跑过的诊断",
    description="返回最近 N 条后台诊断记录, 按时间倒序.",
)
async def get_history(limit: int = 20):
    if not HISTORY_FILE.exists():
        return {"count": 0, "items": []}

    records: List[Dict[str, Any]] = []
    with HISTORY_FILE.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except Exception:
                continue

    records = list(reversed(records))[:limit]
    return {"count": len(records), "items": records}


@router.delete(
    "/history",
    summary="清空 webhook 诊断历史 (演示用)",
)
async def clear_history():
    if HISTORY_FILE.exists():
        HISTORY_FILE.unlink()
    return {"status": "cleared"}
