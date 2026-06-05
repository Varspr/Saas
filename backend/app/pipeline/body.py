"""Тело-носитель для примерки (Фаза 3) — параметрическое от роста и веса.

Раньше тут был грубый манекен из несвязанных примитивов. Теперь:

  • build_parametric_body(height_cm, weight_kg) — связное человекоподобное
    тело, собранное лофтингом эллиптических сечений вдоль роста. Обхваты
    масштабируются от ИМТ (вес/рост²), общий рост — от height_cm. Это работает
    на CPU и не требует лицензий.

  • load_body_mesh(...) — точка входа: реальный SMPL-X (если подключён и
    доступен), иначе параметрическое тело. SMPL-X даёт анатомически точную
    форму; betas подбираются под рост/вес (см. _smplx_body, scaffold).

Сечения торса доступны отдельно (garment_torso_rings) — по ним draping строит
облегающую одежду, чтобы она точно села на это же тело.
"""
from __future__ import annotations

import numpy as np
import trimesh

from app.config import settings

REF_HEIGHT = 1.75   # рост эталона, м
REF_BMI = 22.0      # ИМТ эталона


def _dims(height_cm: float | None, weight_kg: float | None):
    """Возвращает (рост_м, girth, skel_scale) из роста и веса."""
    H = max(1.30, min(2.20, (height_cm or 175) / 100.0))
    bmi = (weight_kg or 70) / (H * H)
    # обхваты ∝ √(вес/рост); girth=1 при эталонном ИМТ
    girth = max(0.72, min(1.7, (bmi / REF_BMI) ** 0.5))
    skel = H / REF_HEIGHT
    return H, girth, skel


# ── публичный API ───────────────────────────────────────────────────────────

def load_body_mesh(height_cm: float | None = 175,
                   weight_kg: float | None = 70) -> trimesh.Trimesh:
    if not settings.mock_pipeline and settings.use_smplx:
        try:
            return _smplx_body(height_cm, weight_kg)
        except Exception:
            pass  # нет весов/пакета — падаем на параметрическое
    return build_parametric_body(height_cm, weight_kg)


def garment_torso_rings(height_cm: float | None, weight_kg: float | None,
                        offset: float = 0.02):
    """Сечения для облегающей одежды: от плеч до бёдер, чуть шире тела."""
    H, g, s = _dims(height_cm, weight_kg)
    # (доля_роста, rx, rz) — низ майки на бёдрах, верх у плеч
    spec = [
        (0.805, 0.185, 0.110),
        (0.760, 0.165, 0.110),
        (0.700, 0.150, 0.108),
        (0.640, 0.140, 0.103),
        (0.585, 0.140, 0.105),
        (0.540, 0.158, 0.112),
        (0.510, 0.168, 0.116),
    ]
    return [(f * H, rx * s * g + offset, rz * s * g + offset) for f, rx, rz in spec]


# ── параметрическое тело ────────────────────────────────────────────────────

