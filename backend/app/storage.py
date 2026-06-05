"""Хранилище файлов (Фаза 0/4).

Унифицирует два бэкенда:
  • local  — пишет в LOCAL_STORAGE_DIR, ссылки идут через API (/storage/...).
             Для разработки без AWS/Cloudflare.
  • S3/R2  — boto3, presigned URL. Для прода.

Ключи (key) — это относительные пути внутри бакета, например
"jobs/<job_id>/output.glb". Один и тот же код пайплайна работает с обоими
бэкендами.
"""
from __future__ import annotations

from pathlib import Path

from app.config import settings


class Storage:
    def __init__(self) -> None:
        self.local = settings.use_local_storage
        if self.local:
            Path(settings.local_storage_dir).mkdir(parents=True, exist_ok=True)
            self._client = None
        else:
            import boto3
            from botocore.client import Config as BotoConfig

            self._client = boto3.client(
                "s3",
                endpoint_url=settings.s3_endpoint_url,
                region_name=settings.s3_region,
                aws_access_key_id=settings.s3_access_key_id,
                aws_secret_access_key=settings.s3_secret_access_key,
                config=BotoConfig(signature_version="s3v4"),
            )

    # ── запись ──
    def upload_bytes(self, key: str, data: bytes,
                     content_type: str = "application/octet-stream") -> str:
        if self.local:
            path = self._local_path(key)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        else:
            self._client.put_object(
                Bucket=settings.s3_bucket, Key=key,
                Body=data, ContentType=content_type,
            )
        return key

    def upload_file(self, key: str, local_path: str | Path,
                    content_type: str = "application/octet-stream") -> str:
        data = Path(local_path).read_bytes()
        return self.upload_bytes(key, data, content_type)

    # ── чтение ──
    def download_file(self, key: str, local_path: str | Path) -> Path:
        local_path = Path(local_path)
        local_path.parent.mkdir(parents=True, exist_ok=True)
        if self.local:
            local_path.write_bytes(self._local_path(key).read_bytes())
        else:
            self._client.download_file(settings.s3_bucket, key, str(local_path))
        return local_path

    def exists(self, key: str) -> bool:
        if self.local:
            return self._local_path(key).exists()
        try:
            self._client.head_object(Bucket=settings.s3_bucket, Key=key)
            return True
        except Exception:
            return False

    # ── публичная ссылка ──
    def url(self, key: str, expires: int = 3600) -> str:
        """Ссылка для отдачи пользователю/фронтенду."""
        if self.local:
            # отдаём через API: app.main монтирует /storage
            base = settings.public_api_base_url.rstrip("/")
            return f"{base}/storage/{key}"
        if settings.s3_public_base_url:
            return f"{settings.s3_public_base_url.rstrip('/')}/{key}"
        return self._client.generate_presigned_url(
            "get_object",
            Params={"Bucket": settings.s3_bucket, "Key": key},
            ExpiresIn=expires,
        )

    # ── helpers ──
    def _local_path(self, key: str) -> Path:
        return Path(settings.local_storage_dir) / key


# Синглтон на процесс
storage = Storage()
