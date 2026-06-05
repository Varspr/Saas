#!/usr/bin/env bash
# All-in-one старт для RunPod: Postgres + Redis + API + Celery-воркер в одном
# контейнере. Для MVP/демо («одна Pod = весь сервис»). НЕ для прод-нагрузки.
set -euo pipefail

STORAGE="${LOCAL_STORAGE_DIR:-/data/storage}"
PGDATA="${PGDATA:-/data/pgdata}"
mkdir -p "$STORAGE" "$PGDATA"

echo "[runpod] MOCK_PIPELINE=${MOCK_PIPELINE:-false} BODY_ENGINE=${BODY_ENGINE:-parametric} DRAPE_BACKEND=${DRAPE_BACKEND:-auto}"

PGBIN="$(ls -d /usr/lib/postgresql/*/bin | head -1)"

# ── PostgreSQL (данные на volume /data → переживают перезапуск) ──
if [ ! -s "${PGDATA}/PG_VERSION" ]; then
  echo "[runpod] initdb..."
  chown -R postgres:postgres "$PGDATA"
  su postgres -c "${PGBIN}/initdb -D ${PGDATA}"
fi
chown -R postgres:postgres "$PGDATA"
su postgres -c "${PGBIN}/pg_ctl -D ${PGDATA} -o '-c listen_addresses=127.0.0.1' -w start"

su postgres -c "psql -tAc \"SELECT 1 FROM pg_roles WHERE rolname='tryon'\"" | grep -q 1 \
  || su postgres -c "psql -c \"CREATE USER tryon WITH PASSWORD 'tryon';\""
su postgres -c "psql -tAc \"SELECT 1 FROM pg_database WHERE datname='tryon'\"" | grep -q 1 \
  || su postgres -c "psql -c \"CREATE DATABASE tryon OWNER tryon;\""

# ── Redis ──
redis-server --daemonize yes --bind 127.0.0.1

# ── GPU info ──
command -v nvidia-smi >/dev/null && nvidia-smi -L || echo "[runpod] nvidia-smi не найден"

# ── Модели (только real-режим) ──
if [ "${MOCK_PIPELINE:-false}" != "true" ]; then
  /opt/app/scripts/download_models.sh || echo "[runpod] download_models: предупреждение"
fi

# ── API в фоне ──
cd /opt/app
uvicorn app.main:app --host 0.0.0.0 --port 8000 &

echo "[runpod] API на :8000, воркер запускается..."
# ── Воркер на переднем плане (держит контейнер живым) ──
exec celery -A app.worker.celery_app.celery_app worker \
  --loglevel="${CELERY_LOGLEVEL:-info}" --concurrency="${CELERY_CONCURRENCY:-1}"
