"""Pydantic-схемы запросов/ответов API."""
from datetime import datetime

from pydantic import BaseModel, HttpUrl

from app.models import JobStatus


class JobCreateURL(BaseModel):
    """Тело POST /api/jobs когда передаётся ссылка (на товар или картинку)."""

    url: HttpUrl
    height_cm: int | None = None   # рост модели тела, см
    weight_kg: int | None = None   # вес модели тела, кг


class JobResponse(BaseModel):
    """Ответ GET /api/jobs/{id} и POST /api/jobs.

    Ссылки (*_url) формируются в роутере из ключей хранилища — на presigned
    URL в проде или на /storage/... в dev.
    """

    id: str
    status: JobStatus
    progress: int
    error: str | None = None

    height_cm: int | None = None
    weight_kg: int | None = None

    output_glb_url: str | None = None
    preview_urls: list[str] = []

    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
