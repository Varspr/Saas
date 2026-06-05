"""Фаза 2 — 3D-реконструкция одежды из 2D-фото.

reconstruct(clean_png, mesh_obj, texture_png) → пишет mesh (.obj) и текстуру (.png).

real (MOCK_PIPELINE=false): InstantMesh (TencentARC).
    clean_png → 6 синтезированных видов → меш + UV-текстура.
    Запуск через subprocess его run.py. ~60-120 c на A100.
    Хорошо для плоской одежды (футболки/куртки); обувь/аксессуары — v2.

mock: строим лёгкий «гарментоподобный» меш — изогнутую панель (плоскость с
    небольшим прогибом по Z), UV которой 0..1 совпадают с clean_png. Это даёт
    валидный текстурированный меш для последующей примерки на CPU.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import numpy as np
import trimesh
from PIL import Image

from app.config import settings


def reconstruct(clean_png: Path, mesh_obj: Path, texture_png: Path) -> tuple[Path, Path]:
    mesh_obj.parent.mkdir(parents=True, exist_ok=True)
    if settings.mock_pipeline:
        return _reconstruct_mock(clean_png, mesh_obj, texture_png)
    return _reconstruct_instantmesh(clean_png, mesh_obj, texture_png)


# ── mock: изогнутая панель с UV ─────────────────────────────────────────────

def _reconstruct_mock(clean_png: Path, mesh_obj: Path, texture_png: Path,
                      cols: int = 40, rows: int = 40) -> tuple[Path, Path]:
    img = Image.open(clean_png).convert("RGBA")
    img.save(texture_png, "PNG")

    aspect = img.height / img.width
    width = 0.6                       # ширина панели в метрах (~торс)
    height = width * aspect

    # Сетка вершин в плоскости XY с лёгким прогибом по Z (имитация объёма)
    xs = np.linspace(-width / 2, width / 2, cols)
    ys = np.linspace(height / 2, -height / 2, rows)
    verts, uvs = [], []
    for j, y in enumerate(ys):
        for i, x in enumerate(xs):
            u = i / (cols - 1)
            bend = 0.06 * np.sin(np.pi * u)  # выпуклость к зрителю
            verts.append([x, y, bend])
            uvs.append([u, 1 - j / (rows - 1)])
    verts = np.array(verts)
    uvs = np.array(uvs)

    faces = []
    for j in range(rows - 1):
        for i in range(cols - 1):
            a = j * cols + i
            b = a + 1
            c = a + cols
            d = c + 1
            faces.append([a, b, d])
            faces.append([a, d, c])
    faces = np.array(faces)

    material = trimesh.visual.material.PBRMaterial(baseColorTexture=img)
    visual = trimesh.visual.TextureVisuals(uv=uvs, material=material)
    mesh = trimesh.Trimesh(vertices=verts, faces=faces, visual=visual, process=False)

    # Экспорт в OBJ (+ .mtl + текстура рядом) — артефакт для дебага/контракта.
    mesh.export(mesh_obj)
    return mesh_obj, texture_png


# ── real: InstantMesh ───────────────────────────────────────────────────────

def _reconstruct_instantmesh(clean_png: Path, mesh_obj: Path,
                             texture_png: Path) -> tuple[Path, Path]:
    """Вызывает InstantMesh CLI и забирает .obj + текстуру из его outputs/.

    Команда (сверить с версией репозитория, см. MODELS.md):
        python run.py <config.yaml> <clean_png> \
            --output_path <out_dir> --export_texmap --no_rembg

    --no_rembg: фон уже убран SAM на Фазе 1, повторный rembg только испортит
    альфу. InstantMesh пишет результат в <out_dir>/<config_stem>/meshes/<name>.obj.
    """
    repo = Path(settings.instantmesh_repo)
    out_dir = mesh_obj.parent / "instantmesh_out"
    out_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        "python", str(repo / "run.py"),
        settings.instantmesh_config,
        str(clean_png),
        "--output_path", str(out_dir),
        "--export_texmap",
        "--no_rembg",
    ]
    subprocess.run(cmd, cwd=str(repo), check=True)

    produced_obj = _find_first(out_dir, "*.obj")
    if produced_obj is None:
        raise RuntimeError(f"InstantMesh не создал .obj в {out_dir}")
    shutil.copy(produced_obj, mesh_obj)

    produced_tex = (
        _find_first(out_dir, "*albedo*.png")
        or _find_first(out_dir, "*material*.png")
        or _find_first(out_dir, "*.png")
    )
    if produced_tex is not None:
        shutil.copy(produced_tex, texture_png)
    else:
        Image.open(clean_png).convert("RGBA").save(texture_png, "PNG")
    return mesh_obj, texture_png


def _find_first(root: Path, pattern: str) -> Path | None:
    files = sorted(root.rglob(pattern))
    return files[0] if files else None
