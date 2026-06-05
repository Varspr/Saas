"""ORM-модели (Фаза 0).

Для MVP — одна таблица `jobs`. Пользователи/аутентификация — v2, поэтому
поле user_id опционально и пока не используется.
"""
import enum
import uuid
from datetime import datetime

from sqlalchemy import JSON, Column, DateTime, Enum, Integer, String, Text

from app.database import Base


class JobStatus(str, enum.Enum):
    """Статусы соответствуют этапам пайплайна из плана."""

    pending = "pending"            # создано, ждёт воркера
    scraping = "scraping"          # Фаза 1: получаем фото
    segmenting = "segmenting"      # Фаза 1: SAM
    reconstructing = "reconstructing"  # Фаза 2: InstantMesh
    draping = "draping"            # Фаза 3: Blender cloth
    rendering = "rendering"        # Фаза 4: превью
    uploading = "uploading"        # выгрузка результатов в S3
    done = "done"
    failed = "failed"


def _uuid() -> str:
    return uuid.uuid4().hex


class Job(Base):
    __tablename__ = "jobs"

    id = Column(String(32), primary_key=True, default=_uuid)
    status = Column(Enum(JobStatus), default=JobStatus.pending, nullable=False)
    progress = Column(Integer, default=0)  # 0..100 для прогресс-бара во фронте

    # Опционально (v2): привязка к пользователю
    user_id = Column(String(32), nullable=True)

    # ── Вход ──
    input_type = Column(String(16), nullable=False)  # "url" | "file"
    input_url = Column(Text, nullable=True)
    input_image_key = Column(Text, nullable=True)     # ключ загруженного файла

    # Параметры тела (Фаза 3): рост/вес → форма манекена
    height_cm = Column(Integer, nullable=True)
    weight_kg = Column(Integer, nullable=True)

    # ── Промежуточные артефакты (ключи в хранилище) ──
    clothing_clean_key = Column(Text, nullable=True)  # Фаза 1 результат
    mesh_key = Column(Text, nullable=True)            # Фаза 2: .obj/.glb меша
    texture_key = Column(Text, nullable=True)         # Фаза 2: текстура

    # ── Результаты ──
    output_glb_key = Column(Text, nullable=True)      # Фаза 3 итог
    preview_keys = Column(JSON, nullable=True)        # Фаза 4: list[str] из 4 PNG

    error = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
