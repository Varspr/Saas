"""Настройки приложения (Фаза 0).

Все значения берутся из переменных окружения / .env. Дефолты подобраны так,
чтобы приложение поднималось в mock-режиме без внешних ключей.
"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # ── App ──
    app_name: str = "AI Virtual Try-On"
    environment: str = "development"
    public_api_base_url: str = "http://localhost:8000"

    # ── Database (Фаза 0) ──
    database_url: str = "postgresql+psycopg://tryon:tryon@db:5432/tryon"

    # ── Redis / Celery (Фаза 0) ──
    redis_url: str = "redis://redis:6379/0"
    # eager=true → задача выполняется синхронно прямо в процессе API,
    # без Redis и отдельного воркера. Удобно для локального запуска «на посмотреть».
    celery_task_always_eager: bool = False

    # ── Storage S3/R2 (Фаза 0/4) ──
    use_local_storage: bool = True
    local_storage_dir: str = "/data/storage"
    s3_endpoint_url: str | None = None
    s3_region: str = "auto"
    s3_bucket: str = "tryon"
    s3_access_key_id: str | None = None
    s3_secret_access_key: str | None = None
    s3_public_base_url: str | None = None

    # ── Pipeline (Фазы 1-4) ──
    # mock_pipeline=True  → CPU-заглушки (Pillow/trimesh), без GPU.
    # mock_pipeline=False → реальные SAM + InstantMesh + Blender.
    mock_pipeline: bool = True
    sam_checkpoint: str = "/models/sam_vit_h_4b8939.pth"
    sam_model_type: str = "vit_h"
    instantmesh_repo: str = "/opt/InstantMesh"
    instantmesh_config: str = "/opt/InstantMesh/configs/instant-mesh-large.yaml"
    blender_bin: str = "blender"
    body_mesh_path: str = "/assets/body_tpose.obj"

    # Движок тела:
    #   "parametric" — trimesh-манекен из сечений (без Blender, стилизованный)
    #   "mpfb"       — реалистичный манекен MakeHuman/MPFB2 в Blender (как на фото)
    #   "smplx"      — SMPL-X (нужна коммерческая лицензия; scaffold)
    body_engine: str = "parametric"
    body_gender: str = "male"   # male | female | neutral (для MPFB)

    # SMPL-X (scaffold, по умолчанию выключен)
    use_smplx: bool = False
    smplx_model_path: str = "/models/smplx"

    # Метод примерки: "auto" | "mock" | "blender".
    #   auto    — Blender, если он установлен (физика ткани на CPU), иначе mock.
    #   mock    — статичная облегающая одежда без симуляции (быстро, без Blender).
    #   blender — всегда cloth simulation в Blender (нужен установленный blender).
    # Физика ткани НЕ требует GPU — её можно включить и в mock-AI режиме.
    drape_backend: str = "auto"

    # Параметры тела по умолчанию (если пользователь не задал)
    default_height_cm: int = 175
    default_weight_kg: int = 70

    # ── Job ──
    max_upload_mb: int = 15

    # Celery читает именно эти имена
    @property
    def celery_broker_url(self) -> str:
        return self.redis_url

    @property
    def celery_result_backend(self) -> str:
        return self.redis_url


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
