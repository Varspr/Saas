"""Фаза 4 — превью-рендеры результата.

render_previews(output_glb, clean_png, out_dir) → список из 4 PNG
(front / side / back / three_quarter), 1024×1024.

real (MOCK_PIPELINE=false): Blender Cycles рендерит output.glb с 4 камер
    (blender_scripts/render_preview.py).

mock: без GL — компонуем превью на Pillow из чистого фото одежды (clean_png)
    на нейтральном фоне с подписью ракурса. Этого достаточно, чтобы фронтенд
    показал галерею, пока не подключён GPU-рендер.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from app.config import settings

VIEWS = ["front", "side", "back", "three_quarter"]
_BLENDER_SCRIPT = Path(__file__).parent / "blender_scripts" / "render_preview.py"


def render_previews(output_glb: Path, clean_png: Path, out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    if settings.mock_pipeline:
        return _previews_mock(clean_png, out_dir)
    return _previews_blender(output_glb, out_dir)


# ── mock ────────────────────────────────────────────────────────────────────

def _previews_mock(clean_png: Path, out_dir: Path, size: int = 1024) -> list[Path]:
    garment = Image.open(clean_png).convert("RGBA")
    paths: list[Path] = []
    for idx, view in enumerate(VIEWS):
        canvas = _gradient_bg(size, tint=idx)
        g = garment.copy()
        g.thumbnail((int(size * 0.7), int(size * 0.7)), Image.LANCZOS)
        # «спина» — отражаем по горизонтали как грубый намёк
        if view == "back":
            g = g.transpose(Image.FLIP_LEFT_RIGHT)
        canvas.alpha_composite(g, ((size - g.width) // 2, (size - g.height) // 2))
        _label(canvas, view.replace("_", " ").upper(), size)
        path = out_dir / f"{view}.png"
        canvas.convert("RGB").save(path, "PNG")
        paths.append(path)
    return paths


def _gradient_bg(size: int, tint: int) -> Image.Image:
    base = [(238, 240, 244), (244, 240, 238), (240, 244, 238), (240, 238, 244)][tint % 4]
    top = tuple(min(255, c + 8) for c in base)
    img = Image.new("RGBA", (size, size))
    px = img.load()
    for y in range(size):
        t = y / size
        row = tuple(int(top[i] * (1 - t) + base[i] * t) for i in range(3)) + (255,)
        for x in range(size):
            px[x, y] = row
    return img


def _label(img: Image.Image, text: str, size: int) -> None:
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("DejaVuSans-Bold.ttf", 34)
    except Exception:
        font = ImageFont.load_default()
    draw.text((30, size - 64), text, fill=(90, 90, 96, 255), font=font)
    draw.text((30, 28), "preview (mock)", fill=(150, 150, 156, 255), font=font)


# ── real ────────────────────────────────────────────────────────────────────

def _previews_blender(output_glb: Path, out_dir: Path) -> list[Path]:
    cmd = [
        settings.blender_bin, "--background", "--python", str(_BLENDER_SCRIPT), "--",
        "--input", str(output_glb),
        "--out_dir", str(out_dir),
    ]
    subprocess.run(cmd, check=True)
    paths = [out_dir / f"{v}.png" for v in VIEWS]
    missing = [p for p in paths if not p.exists()]
    if missing:
        raise RuntimeError(f"Blender не отрендерил превью: {missing}")
    return paths
