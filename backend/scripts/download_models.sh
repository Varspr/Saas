#!/usr/bin/env bash
# Скачивание весов в $MODELS_DIR (идемпотентно — пропускает уже скачанное).
# Вызывается из entrypoint.sh при MOCK_PIPELINE != true.
set -euo pipefail

MODELS_DIR="${MODELS_DIR:-/models}"
SAM_CKPT="${SAM_CHECKPOINT:-$MODELS_DIR/sam_vit_h_4b8939.pth}"
PREWARM_INSTANTMESH="${PREWARM_INSTANTMESH:-false}"

mkdir -p "$MODELS_DIR" "${HF_HOME:-$MODELS_DIR/hf}"

# ── SAM ViT-H (~2.4 ГБ) ──
if [ ! -f "$SAM_CKPT" ]; then
  echo "[models] качаю SAM ViT-H -> $SAM_CKPT"
  wget -q --show-progress \
    https://dl.fbaipublicfiles.com/segment_anything/sam_vit_h_4b8939.pth \
    -O "$SAM_CKPT.part"
  mv "$SAM_CKPT.part" "$SAM_CKPT"
else
  echo "[models] SAM уже на месте: $SAM_CKPT"
fi

# ── InstantMesh + zero123plus ──
# По умолчанию веса тянутся автоматически из HuggingFace при первом инференсе
# (кэшируются в HF_HOME). Чтобы прогреть заранее (дольше старт, но первый job
# не ждёт скачивания) — PREWARM_INSTANTMESH=true.
if [ "$PREWARM_INSTANTMESH" = "true" ]; then
  echo "[models] прогрев весов InstantMesh/zero123plus в $HF_HOME ..."
  python - <<'PY'
from huggingface_hub import snapshot_download
for repo in ("TencentARC/InstantMesh", "sudo-ai/zero123plus-v1.2"):
    print(f"  snapshot_download({repo})")
    snapshot_download(repo)
PY
fi

echo "[models] готово."
