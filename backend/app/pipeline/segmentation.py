"""Фаза 1б — сегментация одежды (убрать фон).

segment(src_png, dest_png) → dest_png это RGBA 1024×1024, одежда без фона.

real (MOCK_PIPELINE=false): Segment Anything Model (SAM) от Meta.
    PIL → SAM AutomaticMaskGenerator → берём самую крупную центральную маску
    → вырезаем по альфе. Модель грузится один раз и кэшируется в процессе.

mock (по умолчанию): быстрый chroma-key на Pillow/numpy — считаем фон по
    цвету углов и делаем его прозрачным. Качество хуже SAM, но позволяет
    гонять весь пайплайн на CPU.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from app.config import settings

_sam_generator = None  # кэш реальной модели


def segment(src_png: Path, dest_png: Path) -> Path:
    dest_png.parent.mkdir(parents=True, exist_ok=True)
    if settings.mock_pipeline:
        return _segment_mock(src_png, dest_png)
    return _segment_sam(src_png, dest_png)


# ── mock: chroma-key по углам ───────────────────────────────────────────────

def _segment_mock(src_png: Path, dest_png: Path, tol: int = 28) -> Path:
    img = Image.open(src_png).convert("RGB")
    arr = np.asarray(img).astype(np.int16)
    h, w = arr.shape[:2]

    # Цвет фона = медиана по четырём углам
    corners = np.concatenate([
        arr[:10, :10].reshape(-1, 3),
        arr[:10, -10:].reshape(-1, 3),
        arr[-10:, :10].reshape(-1, 3),
        arr[-10:, -10:].reshape(-1, 3),
    ])
    bg = np.median(corners, axis=0)

    dist = np.sqrt(((arr - bg) ** 2).sum(axis=2))
    alpha = np.where(dist < tol, 0, 255).astype(np.uint8)

    # Лёгкое сглаживание краёв
    rgba = np.dstack([arr.astype(np.uint8), alpha])
    out = Image.fromarray(rgba, "RGBA")
    out = _crop_to_alpha(out)
    out = _fit_square(out, 1024)
    out.save(dest_png, "PNG")
    return dest_png


# ── real: SAM ───────────────────────────────────────────────────────────────

def _get_sam_generator():
    global _sam_generator
    if _sam_generator is not None:
        return _sam_generator

    import torch
    from segment_anything import SamAutomaticMaskGenerator, sam_model_registry

    device = "cuda" if torch.cuda.is_available() else "cpu"
    sam = sam_model_registry[settings.sam_model_type](checkpoint=settings.sam_checkpoint)
    sam.to(device)
    _sam_generator = SamAutomaticMaskGenerator(
        sam, points_per_side=32, pred_iou_thresh=0.88, stability_score_thresh=0.92
    )
    return _sam_generator


def _segment_sam(src_png: Path, dest_png: Path) -> Path:
    img = Image.open(src_png).convert("RGB")
    arr = np.asarray(img)

    masks = _get_sam_generator().generate(arr)
    if not masks:
        # Фолбэк, чтобы задание не падало целиком
        return _segment_mock(src_png, dest_png)

    # Берём самую крупную маску, центр которой ближе к центру кадра
    h, w = arr.shape[:2]
    cx, cy = w / 2, h / 2

    def score(m):
        ys, xs = np.where(m["segmentation"])
        if len(xs) == 0:
            return -1
        mcx, mcy = xs.mean(), ys.mean()
        center_pen = ((mcx - cx) ** 2 + (mcy - cy) ** 2) ** 0.5 / (w + h)
        return m["area"] * (1 - center_pen)

    best = max(masks, key=score)["segmentation"]
    alpha = (best.astype(np.uint8)) * 255
    rgba = np.dstack([arr, alpha])
    out = Image.fromarray(rgba, "RGBA")
    out = _crop_to_alpha(out)
    out = _fit_square(out, 1024)
    out.save(dest_png, "PNG")
    return dest_png


# ── общие пост-обработки ────────────────────────────────────────────────────

def _crop_to_alpha(img: Image.Image) -> Image.Image:
    bbox = img.getchannel("A").getbbox()
    return img.crop(bbox) if bbox else img


def _fit_square(img: Image.Image, size: int, pad: float = 0.92) -> Image.Image:
    scale = (size * pad) / max(img.width, img.height)
    new = img.resize((max(1, int(img.width * scale)), max(1, int(img.height * scale))), Image.LANCZOS)
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    canvas.paste(new, ((size - new.width) // 2, (size - new.height) // 2), new)
    return canvas
