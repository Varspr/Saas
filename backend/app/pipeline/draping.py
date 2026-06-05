"""Фаза 3 — надеть одежду на 3D-модель тела.

drape(mesh_obj, texture_png, output_glb, height_cm, weight_kg) → output.glb.

Тело строится от роста/веса (pipeline.body). Одежда:
  • mock-AI: облегающая текстурированная оболочка по сечениям торса —
    садится ровно на это же тело (без реконструкции из фото).
  • real-AI: меш одежды из InstantMesh, подогнанный к торсу.

Способ «надевания» (settings.drape_backend):
  • mock    — статичная посадка (без симуляции), быстро, на CPU.
  • blender — настоящая cloth simulation (физика ткани). Считается на CPU,
              GPU не нужен — нужен лишь установленный Blender.
  • auto    — blender, если он найден в системе, иначе mock.
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import trimesh
from PIL import Image

from app.config import settings
from app.pipeline import body as body_mod

_BLENDER_SCRIPT = Path(__file__).parent / "blender_scripts" / "drape_cloth.py"


def drape(mesh_obj: Path, texture_png: Path, output_glb: Path,
          height_cm: float | None = None, weight_kg: float | None = None) -> Path:
    output_glb.parent.mkdir(parents=True, exist_ok=True)
    height_cm = height_cm or settings.default_height_cm
    weight_kg = weight_kg or settings.default_weight_kg

    gender = settings.body_gender

    # Одежда
    if settings.mock_pipeline:
        fabric = _fabric_texture(texture_png)
        garment = _garment_shell(fabric, height_cm, weight_kg)
        garment_tex = fabric
    else:
        garment = _fit_real_garment(trimesh.load(mesh_obj, force="mesh"),
                                    height_cm, weight_kg)
        garment_tex = Image.open(texture_png).convert("RGBA")

    if _use_blender():
        # При body_engine=mpfb тело генерит сам Blender (реалистичный манекен),
        # trimesh-тело не нужно. Иначе экспортируем параметрическое тело в OBJ.
        body_mesh = None if settings.body_engine == "mpfb" \
            else body_mod.load_body_mesh(height_cm, weight_kg)
        return _drape_blender_scene(garment, garment_tex, output_glb,
                                    height_cm, weight_kg, gender, body_mesh)

    # Без Blender — статичная сборка с параметрическим телом
    body_mesh = body_mod.load_body_mesh(height_cm, weight_kg)
    return _export_scene(body_mesh, garment, output_glb)


# ── выбор бэкенда ───────────────────────────────────────────────────────────

def _use_blender() -> bool:
    if settings.body_engine == "mpfb":
        return True  # реалистичный манекен MakeHuman требует Blender
    mode = settings.drape_backend
    if mode == "mock":
        return False
    if mode == "blender":
        return True
    # auto
    if not settings.mock_pipeline:
        return True
    return shutil.which(settings.blender_bin) is not None


# ── одежда (mock): облегающая оболочка ──────────────────────────────────────

def _garment_shell(fabric_img: Image.Image, height_cm, weight_kg,
                   sections: int = 48) -> trimesh.Trimesh:
    """Тонкая текстурированная оболочка по сечениям торса (майка/футболка)."""
    rings = body_mod.garment_torso_rings(height_cm, weight_kg)  # top→bottom
    R = len(rings)
    ang = np.linspace(0, 2 * np.pi, sections, endpoint=False)

    verts, uvs = [], []
    for i, (y, rx, rz) in enumerate(rings):
        v = 1.0 - i / (R - 1)                      # верх=1 (плечи), низ=0
        for a in ang:
            verts.append([rx * np.cos(a), y, rz * np.sin(a)])
            # перёд (+Z, a=π/2) → центр текстуры; бока/спина → к краям
            phi = ((a - np.pi / 2 + np.pi) % (2 * np.pi)) - np.pi
            u = min(1.0, max(0.0, 0.5 + 0.5 * (phi / np.pi)))
            uvs.append([u, v])

    faces = []
    for i in range(R - 1):
        base, nxt = i * sections, (i + 1) * sections
        for j in range(sections):
            j2 = (j + 1) % sections
            faces.append([base + j, base + j2, nxt + j2])
            faces.append([base + j, nxt + j2, nxt + j])

    material = trimesh.visual.material.PBRMaterial(
        baseColorTexture=fabric_img, metallicFactor=0.0, roughnessFactor=0.85,
    )
    visual = trimesh.visual.TextureVisuals(uv=np.array(uvs), material=material)
    return trimesh.Trimesh(vertices=np.array(verts), faces=np.array(faces),
                           visual=visual, process=False)


def _fabric_texture(texture_png: Path) -> Image.Image:
    """Заливает прозрачный фон средним цветом одежды → сплошная «ткань»."""
    arr = np.asarray(Image.open(texture_png).convert("RGBA"))
    rgb = arr[..., :3].astype(float)
    mask = arr[..., 3] > 16
    mean = rgb[mask].mean(axis=0) if mask.any() else np.array([180, 180, 188.0])
    out = rgb.copy()
    out[~mask] = mean
    return Image.fromarray(out.astype(np.uint8), "RGB")


# ── одежда (real): подгонка меша InstantMesh к торсу ────────────────────────

def _fit_real_garment(mesh: trimesh.Trimesh, height_cm, weight_kg) -> trimesh.Trimesh:
    """InstantMesh выдаёт меш в ~единичном кубе — масштабируем на торс."""
    rings = body_mod.garment_torso_rings(height_cm, weight_kg)
    top_y, bottom_y = rings[0][0], rings[-1][0]
    target_h = top_y - bottom_y
    target_w = 2 * max(r[1] for r in rings) * 1.05

    ext = mesh.extents
    if ext[1] > 1e-6:
        mesh.apply_scale(target_h / ext[1])
    ext = mesh.extents
    if ext[0] > 1e-6 and ext[0] > target_w:
        mesh.apply_scale(target_w / ext[0])
    # центрируем на торс
    mesh.apply_translation(-mesh.centroid)
    mesh.apply_translation([0, (top_y + bottom_y) / 2, 0.02])
    return mesh


# ── сборка / экспорт ────────────────────────────────────────────────────────

def _export_scene(body_mesh: trimesh.Trimesh, garment: trimesh.Trimesh,
                  output_glb: Path) -> Path:
    scene = trimesh.Scene()
    scene.add_geometry(body_mesh, geom_name="body")
    scene.add_geometry(garment, geom_name="clothing")
    scene.export(output_glb)
    return output_glb


def _drape_blender_scene(garment, garment_tex, output_glb,
                         height_cm, weight_kg, gender, body_mesh=None) -> Path:
    """Реальная физика: тело (MPFB или OBJ) + cloth simulation одежды."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        cloth_obj = tmp / "clothing.obj"
        tex_png = tmp / "texture.png"
        garment.export(cloth_obj)
        garment_tex.convert("RGBA").save(tex_png)

        cmd = [
            settings.blender_bin, "--background", "--python", str(_BLENDER_SCRIPT),
            "--",
            "--clothing", str(cloth_obj),
            "--texture", str(tex_png),
            "--output", str(output_glb),
            "--height", str(int(height_cm)),
            "--weight", str(int(weight_kg)),
            "--gender", gender,
        ]
        if settings.body_engine == "mpfb":
            cmd += ["--body-engine", "mpfb"]
        else:
            body_obj = tmp / "body.obj"
            body_mesh.export(body_obj)
            cmd += ["--body-engine", "import", "--body", str(body_obj)]

        subprocess.run(cmd, check=True)
    if not output_glb.exists():
        raise RuntimeError("Blender не создал output.glb")
    return output_glb
