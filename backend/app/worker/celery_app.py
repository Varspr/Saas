"""Конфигурация Celery (Фаза 0).

Запуск воркера:
    celery -A app.worker.celery_app.celery_app worker --loglevel=info --concurrency=1

concurrency=1 — GPU-задачи тяжёлые и не делятся на одной карте.
"""
from celery import Celery

from app.config import settings

celery_app = Celery(
    "tryon",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    # Жёсткий лимит на задачу: пайплайн ~3-5 мин, ставим запас.
    task_time_limit=15 * 60,
    task_soft_time_limit=14 * 60,
    worker_prefetch_multiplier=1,  # не хватать вперёд тяжёлые задачи
    worker_max_tasks_per_child=20,  # перезапуск воркера: чистка GPU-памяти
    # Локальный запуск без Redis/воркера (CELERY_TASK_ALWAYS_EAGER=true)
    task_always_eager=settings.celery_task_always_eager,
    task_eager_propagates=settings.celery_task_always_eager,
)

# Регистрируем задачи
from app.worker import tasks  # noqa: E402,F401
