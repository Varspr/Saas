# Подключение реальных моделей (real-режим)

В dev всё работает на заглушках (`MOCK_PIPELINE=true`). Ниже — что нужно,
чтобы перевести пайплайн на настоящие модели (`MOCK_PIPELINE=false`) на
GPU-воркере (A100, RunPod/Modal/Lambda).

## 0. Общее

```bash
MOCK_PIPELINE=false
pip install -r requirements-gpu.txt   # раскомментировать torch под вашу CUDA
```

GPU-образ собирается из `Dockerfile.worker` (см. закомментированный
REAL/GPU-блок в его конце). Итоговый образ ~15 GB со всеми весами внутри
(или веса монтируются volume'ом, чтобы не раздувать образ).

## 1. Сегментация — SAM (Фаза 1)

```bash
pip install git+https://github.com/facebookresearch/segment-anything.git
# веса ViT-H (~2.4 GB)
wget https://dl.fbaipublicfiles.com/segment_anything/sam_vit_h_4b8939.pth \
  -O /models/sam_vit_h_4b8939.pth
```
```bash
SAM_CHECKPOINT=/models/sam_vit_h_4b8939.pth
SAM_MODEL_TYPE=vit_h
```
Код: `app/pipeline/segmentation.py::_segment_sam`.

## 2. 3D-реконструкция — InstantMesh (Фаза 2)

```bash
git clone https://github.com/TencentARC/InstantMesh /opt/InstantMesh
cd /opt/InstantMesh && pip install -r requirements.txt
# веса подтянутся с HuggingFace при первом запуске (или скачать заранее)
```
```bash
INSTANTMESH_REPO=/opt/InstantMesh
INSTANTMESH_CONFIG=/opt/InstantMesh/configs/instant-mesh-large.yaml
```
Код: `app/pipeline/reconstruction.py::_reconstruct_instantmesh`.
**Сверьте CLI** `run.py` с вашей версией репозитория и при необходимости
поправьте аргументы (`--output_path`, `--export_texmap`).

## 3. Тело — SMPL-X (Фаза 3)

Положите нейтральный меш тела в T-pose (размер M) как:
```
/assets/body_tpose.obj      # BODY_MESH_PATH
```
Источник: SMPL-X (https://smpl-x.is.tue.mpg.de/) — требуется регистрация и
согласие с лицензией. Экспортируйте T-pose в .obj.
Если файла нет — `app/pipeline/body.py` сгенерирует примитивный манекен.

## 4. Blender (Фазы 3-4)

```bash
apt-get install -y blender         # или скачать с blender.org
BLENDER_BIN=blender
```
Скрипты уже в репозитории:
- `app/pipeline/blender_scripts/drape_cloth.py` — cloth simulation;
- `app/pipeline/blender_scripts/render_preview.py` — 4 ракурса (Cycles).

Проверка вручную:
```bash
blender --background --python app/pipeline/blender_scripts/drape_cloth.py -- \
  --body /assets/body_tpose.obj --clothing mesh.obj \
  --texture tex.png --output out.glb
```

## Чек-лист перехода

- [ ] `MOCK_PIPELINE=false`
- [ ] GPU доступен в контейнере (`nvidia-smi` внутри воркера)
- [ ] Веса SAM на месте
- [ ] InstantMesh клонирован, его `run.py` запускается
- [ ] `body_tpose.obj` в `/assets`
- [ ] `blender` в PATH
- [ ] Прогнать 1 задание и проверить `output.glb` + 4 PNG
