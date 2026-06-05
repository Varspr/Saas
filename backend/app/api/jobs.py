"""REST-эндпоинты заданий (Фаза 0).

| Метод | Путь                      | Описание                          |
|-------|---------------------------|-----------------------------------|
| POST  | /api/jobs                 | Создать задание (URL или файл)    |
| GET   | /api/jobs/{id}            | Статус + ссылки на результат      |
| GET   | /api/jobs/{id}/preview    | 4 PNG превью                      |
| GET   | /api/jobs/{id}/download   | Скачать .glb                      |
"""
from __future__ import annotations

import redis.asyncio as aioredis
from fastapi import (
    APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect,
)
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal, get_db
from app.events import job_channel
from app.models import Job, JobStatus
from app.schemas import JobResponse
from app.storage import storage

router = APIRouter()

_TERMINAL = (JobStatus.done, JobStatus.failed)


def _to_response(job: Job) -> JobResponse:
    """Собирает ответ, превращая ключи хранилища в публичные ссылки."""
    preview_urls = [storage.url(k) for k in (job.preview_keys or [])]
    return JobResponse(
        id=job.id,
        status=job.status,
        progress=job.progress or 0,
        error=job.error,
        height_cm=job.height_cm,
        weight_kg=job.weight_kg,
        output_glb_url=storage.url(job.output_glb_key) if job.output_glb_key else None,
        preview_urls=preview_urls,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


def _enqueue(job_id: str) -> None:
    # Импорт внутри функции: не тянуть пайплайн при загрузке API-модуля.
    from app.worker.tasks import process_job

    process_job.delay(job_id)


@router.post("/jobs", response_model=JobResponse, status_code=201)
async def create_job(request: Request, db: Session = Depends(get_db)):
    """Принимает либо JSON {"url": "..."}, либо multipart с полем file (или url)."""
    content_type = request.headers.get("content-type", "")

    job = Job(status=JobStatus.pending, progress=0, input_type="url")

    if content_type.startswith("application/json"):
        body = await request.json()
        url = body.get("url")
        if not url:
            raise HTTPException(422, "Поле 'url' обязательно")
        job.input_type = "url"
        job.input_url = str(url)
        job.height_cm = _coerce_int(body.get("height_cm"), 120, 220)
        job.weight_kg = _coerce_int(body.get("weight_kg"), 30, 250)
        db.add(job)
        db.commit()

    elif content_type.startswith("multipart/form-data"):
        form = await request.form()
        upload = form.get("file")
        url = form.get("url")

        job.height_cm = _coerce_int(form.get("height_cm"), 120, 220)
        job.weight_kg = _coerce_int(form.get("weight_kg"), 30, 250)
        db.add(job)
        db.flush()  # получить job.id до загрузки файла

        if upload is not None and getattr(upload, "filename", None):
            data = await upload.read()
            if len(data) > settings.max_upload_mb * 1024 * 1024:
                raise HTTPException(413, f"Файл больше {settings.max_upload_mb} МБ")
            ext = _ext_from_name(upload.filename)
            key = f"jobs/{job.id}/input{ext}"
            storage.upload_bytes(key, data, content_type=upload.content_type or "image/jpeg")
            job.input_type = "file"
            job.input_image_key = key
        elif url:
            job.input_type = "url"
            job.input_url = str(url)
        else:
            raise HTTPException(422, "Нужен либо файл 'file', либо поле 'url'")

        db.commit()
    else:
        raise HTTPException(415, "Ожидается application/json или multipart/form-data")

    db.refresh(job)
    _enqueue(job.id)
    return _to_response(job)


@router.get("/jobs/{job_id}", response_model=JobResponse)
def get_job(job_id: str, db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "Задание не найдено")
    return _to_response(job)


@router.get("/jobs/{job_id}/preview")
def get_preview(job_id: str, db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "Задание не найдено")
    return {"preview_urls": [storage.url(k) for k in (job.preview_keys or [])]}


@router.get("/jobs/{job_id}/download")
def download_glb(job_id: str, db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "Задание не найдено")
    if not job.output_glb_key:
        raise HTTPException(409, "Результат ещё не готов")
    return RedirectResponse(storage.url(job.output_glb_key))


@router.websocket("/ws/jobs/{job_id}")
async def job_ws(websocket: WebSocket, job_id: str):
    """Прогресс задания в реальном времени (замена polling).

    Поток: сразу отдаём текущий снимок, затем на каждый сигнал из Redis
    pub/sub перечитываем состояние из БД и шлём клиенту. Закрываемся, когда
    задание в терминальном статусе (done/failed). Каждое сообщение — полный
    JobResponse (тот же формат, что у REST), фронт просто заменяет состояние.
    """
    await websocket.accept()

    # 1. Начальный снимок — работает даже без Redis (важно для холодного клиента,
    #    подключившегося к уже готовому заданию).
    if await _send_snapshot(websocket, job_id):
        await websocket.close()
        return

    # 2. Подписка на обновления задания.
    r = aioredis.from_url(settings.redis_url)
    pubsub = r.pubsub()
    try:
        await pubsub.subscribe(job_channel(job_id))
        while True:
            # timeout=15 — серверный keepalive/страховка от пропущенного события,
            # клиент при этом НЕ опрашивает (никакого polling на фронте).
            await pubsub.get_message(ignore_subscribe_messages=True, timeout=15.0)
            if await _send_snapshot(websocket, job_id):
                break
    except WebSocketDisconnect:
        pass
    finally:
        try:
            await pubsub.unsubscribe(job_channel(job_id))
            await pubsub.aclose()
        except Exception:
            pass
        await r.aclose()
        try:
            await websocket.close()
        except Exception:
            pass


async def _send_snapshot(websocket: WebSocket, job_id: str) -> bool:
    """Шлёт текущий JobResponse. Возвращает True, если задание терминально."""
    db = SessionLocal()
    try:
        job = db.get(Job, job_id)
        if job is None:
            await websocket.send_json({"error": "Задание не найдено"})
            return True
        await websocket.send_text(_to_response(job).model_dump_json())
        return job.status in _TERMINAL
    except WebSocketDisconnect:
        return True
    finally:
        db.close()


def _ext_from_name(name: str) -> str:
    name = (name or "").lower()
    for ext in (".png", ".jpg", ".jpeg", ".webp"):
        if name.endswith(ext):
            return ext
    return ".jpg"


def _coerce_int(value, lo: int, hi: int) -> int | None:
    """Парсит и зажимает число в [lo, hi]; None если не число."""
    try:
        return max(lo, min(hi, int(float(value))))
    except (TypeError, ValueError):
        return None
