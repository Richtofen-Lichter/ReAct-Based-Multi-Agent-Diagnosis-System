"""Celery 应用实例 — 独立模块避免与 app 包命名冲突.

broker: Redis DB 1 (独立于 RAG Chat 的 DB 0)
result_backend: Redis DB 2 (存储任务结果, TTL 7 天)

启动 worker:
  celery -A celery_worker worker --concurrency=1 --loglevel=info --pool=solo
"""

from celery import Celery

from app.config import settings

celery_app = Celery(
    "aiops",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Shanghai",
    enable_utc=True,
    result_expires=60 * 60 * 24 * 7,  # 7 天
    broker_transport_options={"visibility_timeout": 3600},
)

# 确保 Celery worker 启动时能发现 diagnosis task
# 注意: import app.xxx 会把 app 包绑定到当前命名空间, 所以 Celery 变量不能叫 app
import app.celery_tasks.diagnosis  # noqa: F401
