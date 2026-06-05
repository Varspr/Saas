# Запуск GPU-воркера (real-режим)

GPU-образ воркера — `backend/Dockerfile.worker.gpu`. Внутри: CUDA 12.1 +
PyTorch 2.1 + xformers + Segment Anything + InstantMesh (+ nvdiffrast) +
Blender 4.2 + код приложения. Веса моделей не зашиты в образ — качаются на
старте в volume `/models` (`entrypoint.sh` → `download_models.sh`).

> Образ собирается и работает только на машине с NVIDIA-GPU и установленным
> `nvidia-container-toolkit`. На обычном ноутбуке (без GPU) используйте
> mock-режим из основного README.

---

## Что внутри образа

| Слой | Назначение | Фаза |
|------|-----------|------|
| `nvidia/cuda:12.1.1-cudnn8-devel` | CUDA toolkit (нужен для nvdiffrast) | — |
| Blender 4.2 (`/opt/blender/blender`) | cloth sim + рендер превью | 3, 4 |
| torch 2.1 + xformers (cu121) | бэкенд нейросетей | 1, 2 |
| segment-anything + SAM ViT-H | сегментация одежды | 1 |
| InstantMesh + nvdiffrast | 2D → 3D-меш + UV-текстура | 2 |
| app (FastAPI/Celery/trimesh) | оркестрация и пайплайн | 0-4 |

Веса (качаются в `/models`): `sam_vit_h_4b8939.pth` (~2.4 ГБ) +
HuggingFace-веса InstantMesh/zero123plus (~10 ГБ, в `HF_HOME=/models/hf`).

---

## Вариант 1 — docker-compose на GPU-хосте (RunPod Pod / своя машина)

```bash
cp .env.example .env
# поднимаем api/redis/db (CPU) + worker (GPU)
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up --build
```

`docker-compose.gpu.yml` уже:
- собирает воркер из `Dockerfile.worker.gpu`,
- ставит `MOCK_PIPELINE=false`,
- монтирует volume `models` (веса переживают перезапуск),
- резервирует 1 GPU (`deploy.resources.reservations.devices`).

Первый запуск дольше: качаются веса. Чтобы первый job не ждал —
`PREWARM_INSTANTMESH=true` (прогрев на старте).

---

## Вариант 2 — образ собирается в CI, под только тянет его

Сборка вручную (для локального теста):

```bash
docker build -f backend/Dockerfile.worker.gpu -t <registry>/tryon-worker:gpu backend
docker push <registry>/tryon-worker:gpu
```

Но штатно образ собирает **GitHub Actions** — `.github/workflows/gpu-worker.yml`:
- триггеры: push в `main`, теги `v*`, ручной запуск (`workflow_dispatch`);
  на PR — только проверка сборки без пуша;
- пушит в **GHCR**: `ghcr.io/<owner>/<repo>/worker-gpu` (теги: `latest`,
  ветка, `sha-…`, semver из тегов);
- buildx-кэш слоёв в registry (`:buildcache`) — повторные сборки быстрые;
- освобождает диск раннера (образ большой).

Точный pull-ref (с digest) печатается в Summary каждого прогона.

**Видимость пакета:** свежий GHCR-пакет приватный. Сделайте его public
(Packages → package → Settings → Change visibility) **или** логиньтесь при
pull на поде:

```bash
echo "$GHCR_PAT" | docker login ghcr.io -u <owner> --password-stdin
```

На RunPod (или Lambda/любой GPU-VM):
1. Создать Pod с GPU (A100 80GB или 4090; InstantMesh влезает в ~16-24 ГБ VRAM).
2. Образ: `ghcr.io/<owner>/<repo>/worker-gpu:latest` (приватный — указать
   registry-креды в настройках пода).
3. Network Volume примонтировать в `/models` (чтобы веса качались один раз).
4. ENV: задать `REDIS_URL`, `DATABASE_URL` (managed Redis/Postgres),
   `USE_LOCAL_STORAGE=false` + S3/R2-ключи, `MOCK_PIPELINE=false`.
5. Команда контейнера — дефолтный `ENTRYPOINT` (поднимет Celery-воркер).

Через compose: в `docker-compose.gpu.yml` закомментировать `build:` у `worker`
и раскомментировать `image:` с нужным тегом.

API (`Dockerfile.api`), Redis и Postgres держим отдельно (дёшево, CPU) —
например, managed-сервисы или маленькая CPU-VM. Воркер общается с ними по сети
через `REDIS_URL`/`DATABASE_URL`.

```
[CPU VM/managed]                     [GPU VM: RunPod/Lambda]
  api (FastAPI) ──┐                    worker (этот образ)
  redis ──────────┼─ REDIS_URL ───────────┘
  postgres ───────┘   DATABASE_URL
        ▲                                   │
        └────────── S3/R2 (результаты) ◀─────┘
```

---

## Вариант 3 — serverless per-job (Modal)

Если нужен GPU «по запросу» без постоянно живого воркера — см.
`backend/deploy/modal_app.py`: одна job-функция на A100, поднимается на время
обработки и гасится. Celery-таск тогда лишь вызывает Modal-функцию.

```bash
pip install modal && modal token new
modal deploy backend/deploy/modal_app.py
```

---

## Подготовка весов (если не качать на старте)

Можно «запечь» веса в образ или положить на volume заранее:

```bash
# вручную в volume /models
docker run --rm -v tryon_models:/models tryon-worker:gpu \
  bash -lc 'MOCK_PIPELINE=false PREWARM_INSTANTMESH=true /opt/app/scripts/download_models.sh'
```

`body_tpose.obj` (SMPL-X T-pose, размер M) — положить в `./assets`
(монтируется в `/assets`). Без него подставляется примитивный манекен
(см. `backend/MODELS.md`).

---

## Проверка после старта

```bash
# внутри контейнера воркера
nvidia-smi                      # видит GPU?
ls -lh /models                  # веса на месте?
/opt/blender/blender --version  # Blender ок?
python -c "import torch; print(torch.cuda.is_available())"   # True
```

Затем создать задание через API и дождаться `status=done`. Тайминги из плана:
SAM + InstantMesh ~1-2 мин, Blender ~0.5-1.5 мин, итого 3-5 мин/задача.

---

## Стоимость (ориентир из плана)

| Ресурс | Цена |
|--------|------|
| GPU A100 (RunPod on-demand) | ~$1.5–2.5/час |
| S3/R2 | ~$0.015/ГБ/мес |
| Postgres managed | ~$20/мес |
| Redis managed | ~$15/мес |
| **1 задание** | **~$0.10–0.20** |

Экономия: гасить GPU-воркер при простое (Вариант 3 / autoscale to zero),
держать API+очередь на дешёвой CPU-инстанции постоянно.
