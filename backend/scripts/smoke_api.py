"""End-to-end смоук API без Redis: Celery в eager-режиме, SQLite, файл-вход.

    python backend/scripts/smoke_api.py
"""
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PIL import Image  # noqa: E402


def main() -> int:
    # Celery выполняет задачи синхронно прямо в процессе
    from app.worker.celery_app import celery_app
    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = True

    from fastapi.testclient import TestClient
    from app.main import app
    from app.database import Base, engine
    Base.metadata.create_all(bind=engine)

    client = TestClient(app)

    # health
    assert client.get("/health").json()["mock_pipeline"] is True

    # картинка-«футболка»
    buf = io.BytesIO()
    img = Image.new("RGB", (600, 700), (255, 255, 255))
    for x in range(180, 420):
        for y in range(160, 560):
            img.putpixel((x, y), (200, 60, 60))
    img.save(buf, "PNG")
    buf.seek(0)

    # создать задание (multipart-файл + рост/вес) — таск выполнится синхронно
    r = client.post(
        "/api/jobs",
        files={"file": ("tshirt.png", buf, "image/png")},
        data={"height_cm": "185", "weight_kg": "95"},
    )
    assert r.status_code == 201, r.text
    job = r.json()
    assert job["height_cm"] == 185 and job["weight_kg"] == 95, job
    print("created:", job["id"], job["status"], f'{job["height_cm"]}см/{job["weight_kg"]}кг')

    # статус
    r = client.get(f"/api/jobs/{job['id']}")
    job = r.json()
    print("final status:", job["status"], job["progress"], "%")
    assert job["status"] == "done", f"ожидался done, error={job.get('error')}"
    assert job["output_glb_url"], "нет ссылки на glb"
    assert len(job["preview_urls"]) == 4, "ожидалось 4 превью"
    print("glb:", job["output_glb_url"])
    print("previews:", len(job["preview_urls"]))

    # эндпоинты результата
    assert client.get(f"/api/jobs/{job['id']}/preview").json()["preview_urls"]
    dl = client.get(f"/api/jobs/{job['id']}/download", follow_redirects=False)
    assert dl.status_code in (302, 307), dl.status_code
    print("download redirect ->", dl.headers.get("location"))

    # WebSocket: задание уже done → ждём один снимок и закрытие (без Redis).
    with client.websocket_connect(f"/api/ws/jobs/{job['id']}") as ws:
        msg = ws.receive_json()
        assert msg["status"] == "done", msg
        assert msg["progress"] == 100, msg
    print("ws snapshot ->", "done 100% (закрылся)")

    print("\n✅ API SMOKE PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
