"""Пайплайн обработки задания (Фазы 1-4).

Каждый модуль экспортирует одну функцию-вход и сам выбирает реализацию по
флагу settings.mock_pipeline:
    scraping.fetch_image        — получить фото (Playwright / прямое скачивание)
    segmentation.segment        — убрать фон (SAM / Pillow)
    reconstruction.reconstruct  — 2D→3D (InstantMesh / примитив)
    draping.drape               — надеть на тело (Blender / trimesh-сцена)
    rendering.render_previews   — 4 ракурса (Blender Cycles / Pillow)
"""
