#!/usr/bin/env bash
# All-in-one старт для RunPod: Redis + API + Celery-воркер. БД — SQLite.
#
# Postgres НЕ используем намеренно: его data-каталог нельзя chown на сетевом
# volume RunPod (/data) → «Operation not permitted» → контейнер падал в
# бесконечный перезапуск. SQLite не требует отдельного процесса и прав на volume,
# и для одного контейнера-MVP полностью достаточен.
set -euo pipefail

mkdir -p "${LOCAL_STORAGE_DIR:-/data/storage}" "${MODELS_DIR:-/data/models}" /var/tryon

echo "[runpod] MOCK_PIPELINE=${MOCK_PIPELINE:-false} BODY_ENGINE=${BODY_ENGINE:-parametric} DRAPE_BACKEND=${DRAPE_BACKEND:-auto}"

# Redis — брокер Celery
redis-server --daemonize yes --bind 127.0.0.1

command -v nvidia-smi >/dev/null && nvidia-smi -L || echo "[runpod] nvidia-smi не найден (CPU/mock?)"

# Веса моделей (только real-режим)
if [ "${MOCK_PIPELINE:-false}" != "true" ]; then
  /opt/app/scripts/download_models.sh || echo "[runpod] download_models: предупреждение"
fi

cd /opt/app
# API в фоне
uvicorn app.main:app --host 0.0.0.0 --port 8000 &
echo "[runpod] API на :8000, воркер запускается..."

# Воркер на переднем плане (держит контейнер живым)
exec celery -A app.worker.celery_app.celery_app worker \
  --loglevel="${CELERY_LOGLEVEL:-info}" --concurrency="${CELERY_CONCURRENCY:-1}"
