"""Blender headless: рендер 4 превью результата (Фаза 4).

Запуск (вызывается из rendering._previews_blender):
    blender --background --python render_preview.py -- \
        --input output.glb --out_dir preview/

Рендерит Cycles с 4 ракурсов: front / side / back / three_quarter → 4 PNG 1024².
"""
import argparse
import math
import sys

import bpy
from mathutils import Vector

VIEWS = {
    "front": 0,
    "side": 90,
    "back": 180,
    "three_quarter": 45,
}


def parse_args():
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True)
    p.add_argument("--out_dir", required=True)
    p.add_argument("--samples", type=int, default=64)
    p.add_argument("--res", type=int, default=1024)
    return p.parse_args(argv)


def clear_scene():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()


def scene_bounds():
    """Центр и радиус всей геометрии — чтобы навести камеру."""
    coords = []
    for obj in bpy.data.objects:
        if obj.type == "MESH":
            coords += [obj.matrix_world @ Vector(c) for c in obj.bound_box]
    if not coords:
        return Vector((0, 0, 0)), 1.0
    minv = Vector((min(c[i] for c in coords) for i in range(3)))
    maxv = Vector((max(c[i] for c in coords) for i in range(3)))
    center = (minv + maxv) / 2
    radius = (maxv - minv).length / 2
    return center, max(radius, 0.5)


def setup_lighting():
    bpy.ops.object.light_add(type="AREA", location=(2, -2, 3))
    bpy.context.object.data.energy = 800
    bpy.ops.object.light_add(type="AREA", location=(-2, -1, 2))
    bpy.context.object.data.energy = 400


def place_camera(angle_deg, center, radius):
    cam_data = bpy.data.cameras.new("Cam")
    cam = bpy.data.objects.new("Cam", cam_data)
    bpy.context.collection.objects.link(cam)

    dist = radius * 3.0
    a = math.radians(angle_deg)
    cam.location = center + Vector((math.sin(a) * dist, -math.cos(a) * dist, radius * 0.3))

    # направить на центр
    direction = center - cam.location
    cam.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    bpy.context.scene.camera = cam
    return cam


def main():
    args = parse_args()
    clear_scene()

    bpy.ops.import_scene.gltf(filepath=args.input)

    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.samples = args.samples
    scene.render.resolution_x = args.res
    scene.render.resolution_y = args.res
    scene.render.film_transparent = True
    scene.render.image_settings.file_format = "PNG"

    setup_lighting()
    center, radius = scene_bounds()

    for name, angle in VIEWS.items():
        cam = place_camera(angle, center, radius)
        scene.render.filepath = f"{args.out_dir.rstrip('/')}/{name}.png"
        bpy.ops.render.render(write_still=True)
        bpy.data.objects.remove(cam, do_unlink=True)
        print(f"[render_preview] {name}.png done")


if __name__ == "__main__":
    main()
