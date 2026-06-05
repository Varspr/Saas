"""Проверка готовности GPU-воркера ПОСЛЕ аренды сервера.

Запуск внутри контейнера воркера:
    docker compose -f docker-compose.yml -f docker-compose.gpu.yml \
        exec worker python /opt/app/scripts/gpu_check.py

Печатает ✅/❌ по каждому компоненту real-пайплайна.
"""
import os
import shutil
import subprocess
import sys

_ok = True


def check(name: str, cond: bool, detail: str = "") -> None:
    global _ok
    print(("✅" if cond else "❌"), name, ("— " + detail) if detail else "")
    _ok = _ok and cond


# GPU
has_smi = shutil.which("nvidia-smi") is not None
check("nvidia-smi", has_smi)
if has_smi:
    subprocess.run(
        ["nvidia-smi", "--query-gpu=name,memory.total,driver_version",
         "--format=csv,noheader"],
        check=False,
    )

# PyTorch + CUDA
try:
    import torch
    avail = torch.cuda.is_available()
    name = torch.cuda.get_device_name(0) if avail else ""
    check("torch.cuda", avail, name)
except Exception as e:  # noqa: BLE001
    check("import torch", False, str(e))

# Blender
blender = os.getenv("BLENDER_BIN", "blender")
check("Blender", bool(shutil.which(blender)) or os.path.exists(blender), blender)

# Веса SAM
sam = os.getenv("SAM_CHECKPOINT", "/models/sam_vit_h_4b8939.pth")
check("Веса SAM", os.path.exists(sam), sam)

# InstantMesh
im = os.getenv("INSTANTMESH_REPO", "/opt/InstantMesh")
check("InstantMesh", os.path.exists(os.path.join(im, "run.py")), im)

# Импорт SAM
try:
    import segment_anything  # noqa: F401
    check("import segment_anything", True)
except Exception as e:  # noqa: BLE001
    check("import segment_anything", False, str(e))

print()
if _ok:
    print("ГОТОВ к real-режиму. Создавайте задание через API/фронтенд.")
    sys.exit(0)
print("Есть проблемы — см. ❌ выше (часто: не докачались веса — подождите/перезапустите).")
sys.exit(1)
