#!/usr/bin/env bash
# Локальный запуск БЕЗ Docker: API + весь пайплайн в одном процессе.
# Режим mock (без GPU) + eager (без Redis/воркера) + SQLite + локальные файлы.
#
# Использование:
#   cd backend
#   python3 -m venv .venv && source .venv/bin/activate
#   pip install -r requirements-local.txt
#   ./scripts/run_local.sh
# Затем открой http://localhost:8000/docs
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
DATA="$ROOT/.localdata"
mkdir -p "$DATA/storage"

export MOCK_PIPELINE=true            # CPU-заглушки, без GPU
export CELERY_TASK_ALWAYS_EAGER=true # задача выполняется в процессе API, без Redis
export USE_LOCAL_STORAGE=true
export LOCAL_STORAGE_DIR="$DATA/storage"
export BODY_MESH_PATH="$DATA/body.obj"
export DATABASE_URL="sqlite+pysqlite:///$DATA/app.db"
export PUBLIC_API_BASE_URL="http://localhost:8000"

cd "$ROOT/backend"
echo "API → http://localhost:8000  (docs: /docs)"
exec uvicorn app.main:app --host 127.0.0.1 --port 8000
