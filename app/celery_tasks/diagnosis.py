"""Webhook 全自动诊断 Celery 任务."""

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from loguru import logger

from celery_worker import celery_app
from app.services import aiops_service

HISTORY_FILE = Path(__file__).resolve().parents[2] / "data" / "alert_history.jsonl"


def _append_history(record: Dict[str, Any]) -> None:
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    import json
    with HISTORY_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


@celery_app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    autoretry_for=(Exception,),
)
def run_webhook_diagnosis(self, query: str, session_id: str, alert_meta: Dict[str, Any]) -> Dict[str, Any]:
    """后台跑 stream_diagnose, 收集事件 → 写 history.

    Celery worker 独立进程执行, 不阻塞 FastAPI.
    失败时自动重试 (3 次, 指数退避 30s/60s/120s).
    """
    started_at = datetime.now(timezone.utc).isoformat()
    events: List[Dict[str, Any]] = []
    final_report = ""
    selected_skill = ""
    error_msg = ""

    logger.info(
        f"[celery] 后台启动诊断 session={session_id} "
        f"alert={alert_meta.get('alertname')} retry={self.request.retries}"
    )

    async def _run() -> None:
        nonlocal selected_skill, final_report, events
        async for ev in aiops_service.stream_diagnose(query, session_id=session_id):
            events.append(ev)
            ev_type = ev.get("type", "")
            if ev_type == "skill_selected":
                selected_skill = ev.get("data", {}).get("skill", "")
            elif ev_type == "report":
                final_report = ev.get("data", {}).get("report", "")

    try:
        asyncio.run(_run())
    except Exception as e:
        error_msg = f"{type(e).__name__}: {e}"
        logger.exception(f"[celery] 诊断异常 session={session_id}: {e}")

        # LLM / 网络临时错误 → 重试; 逻辑错误 (如参数问题) → 不重试
        if self.request.retries < self.max_retries:
            retry_delay = 30 * (2 ** self.request.retries)
            logger.warning(
                f"[celery] 将在 {retry_delay}s 后重试 session={session_id} "
                f"({self.request.retries + 1}/{self.max_retries})"
            )
            raise self.retry(exc=e, countdown=retry_delay)

    finished_at = datetime.now(timezone.utc).isoformat()

    record = {
        "session_id": session_id,
        "alert": alert_meta,
        "query": query,
        "started_at": started_at,
        "finished_at": finished_at,
        "selected_skill": selected_skill,
        "report": final_report,
        "event_count": len(events),
        "error": error_msg,
        "celery_task_id": self.request.id,
    }
    _append_history(record)

    logger.info(
        f"[celery] 诊断完成 session={session_id} "
        f"skill={selected_skill or '(未选中)'} "
        f"events={len(events)} report_len={len(final_report)}"
    )
    return {
        "session_id": session_id,
        "selected_skill": selected_skill,
        "report_len": len(final_report),
        "event_count": len(events),
        "error": error_msg,
    }
