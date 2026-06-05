"""FastAPI-приложение (Фаза 0).

Точка входа API. Поднимает таблицы, CORS, монтирует роутер заданий и (в
dev-режиме) отдаёт файлы локального хранилища по /storage/*.
"""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api import jobs
from app.config import settings
from app.database import Base, engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    # MVP: создаём таблицы напрямую. В проде заменить на Alembic-миграции.
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)

# Фронтенд (Next.js) ходит с другого origin
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # MVP. В проде сузить до домена фронтенда.
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(jobs.router, prefix="/api", tags=["jobs"])


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "mock_pipeline": settings.mock_pipeline}


# Dev-хранилище: отдаём файлы напрямую. В проде их раздаёт S3/R2/CDN.
if settings.use_local_storage:
    Path(settings.local_storage_dir).mkdir(parents=True, exist_ok=True)
    app.mount(
        "/storage",
        StaticFiles(directory=settings.local_storage_dir),
        name="storage",
    )
