# AI Virtual Try-On SaaS — MVP

Пользователь вставляет ссылку или загружает фото одежды → сервис возвращает
3D-рендер этой одежды на стандартной 3D-модели тела (`.glb` + 4 превью PNG),
который можно крутить прямо в браузере (Three.js) и открыть в Blender.

Этот репозиторий — реализация технического плана из `mvp_plan.md`.

---

## Главная идея реализации: два режима

Тяжёлые модели (SAM, InstantMesh) и Blender-симуляция требуют GPU и
весов моделей (~15 GB). Чтобы можно было разрабатывать и тестировать
**весь пайплайн end-to-end на ноутбуке без GPU**, каждый шаг пайплайна
имеет два пути:

| Режим | Флаг | Что делает |
|-------|------|-----------|
| **mock** | `MOCK_PIPELINE=true` (по умолчанию) | CPU-заглушки на Pillow + trimesh. Реально гоняет очередь, БД, хранилище, отдаёт валидный `.glb` и PNG. |
| **real** | `MOCK_PIPELINE=false` | Настоящие SAM + InstantMesh + Blender на GPU-воркере. |

Переключение — один флаг в `.env`. Архитектура, API, очередь, БД и фронтенд
работают одинаково в обоих режимах. Это и есть «скелет», в который
вставляются реальные модели по мере готовности GPU-инфраструктуры.

---

## Карта плана → код

| Фаза плана | Где в коде |
|-----------|-----------|
| Фаза 0 — Инфраструктура (FastAPI, Celery, Redis, S3, PG) | `backend/app/main.py`, `worker/celery_app.py`, `storage.py`, `database.py`, `docker-compose.yml` |
| Фаза 1 — Скрейпинг + сегментация (Playwright, SAM) | `backend/app/pipeline/scraping.py`, `segmentation.py` |
| Фаза 2 — 3D-реконструкция (InstantMesh) | `backend/app/pipeline/reconstruction.py` |
| Фаза 3 — Надевание на тело (Blender cloth) | `backend/app/pipeline/draping.py`, `blender_scripts/drape_cloth.py` |
| Фаза 4 — Рендер + доставка (превью, Three.js) | `blender_scripts/render_preview.py`, `frontend/` |
| API эндпоинты | `backend/app/api/jobs.py` |
| Оркестрация пайплайна | `backend/app/worker/tasks.py` |

---

## Быстрый старт (mock, без GPU)

### Вариант А — Docker Compose (рекомендуется)

```bash
cp .env.example .env
docker compose up --build
# API:       http://localhost:8000/docs
# Frontend:  http://localhost:3000
```

### Вариант Б — локально без Docker

```bash
# 1. Зависимости (лёгкие, без torch)
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. Поднять Redis + Postgres (через Docker — только инфраструктуру)
docker compose up -d redis db

# 3. API
uvicorn app.main:app --reload

# 4. В другом терминале — воркер
celery -A app.worker.celery_app.celery_app worker --loglevel=info --concurrency=1
```

Фронтенд:

```bash
cd frontend
npm install
npm run dev
```

---

## Проверить пайплайн руками

```bash
# создать задание из URL картинки
curl -X POST http://localhost:8000/api/jobs \
  -H 'Content-Type: application/json' \
  -d '{"url": "https://upload.wikimedia.org/wikipedia/commons/2/24/Blue_Tshirt.jpg"}'

# -> {"id": "ab12...", "status": "pending", ...}

# опрос статуса
curl http://localhost:8000/api/jobs/ab12...

# когда status == "done":
#   output_glb_url  — .glb файл
#   preview_urls    — 4 PNG
```

---

## Прогресс в реальном времени (WebSocket)

Фронтенд не опрашивает статус (no polling) — он подписывается на
`ws://<api>/api/ws/jobs/{id}` и получает полный `Job` на каждом изменении.

```
worker ──publish(job:{id})──▶ Redis pub/sub ──▶ WS /api/ws/jobs/{id} ──▶ браузер
   (Celery, app/events.py)                       (app/api/jobs.py)        (lib/useJobStream.ts)
```

- Воркер на каждом этапе шлёт сигнал в Redis (`publish_job_update`).
- WS-эндпоинт сразу отдаёт текущий снимок, затем по каждому сигналу
  перечитывает состояние из БД и шлёт клиенту; закрывается на `done`/`failed`.
