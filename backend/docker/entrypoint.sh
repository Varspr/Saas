#!/usr/bin/env bash
# Entrypoint GPU-воркера: убеждаемся, что веса на месте, потом запускаем Celery.
set -euo pipefail

echo "[entrypoint] MOCK_PIPELINE=${MOCK_PIPELINE:-false}"

# Диагностика GPU (не валим контейнер, если nvidia-smi нет — например, mock).
if command -v nvidia-smi >/dev/null 2>&1; then
  nvidia-smi --query-gpu=name,memory.total --format=csv,noheader || true
else
  echo "[entrypoint] nvidia-smi не найден (CPU/mock?)"
fi

# В real-режиме докачиваем веса (на персистентный volume /models).
if [ "${MOCK_PIPELINE:-false}" != "true" ]; then
  /opt/app/scripts/download_models.sh
fi

exec celery -A app.worker.celery_app.celery_app worker \
  --loglevel="${CELERY_LOGLEVEL:-info}" \
  --concurrency="${CELERY_CONCURRENCY:-1}"
