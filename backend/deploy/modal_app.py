"""Опциональный serverless-вариант GPU-воркера на Modal (Вариант 3 в DEPLOY-GPU.md).

Идея: вместо постоянно живого Celery-воркера на A100 — GPU-функция «по запросу».
Она поднимается на время обработки одного задания и гаснет (scale-to-zero),
что дешевле при неравномерной нагрузке. Celery-таск в этом варианте лишь
вызывает Modal-функцию (см. ниже enqueue-пример).

Деплой:
    pip install modal && modal token new
    modal deploy backend/deploy/modal_app.py

Перед деплоем создать секрет с переменными окружения воркера:
    modal secret create tryon-env \
        DATABASE_URL=... REDIS_URL=... \
        USE_LOCAL_STORAGE=false S3_ENDPOINT_URL=... S3_BUCKET=... \
        S3_ACCESS_KEY_ID=... S3_SECRET_ACCESS_KEY=... \
        MOCK_PIPELINE=false
"""
from pathlib import Path

import modal

BACKEND_DIR = Path(__file__).resolve().parents[1]

# Переиспользуем тот же GPU-Dockerfile, что и для RunPod/compose.
image = modal.Image.from_dockerfile(
    str(BACKEND_DIR / "Dockerfile.worker.gpu"),
    context_dir=str(BACKEND_DIR),
)

# Веса между вызовами живут в персистентном Modal Volume (аналог /models).
models_volume = modal.Volume.from_name("tryon-models", create_if_missing=True)

app = modal.App("tryon-worker")


@app.function(
    image=image,
    gpu="A100",
    timeout=15 * 60,                     # как task_time_limit в Celery
    volumes={"/models": models_volume},
    secrets=[modal.Secret.from_name("tryon-env")],
    scaledown_window=60,                 # погасить через 60 c простоя
)
def process_job_remote(job_id: str) -> dict:
    """Обрабатывает одно задание на GPU. Переиспользует ту же оркестрацию."""
    import subprocess

    # Догрузить веса при первом холодном старте (идемпотентно).
    subprocess.run(["/opt/app/scripts/download_models.sh"], check=True)
    models_volume.commit()

    # Та же логика пайплайна, что и в Celery-воркере (eager-вызов таска).
    from app.worker.tasks import process_job
    return process_job.apply(args=[job_id]).get()


# ── Как ставить задание из API/Celery в этом варианте ──
#
# В app/api/jobs.py::_enqueue заменить celery .delay на вызов Modal-функции:
#
#     import modal
#     fn = modal.Function.from_name("tryon-worker", "process_job_remote")
#     fn.spawn(job_id)          # неблокирующе, как .delay()
#
# Тогда Redis/Celery нужны только для лёгких задач (или не нужны вовсе —
# Modal сам очередит вызовы). Статус по-прежнему пишется в Postgres внутри
# process_job, фронтенд опрашивает GET /api/jobs/{id} как и раньше.
