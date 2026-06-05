"""Оркестрация пайплайна (связывает Фазы 1-4).

Один Celery-таск `process_job` проводит задание через все этапы, обновляя
статус и прогресс в БД после каждого шага. Артефакты каждого этапа
выгружаются в хранилище, чтобы их можно было дебажить и переиспользовать.

    URL/фото
       │  scraping.fetch_image / storage.download_file
       ▼
    input.png
       │  segmentation.segment            (SAM / mock)
       ▼
    clothing_clean.png
       │  reconstruction.reconstruct      (InstantMesh / mock)
       ▼
    clothing_mesh.obj + clothing_texture.png
       │  draping.drape                   (Blender cloth / mock)
       ▼
    output.glb
       │  rendering.render_previews       (Blender Cycles / mock)
       ▼
    preview/{front,side,back,three_quarter}.png
       │  storage.upload_file
       ▼
    готово
"""
from __future__ import annotations

import shutil
import tempfile
import traceback
from pathlib import Path

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.events import publish_job_update
from app.models import Job, JobStatus
from app.pipeline import draping, reconstruction, rendering, scraping, segmentation
from app.storage import storage
from app.worker.celery_app import celery_app


def _set(db: Session, job: Job, status: JobStatus, progress: int) -> None:
    job.status = status
    job.progress = progress
    db.commit()
    # Уведомляем WebSocket-подписчиков (Redis pub/sub)
    publish_job_update(job.id, status.value, progress)


@celery_app.task(name="process_job", bind=True)
def process_job(self, job_id: str) -> dict:
    db = SessionLocal()
    job = db.get(Job, job_id)
    if job is None:
        db.close()
        return {"error": "job not found"}

    workdir = Path(tempfile.mkdtemp(prefix=f"job_{job_id}_"))
    try:
        # ── Фаза 1а: получить входное изображение ──
        _set(db, job, JobStatus.scraping, 10)
        input_img = workdir / "input.png"
        if job.input_type == "url":
            scraping.fetch_image(job.input_url, input_img)
        else:
            storage.download_file(job.input_image_key, input_img)

        # ── Фаза 1б: сегментация одежды (SAM) ──
        _set(db, job, JobStatus.segmenting, 30)
        clean_png = workdir / "clothing_clean.png"
        segmentation.segment(input_img, clean_png)
        job.clothing_clean_key = storage.upload_file(
            f"jobs/{job_id}/clothing_clean.png", clean_png, "image/png"
        )
        db.commit()

        # ── Фаза 2: 3D-реконструкция (InstantMesh) ──
        _set(db, job, JobStatus.reconstructing, 55)
        mesh_obj = workdir / "clothing_mesh.obj"
        texture_png = workdir / "clothing_texture.png"
        reconstruction.reconstruct(clean_png, mesh_obj, texture_png)
        job.mesh_key = storage.upload_file(
            f"jobs/{job_id}/clothing_mesh.obj", mesh_obj, "model/obj"
        )
        job.texture_key = storage.upload_file(
            f"jobs/{job_id}/clothing_texture.png", texture_png, "image/png"
        )
        db.commit()

        # ── Фаза 3: надевание на тело (тело от роста/веса + cloth) ──
        _set(db, job, JobStatus.draping, 75)
        output_glb = workdir / "output.glb"
        draping.drape(mesh_obj, texture_png, output_glb,
                      height_cm=job.height_cm, weight_kg=job.weight_kg)

        # ── Фаза 4а: рендер 4 превью ──
        _set(db, job, JobStatus.rendering, 90)
        preview_dir = workdir / "preview"
        previews = rendering.render_previews(output_glb, clean_png, preview_dir)

        # ── Фаза 4б: выгрузка результатов ──
        _set(db, job, JobStatus.uploading, 95)
        job.output_glb_key = storage.upload_file(
            f"jobs/{job_id}/output.glb", output_glb, "model/gltf-binary"
        )
        preview_keys = []
        for p in previews:
            key = f"jobs/{job_id}/preview/{p.name}"
            storage.upload_file(key, p, "image/png")
            preview_keys.append(key)
        job.preview_keys = preview_keys

        _set(db, job, JobStatus.done, 100)
        return {"job_id": job_id, "status": "done"}

    except Exception as exc:  # noqa: BLE001
        job.status = JobStatus.failed
        job.error = f"{exc}\n{traceback.format_exc()}"
        db.commit()
        publish_job_update(job.id, JobStatus.failed.value, job.progress or 0)
        raise
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
        db.close()