- Сообщение = тот же `JobResponse`, что и у REST. Источник истины — Postgres,
  pub/sub лишь будит обработчик (+ серверный keepalive 15 c как страховка).
- Если сокет недоступен, хук `useJobStream` мягко деградирует на разовый fetch
  (не на постоянный polling).

`GET /api/jobs/{id}` остаётся для дозабора/совместимости.

## Переход на real-режим (GPU)

Готовый GPU-образ воркера: `backend/Dockerfile.worker.gpu` (CUDA 12.1 +
PyTorch + SAM + InstantMesh + Blender). Запуск на GPU-хосте:

```bash
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up --build
```

**Где арендовать сервер, какие мощности брать и как подключить после покупки —
[АРЕНДА-GPU.md](АРЕНДА-GPU.md)** (пошагово, для начинающих).

**Деплой на RunPod (одна Pod = весь сервис) — [RUNPOD.md](RUNPOD.md)** (готовый
all-in-one образ собирает CI, RunPod его тянет).

Реалистичный манекен (как витринный, параметрический по росту/весу, через
MakeHuman/MPFB2, лицензия CC0) — [MANNEQUIN.md](MANNEQUIN.md). Включается
`BODY_ENGINE=mpfb`.

Технические детали деплоя (RunPod / Modal / Lambda, веса, тома) —
[DEPLOY-GPU.md](DEPLOY-GPU.md). Что качать и как настроить модели —
[backend/MODELS.md](backend/MODELS.md).

---

## Структура

```
backend/
  app/
    main.py            FastAPI приложение (Фаза 0)
    config.py          настройки (pydantic-settings)
    database.py        SQLAlchemy engine/session
    models.py          ORM: Job, JobStatus
    schemas.py         Pydantic-схемы ответов
    storage.py         S3/R2 + локальный fallback
    api/jobs.py        REST-эндпоинты
    worker/
      celery_app.py    конфиг Celery
      tasks.py         оркестрация пайплайна
    pipeline/
      scraping.py      Playwright (Фаза 1)
      segmentation.py  SAM (Фаза 1)
      reconstruction.py InstantMesh (Фаза 2)
      draping.py       вызов Blender (Фаза 3)
      blender_scripts/
        drape_cloth.py    cloth simulation
        render_preview.py 4 ракурса
    events.py          Redis pub/sub для прогресса (worker→WS)
    scripts/
      smoke_pipeline.py  end-to-end проверка mock-пайплайна
      smoke_api.py       end-to-end проверка API (+ WebSocket-снимок)
      smoke_ws_bridge.py проверка моста прогресса через pub/sub
      download_models.sh скачивание весов (real-режим)
    docker/
      entrypoint.sh      старт GPU-воркера
    deploy/
      modal_app.py       serverless GPU на Modal (опционально)
  requirements.txt       лёгкие зависимости (API + mock)
  requirements-gpu.txt   standalone deps для GPU-воркера
  Dockerfile.api         API-образ (CPU)
  Dockerfile.worker      воркер CPU/mock
  Dockerfile.worker.gpu  воркер GPU/real (CUDA+SAM+InstantMesh+Blender)
  MODELS.md              как поставить реальные модели
frontend/                Next.js + Three.js + live-прогресс по WebSocket
assets/                  body_tpose.obj (плейсхолдер)
docker-compose.yml       api + worker(mock) + redis + db + frontend
docker-compose.gpu.yml   override: воркер на GPU (real-режим)
.env.gpu.example         окружение для арендованной GPU-машины
АРЕНДА-GPU.md            где арендовать GPU, что брать, как подключить
RUNPOD.md                пошаговый деплой на RunPod (all-in-one)
MANNEQUIN.md             реалистичный манекен (MakeHuman/MPFB2)
DEPLOY-GPU.md            технические детали деплоя (RunPod/Modal/Lambda)
backend/Dockerfile.runpod   all-in-one образ (api+worker+redis+postgres)
deploy/gpu_vm_bootstrap.sh  one-command поднятие стека на свежей GPU-VM
.github/workflows/
  gpu-worker.yml         CI: сборка+пуш GPU-образа в GHCR (buildx-кэш)
```

---

## Что НЕ входит в MVP (см. план, раздел v2)

Кастомизация тела, несколько вещей сразу, анимация, обувь/аксессуары,
интеграция API магазинов — всё это вне текущего скелета.
