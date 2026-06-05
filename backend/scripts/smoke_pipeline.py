"""Смоук-тест mock-пайплайна без Redis/Postgres/FastAPI.

Гоняет сегментацию → реконструкцию → примерку → рендер на сгенерированной
картинке и проверяет, что получились валидные output.glb и 4 PNG.

    python backend/scripts/smoke_pipeline.py
"""
import sys
import tempfile
from pathlib import Path

# чтобы импортировать пакет app
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PIL import Image, ImageDraw  # noqa: E402

from app.pipeline import draping, reconstruction, rendering, segmentation  # noqa: E402


def make_fake_clothing(path: Path) -> None:
    """Картинка «футболки» на белом фоне (имитация фото товара)."""
    img = Image.new("RGB", (800, 900), (255, 255, 255))
    d = ImageDraw.Draw(img)
    d.rectangle([250, 200, 550, 700], fill=(40, 110, 200))      # торс
    d.polygon([(250, 200), (150, 320), (220, 400), (250, 320)], fill=(40, 110, 200))
    d.polygon([(550, 200), (650, 320), (580, 400), (550, 320)], fill=(40, 110, 200))
    img.save(path)


def main() -> int:
    work = Path(tempfile.mkdtemp(prefix="smoke_"))
    print(f"workdir: {work}")

    src = work / "input.png"
    make_fake_clothing(src)

    clean = work / "clean.png"
    segmentation.segment(src, clean)
    assert clean.exists(), "segmentation: нет clean.png"
    assert Image.open(clean).mode == "RGBA", "clean должен быть RGBA"
    print("[1/4] segmentation OK ->", clean.name)

    mesh = work / "mesh.obj"
    tex = work / "tex.png"
    reconstruction.reconstruct(clean, mesh, tex)
    assert mesh.exists() and mesh.stat().st_size > 0, "reconstruction: пустой .obj"
    print("[2/4] reconstruction OK ->", mesh.name, f"({mesh.stat().st_size} B)")

    glb = work / "output.glb"
    draping.drape(mesh, tex, glb)
    assert glb.exists() and glb.stat().st_size > 0, "draping: пустой .glb"
    head = glb.read_bytes()[:4]
    assert head == b"glTF", f"draping: невалидный GLB-заголовок: {head!r}"
    print("[3/4] draping OK ->", glb.name, f"({glb.stat().st_size} B, magic={head!r})")

    previews = rendering.render_previews(glb, clean, work / "preview")
    assert len(previews) == 4, f"rendering: ожидалось 4 превью, получено {len(previews)}"
    for p in previews:
        assert p.exists() and p.stat().st_size > 0, f"пустое превью {p}"
    print("[4/4] rendering OK ->", [p.name for p in previews])

    print("\n✅ SMOKE PASSED — весь mock-пайплайн отработал.")
    print(f"   Артефакты: {work}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
