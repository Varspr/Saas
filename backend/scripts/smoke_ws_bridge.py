"""Проверка моста прогресса worker→WS через Redis pub/sub (на fakeredis).

Имитирует: Celery-воркер публикует событие синхронным клиентом, а
WS-обработчик API читает его асинхронным клиентом из того же канала.
Оба клиента делят один FakeServer (как один настоящий Redis).

    python backend/scripts/smoke_ws_bridge.py
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import fakeredis  # noqa: E402
import redis  # noqa: E402
import redis.asyncio as redis_async  # noqa: E402

# Подменяем оба фабричных метода на fakeredis с общим сервером —
# так sync-публикация и async-подписка видят один и тот же pub/sub.
_server = fakeredis.FakeServer()
redis.Redis.from_url = lambda *a, **k: fakeredis.FakeStrictRedis(server=_server)
redis_async.from_url = lambda *a, **k: fakeredis.FakeAsyncRedis(server=_server)

from app.events import job_channel, publish_job_update  # noqa: E402


async def main() -> int:
    sub = redis_async.from_url("redis://fake")
    pubsub = sub.pubsub()
    await pubsub.subscribe(job_channel("JOB1"))

    # «воркер» публикует серию обновлений (sync-клиент, как в Celery)
    stages = [("segmenting", 30), ("reconstructing", 55), ("done", 100)]

    received: list[dict] = []
    for status, progress in stages:
        publish_job_update("JOB1", status, progress)

    # читаем всё, что пришло в канал
    deadline = 2.0
    while len(received) < len(stages) and deadline > 0:
        msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=0.1)
        deadline -= 0.1
        if msg and msg.get("type") == "message":
            received.append(json.loads(msg["data"]))

    await pubsub.unsubscribe(job_channel("JOB1"))
    await pubsub.aclose()
    await sub.aclose()

    print("received:", received)
    statuses = [m["status"] for m in received]
    assert statuses == ["segmenting", "reconstructing", "done"], statuses
    assert received[-1]["progress"] == 100
    print("\n✅ WS BRIDGE SMOKE PASSED — pub/sub worker→API работает.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
