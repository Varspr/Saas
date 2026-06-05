# Выгрузка на RunPod — пошагово

Деплоим по схеме **«одна Pod = весь сервис»**: один контейнер, внутри которого
API + воркер + Redis + Postgres. Для MVP/демо это проще всего — не нужно ничего
кроме одной арендованной GPU. (Прод-схема с раздельными сервисами — в
[DEPLOY-GPU.md](DEPLOY-GPU.md).)

Образ собирает CI и кладёт в GHCR, RunPod его просто тянет. Сборку на маке делать
не нужно.

---

## Что понадобится

- Аккаунт на GitHub (код + автосборка образа).
- Аккаунт на RunPod (runpod.io) + немного кредитов ($10 хватит на тесты).
- ~30–60 минут на первый прогон (сборка образа в CI + скачивание весов).

---

## Шаг 1. Запушить код в GitHub → CI соберёт образ

```bash
cd /Users/uliakaptil/Desktop/Saas
git init && git add -A && git commit -m "tryon mvp"
gh repo create tryon --private --source=. --push   # или вручную через сайт
```

После пуша в ветку `main` запустится workflow `.github/workflows/gpu-worker.yml`.
Он соберёт два образа и положит их в GHCR:
- `ghcr.io/<owner>/<repo>/worker-gpu` — GPU-воркер;
- `ghcr.io/<owner>/<repo>/worker-runpod` — **all-in-one для RunPod** (его и берём).

Дождись зелёной галочки в разделе **Actions** (~20–40 мин первый раз).

### Сделать образ доступным для RunPod
Свежий GHCR-пакет приватный. Проще всего — сделать его **public**:
GitHub → твой профиль → **Packages** → `worker-runpod` → **Package settings** →
**Change visibility** → Public.

(Либо оставить приватным и добавить в RunPod registry-креды — см. Troubleshooting.)

---

## Шаг 2. Создать Pod на RunPod

1. runpod.io → **Pods** → **Deploy**.
2. **GPU**: выбери **RTX 4090** (24 ГБ) — оптимально по цене. (A100 — если нужна скорость.)
3. **Pod Template** → **Custom / Edit Template**:
   - **Container Image**: `ghcr.io/<owner>/<repo>/worker-runpod:latest`
   - **Container Disk**: 30 GB
   - **Volume Disk**: 60 GB, **Volume Mount Path**: `/data`
     (сюда лягут веса моделей и БД — переживут перезапуск Pod)
   - **Expose HTTP Ports**: `8000`
4. **Environment Variables** — на ПЕРВЫЙ запуск ставим mock (быстрая проверка
   деплоя без скачивания весов):
   ```
   MOCK_PIPELINE = true
   ```
5. **Deploy**.

---

## Шаг 3. Проверка деплоя (mock, дёшево)

1. Дождись статуса Pod = **Running**.
2. У Pod появится HTTP-эндпоинт вида
   `https://<pod-id>-8000.proxy.runpod.net` (кнопка **Connect → HTTP 8000**).
3. Открой `<этот-url>/docs` — должна открыться страница API.
4. Через `POST /api/jobs` (**Try it out** → загрузить фото) создай задание →
   `GET /api/jobs/{id}` должно дойти до `done` с ссылками на `.glb` и превью.

Если это работает — деплой исправен. Теперь включаем настоящий AI.

---

## Шаг 4. Переключить на real-режим (GPU)

В настройках Pod → **Environment Variables** замени/добавь:
```
MOCK_PIPELINE   = false
DRAPE_BACKEND   = blender
BODY_ENGINE     = parametric        # надёжно для первого прогона; mpfb включим позже
PUBLIC_API_BASE_URL = https://<pod-id>-8000.proxy.runpod.net
PREWARM_INSTANTMESH = true
```
Сохрани и **перезапусти** Pod (Restart).

> `PUBLIC_API_BASE_URL` важен: по нему формируются ссылки на готовые файлы.
> Подставь именно тот proxy-URL, что дал RunPod.

Первый real-запуск качает веса (~13 ГБ на volume `/data`) — несколько минут.
Смотри логи: RunPod → Pod → **Logs**.

### Проверить готовность
В RunPod открой **Connect → Web Terminal** (или SSH) и выполни:
```bash
python /opt/app/scripts/gpu_check.py
```
Должно быть ✅ по nvidia-smi, torch.cuda, Blender, веса SAM, InstantMesh.

Затем создай задание (ссылка на товар Wildberries/Ozon или фото) и дождись
`done`. В real-режиме результат — настоящий 3D-меш одежды с физикой на теле.

---

## Шаг 5. Реалистичный манекен (позже)

Когда будешь готов: `BODY_ENGINE=mpfb` (тело MakeHuman, см. [MANNEQUIN.md](MANNEQUIN.md)).
Сначала проверь генерацию тела в Web Terminal:
```bash
blender --background --python \
  /opt/app/app/pipeline/blender_scripts/make_body.py -- \
  --height 185 --weight 90 --gender male --output /data/body.glb
```
Если ок — ставь `BODY_ENGINE=mpfb` и перезапускай. (Это тот движок, что мы
потом переделаем под лицензию.)

---

## Доступ к сайту (фронтенд)

Фронтенд в all-in-one не входит (чтобы образ был легче). Варианты:
- Пользуйся `/docs` — этого хватает для теста.
- Или запусти красивый фронт **локально** на маке, указав на Pod:
  ```bash
  cd frontend && npm install
  NEXT_PUBLIC_API_BASE_URL=https://<pod-id>-8000.proxy.runpod.net npm run dev
  ```
  → http://localhost:3000

---

## Деньги и гашение

- Платишь, пока Pod **Running**. Не нужен — жми **Stop** (volume с весами/БД
  сохранится, при следующем старте веса не качаются заново).
- 1 задание ≈ $0.10–0.20. RTX 4090 ≈ $0.34–0.69/час.

---

## Troubleshooting

| Симптом | Что делать |
|---------|-----------|
| RunPod не тянет образ | Сделай GHCR-пакет public (Шаг 1) или добавь registry-креды: RunPod → Settings → Container Registry Auth (username = GitHub-логин, token = PAT с `read:packages`) |
| `/docs` не открывается | Проверь, что Expose HTTP Port = 8000 и Pod = Running; смотри Logs |
| `failed`, ошибка InstantMesh | в Logs видно команду `run.py`; возможно, надо подправить аргументы под версию репозитория (напиши мне лог) |
| Долго «pending» | веса ещё качаются (real-режим) — жди, смотри Logs |
| Ссылки на файлы битые | проверь `PUBLIC_API_BASE_URL` = proxy-URL Pod |

---

## Чек-лист

- [ ] Код в GitHub, CI зелёный, образ `worker-runpod` в GHCR (public)
- [ ] Pod: RTX 4090, image = worker-runpod:latest, volume `/data` 60 ГБ, порт 8000
- [ ] Первый запуск `MOCK_PIPELINE=true` → `/docs` работает, задание `done`
- [ ] Переключил на `MOCK_PIPELINE=false` + `DRAPE_BACKEND=blender` + `PUBLIC_API_BASE_URL`
- [ ] `gpu_check.py` — всё ✅
- [ ] Прогнал реальный товар → `done` → 3D с физикой
- [ ] Не используешь — Stop (не жечь деньги)

> Реальный прогон real-режима я локально проверить не мог (нет GPU/Blender на
> маке). Деплой-обвязка готова; на первом запуске возможны 1–2 правки (чаще —
> аргументы InstantMesh). Скинь `Logs` — поправим.