def build_parametric_body(height_cm: float | None = 175,
                          weight_kg: float | None = 70) -> trimesh.Trimesh:
    H, g, s = _dims(height_cm, weight_kg)

    def sc(r):  # масштаб радиуса: скелет × мягкие ткани
        return r * s * g

    parts: list[trimesh.Trimesh] = []

    # Торс (плечи → талия → бёдра), эллиптические сечения
    torso = [
        (0.82, 0.195, 0.110),
        (0.78, 0.175, 0.110),
        (0.72, 0.150, 0.108),
        (0.66, 0.138, 0.103),
        (0.62, 0.132, 0.100),
        (0.57, 0.150, 0.110),
        (0.52, 0.170, 0.118),
    ]
    parts.append(_tube([(f * H, sc(rx), sc(rz)) for f, rx, rz in torso]))

    # Шея
    parts.append(_tube([(0.80 * H, sc(0.058), sc(0.050)),
                        (0.875 * H, sc(0.052), sc(0.046))]))

    # Голова (эллипсоид; почти не толстеет от веса → g^0.25)
    gh = g ** 0.25
    head = trimesh.creation.icosphere(subdivisions=3, radius=1.0)
    head.apply_scale([0.092 * s * gh, 0.118 * s * gh, 0.104 * s * gh])
    head.apply_translation([0, 0.935 * H, 0.012 * s])
    parts.append(head)

    # Ноги
    leg_rings = [
        (0.520, 0.105), (0.440, 0.092), (0.330, 0.066),
        (0.300, 0.060), (0.190, 0.062), (0.060, 0.040),
    ]
    leg_x = 0.085 * s
    for side in (+1, -1):
        leg = _tube([(f * H, sc(r), sc(r)) for f, r in leg_rings])
        leg.apply_translation([side * leg_x, 0, 0])
        parts.append(leg)
        # стопа
        foot = trimesh.creation.icosphere(subdivisions=2, radius=1.0)
        foot.apply_scale([0.040 * s, 0.028 * s, 0.105 * s])
        foot.apply_translation([side * leg_x, 0.028 * H, 0.045 * s])
        parts.append(foot)

    # Руки (T-pose): строим вдоль +Y, поворачиваем в ±X
    arm_len = 0.40 * H
    arm_rings = [
        (0.00, 0.058), (0.12, 0.052), (0.50, 0.045),
        (0.88, 0.036), (1.00, 0.030),
    ]
    shoulder_y = 0.805 * H
    shoulder_x = sc(0.190) - 0.015
    for side in (+1, -1):
        arm = _tube([(t * arm_len, sc(r), sc(r)) for t, r in arm_rings])
        rot = trimesh.transformations.rotation_matrix(side * -np.pi / 2, [0, 0, 1])
        arm.apply_transform(rot)
        arm.apply_translation([side * shoulder_x, shoulder_y, 0])
        parts.append(arm)

    body = trimesh.util.concatenate(parts)
    body.merge_vertices()
    # fix_normals() намеренно не зовём: он тянет scipy, а единственные возможно
    # инвертированные грани — это торцы (заглушки) внутри тела, их не видно.
    body.visual.vertex_colors = [205, 200, 196, 255]  # нейтральный манекен
    return body


def _tube(rings: list[tuple[float, float, float]], sections: int = 32,
          cap: bool = True) -> trimesh.Trimesh:
    """Лофт эллиптических колец вдоль Y. rings: (y, rx, rz)."""
    ang = np.linspace(0, 2 * np.pi, sections, endpoint=False)
    cos, sin = np.cos(ang), np.sin(ang)

    V: list[list[float]] = []
    for (y, rx, rz) in rings:
        for j in range(sections):
            V.append([rx * cos[j], y, rz * sin[j]])

    F: list[list[int]] = []
    R = len(rings)
    for i in range(R - 1):
        base, nxt = i * sections, (i + 1) * sections
        for j in range(sections):
            j2 = (j + 1) % sections
            a, b = base + j, base + j2
            c, d = nxt + j, nxt + j2
            F.append([a, b, d])
            F.append([a, d, c])

    if cap:
        y0 = rings[0][0]
        cb = len(V); V.append([0.0, y0, 0.0])
        for j in range(sections):
            F.append([cb, (j + 1) % sections, j])
        yt = rings[-1][0]
        ct = len(V); V.append([0.0, yt, 0.0])
        tb = (R - 1) * sections
        for j in range(sections):
            F.append([ct, tb + j, tb + (j + 1) % sections])

    return trimesh.Trimesh(vertices=np.array(V), faces=np.array(F), process=True)


# ── реальный SMPL-X (scaffold) ──────────────────────────────────────────────

def _smplx_body(height_cm: float | None, weight_kg: float | None) -> trimesh.Trimesh:
    """Анатомический меш через пакет smplx (нужны лицензионные веса).

    betas (форма тела) подбираются под рост/вес простым градиентным фитом:
    минимизируем |рост(betas)-target| и |объём(betas)·ρ - вес|. Здесь —
    каркас; подключение весов и фит см. backend/MODELS.md.
    """
    import torch  # noqa: F401
    import smplx  # noqa: F401
    raise NotImplementedError(
        "SMPL-X не сконфигурирован: укажите SMPLX_MODEL_PATH и веса (MODELS.md)."
    )
