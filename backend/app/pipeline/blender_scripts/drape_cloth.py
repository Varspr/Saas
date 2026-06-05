"""Blender headless: надевание одежды на тело через cloth simulation (Фаза 3).

Запуск (вызывается из draping._drape_blender_scene):
    blender --background --python drape_cloth.py -- \
        --body-engine mpfb --height 185 --weight 90 --gender male \
        --clothing clothing_mesh.obj --texture clothing_texture.png \
        --output output.glb

  --body-engine mpfb   → тело генерит MakeHuman/MPFB2 (реалистичный манекен);
  --body-engine import → тело берётся из --body <obj> (параметрический trimesh).

Это «Вариант B» из плана: физика ткани даёт естественную посадку. Совместимо
с Blender 3.x/4.x (импорт OBJ менялся).
"""
import argparse
import os
import sys

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # для make_body


def parse_args():
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--body-engine", dest="body_engine", default="import",
                   choices=["import", "mpfb"])
    p.add_argument("--body", default=None)         # для body-engine=import
    p.add_argument("--height", type=float, default=175)
    p.add_argument("--weight", type=float, default=70)
    p.add_argument("--gender", default="male")
    p.add_argument("--clothing", required=True)
    p.add_argument("--texture", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--frames", type=int, default=30)
    return p.parse_args(argv)


def clear_scene():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()


def import_obj(filepath):
    """Импорт OBJ с учётом разных версий Blender, возвращает импортированный объект."""
    before = set(bpy.data.objects)
    if hasattr(bpy.ops.wm, "obj_import"):          # Blender 4.x
        bpy.ops.wm.obj_import(filepath=filepath)
    else:                                            # Blender 3.x
        bpy.ops.import_scene.obj(filepath=filepath)
    new = list(set(bpy.data.objects) - before)
    return new[0] if new else None


def make_textured_material(texture_path):
    mat = bpy.data.materials.new("ClothingMat")
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    tex = mat.node_tree.nodes.new("ShaderNodeTexImage")
    tex.image = bpy.data.images.load(texture_path)
    mat.node_tree.links.new(bsdf.inputs["Base Color"], tex.outputs["Color"])
    return mat


def make_body(args):
    """Тело: либо реалистичный MakeHuman (mpfb), либо импорт OBJ."""
    if args.body_engine == "mpfb":
        from make_body import build_mpfb_body
        return build_mpfb_body(args.height, args.weight, args.gender)
    body = import_obj(args.body)
    body.name = "body"
    return body


def main():
    args = parse_args()
    clear_scene()

    body = make_body(args)

    cloth = import_obj(args.clothing)
    cloth.name = "clothing"

    # Текстура одежды
    mat = make_textured_material(args.texture)
    cloth.data.materials.clear()
    cloth.data.materials.append(mat)

    # Cloth physics на одежде
    bpy.context.view_layer.objects.active = cloth
    bpy.ops.object.modifier_add(type="CLOTH")
    cloth.modifiers["Cloth"].settings.quality = 10
    cloth.modifiers["Cloth"].settings.mass = 0.3
    cloth.modifiers["Cloth"].collision_settings.distance_min = 0.005

    # Collision на теле
    bpy.context.view_layer.objects.active = body
    bpy.ops.object.modifier_add(type="COLLISION")

    # Симуляция
    scene = bpy.context.scene
    scene.frame_start = 1
    scene.frame_end = args.frames
    bpy.ops.ptcache.bake_all(bake=True)
    scene.frame_set(args.frames)

    # Экспорт glTF (.glb)
    bpy.ops.export_scene.gltf(
        filepath=args.output,
        export_format="GLB",
        use_selection=False,
    )
    print(f"[drape_cloth] exported {args.output}")


if __name__ == "__main__":
    main()
