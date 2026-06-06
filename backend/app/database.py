"""SQLAlchemy engine и сессии (Фаза 0)."""
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from app.config import settings

# Для SQLAlchemy + SQLite: разрешаем доступ из разных потоков (API и воркер) и
# даём таймаут на блокировки (API и Celery пишут в один файл).
_connect_args: dict = {}
if settings.database_url.startswith("sqlite"):
    _connect_args = {"check_same_thread": False, "timeout": 30}

engine = create_engine(
    settings.database_url, pool_pre_ping=True, future=True, connect_args=_connect_args
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """FastAPI-зависимость: сессия на запрос."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
