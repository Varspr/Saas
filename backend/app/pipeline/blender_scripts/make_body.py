"""Генерация реалистичного манекена через MakeHuman/MPFB2 внутри Blender.

MPFB2 (MakeHuman Plugin For Blender 2) — открытый аддон; создаваемые им меши
отдаются под CC0, т.е. коммерчески использовать можно. Здесь — функция
build_mpfb_body(), которой пользуется drape_cloth.py, плюс автономный режим
для проверки:

    blender --background --python make_body.py -- \
        --height 185 --weight 90 --gender male --output body.glb

⚠️ ВАЖНО про версии: точные имена API MPFB2 (HumanService, ключи macrodetail)
зависят от версии аддона. Код написан под актуальный MPFB2 и при несовпадении
кидает понятную ошибку — сверьте с https://static.makehumancommunity.org/mpfb/
docs/ (раздел scripting). Тело строится анатомически верно; «вес» меняет
комплекцию, «рост» — высоту.
"""
import argparse
import sys

import bpy


# ── маппинг рост/вес → нормированные макро-параметры MakeHuman (0..1) ──

def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def _height_macro(height_cm: float) -> float:
    # 150 см → 0.0, 175 → 0.5, 200 → 1.0
    return _clamp01((height_cm - 150.0) / 50.0)


def _weight_macro(height_cm: float, weight_kg: float) -> float:
    # через ИМТ: 17 → 0 (худой), 25 → 0.5 (средний), 33 → 1 (плотный)
    bmi = weight_kg / ((height_cm / 100.0) ** 2)
    return _clamp01((bmi - 17.0) / 16.0)


def _gender_macro(gender: str) -> float:
    return {"female": 0.0, "neutral": 0.5, "male": 1.0}.get(gender, 1.0)


def _macro_dict(height_cm, weight_kg, gender) -> dict:
    return {
        "gender": _gender_macro(gender),
        "age": 0.5,            # взрослый
        "muscle": 0.5,
        "weight": _weight_macro(height_cm, weight_kg),
        "height": _height_macro(height_cm),
        "proportions": 0.5,
        "african": 0.33, "asian": 0.33, "caucasian": 0.34,
    }


# ── создание тела ────────────────────────────────────────────────────────────

def _ensure_mpfb_enabled() -> None:
    try:
        import mpfb  # noqa: F401
        return
    except ImportError:
        pass
    try:
        bpy.ops.preferences.addon_enable(module="mpfb")
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(
            "MPFB2 не установлен/не включён в Blender. Установка — см. MANNEQUIN.md"
        ) from exc


def build_mpfb_body(height_cm: float, weight_kg: float,
                    gender: str = "male") -> "bpy.types.Object":
    """Создаёт MakeHuman-тело, красит в белый матовый и возвращает объект."""
    _ensure_mpfb_enabled()

    from mpfb.services.humanservice import HumanService

    macro = _macro_dict(height_cm, weight_kg, gender)

    # Основной путь: передать макро-словарь в create_human.
    try:
        basemesh = HumanService.create_human(
            mask_helpers=True,
            detailed_helpers=False,
            feet_on_ground=True,
            scale_factor=0.1,            # MakeHuman в дециметрах → метры
            macro_detail_dict=macro,
        )
    except TypeError:
        # Фолбэк для версий без macro_detail_dict: создать и догнать таргетами.
        basemesh = HumanService.create_human(feet_on_ground=True, scale_factor=0.1)
        _apply_macros_via_targets(basemesh, macro)

    _apply_white_material(basemesh)
    basemesh.name = "body"
    return basemesh


def _apply_macros_via_targets(basemesh, macro: dict) -> None:
    """Запасной способ задать макро-параметры (имена сверить с версией MPFB2)."""
    from mpfb.services.targetservice import TargetService
    name_map = {
        "gender": "macrodetail-universal-gender",
        "age": "macrodetail-universal-age",
        "muscle": "macrodetail-universal-muscle",
        "weight": "macrodetail-universal-weight",
        "height": "macrodetail-universal-height",
        "proportions": "macrodetail-universal-proportions",
    }
    for key, target in name_map.items():
        try:
            TargetService.set_target_value(basemesh, target, macro[key])
        except Exception:  # noqa: BLE001
            pass
    try:
        TargetService.reapply_macro_details(basemesh)
    except Exception:  # noqa: BLE001
        pass


def _apply_white_material(obj) -> None:
    """Матовый бело-серый материал «как у витринного манекена»."""
    mat = bpy.data.materials.new("Mannequin")
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = (0.92, 0.92, 0.93, 1.0)
        if "Roughness" in bsdf.inputs:
            bsdf.inputs["Roughness"].default_value = 0.45
        # лёгкий «пластиковый» блик
        for spec in ("Specular", "Specular IOR Level"):
            if spec in bsdf.inputs:
                bsdf.inputs[spec].default_value = 0.4
    obj.data.materials.clear()
    obj.data.materials.append(mat)


# ── автономный режим (проверка) ──────────────────────────────────────────────

def _parse_args():
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--height", type=float, default=175)
    p.add_argument("--weight", type=float, default=70)
    p.add_argument("--gender", default="male")
    p.add_argument("--output", required=True)
    return p.parse_args(argv)


def main():
    args = _parse_args()
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()
    build_mpfb_body(args.height, args.weight, args.gender)
    bpy.ops.export_scene.gltf(filepath=args.output, export_format="GLB")
    print(f"[make_body] exported {args.output}")


if __name__ == "__main__":
    main()
