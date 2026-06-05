"""Шина прогресса заданий через Redis pub/sub.

API и Celery-воркер — разные процессы, поэтому воркер не может слать в
WebSocket напрямую. Схема:

    worker ──publish(job:{id})──▶ Redis ──▶ WS-эндпоинт API ──▶ браузер

Воркер на каждом шаге пайплайна публикует событие в канал job:{id}
(publish_job_update). WebSocket-обработчик подписан на этот канал и по сигналу
перечитывает актуальное состояние из БД и шлёт его клиенту.
Содержимое сообщения — лишь триггер; источник истины — Postgres.
"""
from __future__ import annotations

import json

import redis

from app.config import settings

_sync_client: redis.Redis | None = None


def job_channel(job_id: str) -> str:
    return f"job:{job_id}"


def _client() -> redis.Redis:
    global _sync_client
    if _sync_client is None:
        _sync_client = redis.Redis.from_url(settings.redis_url)
    return _sync_client


def publish_job_update(job_id: str, status: str, progress: int) -> None:
    """Синхронный вызов из Celery-воркера. Ошибки pub/sub не валят пайплайн."""
    try:
        _client().publish(
            job_channel(job_id),
            json.dumps({"status": status, "progress": progress}),
        )
    except Exception:
        pass
