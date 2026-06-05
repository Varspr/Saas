"use client";

import { useState } from "react";
import dynamic from "next/dynamic";
import {
  createJobFromFile, createJobFromUrl, Job, STATUS_LABELS,
} from "@/lib/api";
import { useJobStream } from "@/lib/useJobStream";
import StageStepper from "@/components/StageStepper";

// Three.js рендерится только в браузере
const ModelViewer = dynamic(() => import("@/components/ModelViewer"), { ssr: false });

export default function Home() {
  const [url, setUrl] = useState("");
  const [height, setHeight] = useState(175);
  const [weight, setWeight] = useState(70);
  const [created, setCreated] = useState<Job | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // Живой прогресс по WebSocket (без polling)
  const { job, connected } = useJobStream(created);

  const bodyParams = { height_cm: height, weight_kg: weight };

  async function submitUrl() {
    if (!url.trim()) return;
    await run(() => createJobFromUrl(url.trim(), bodyParams));
  }

  async function submitFile(file: File) {
    await run(() => createJobFromFile(file, bodyParams));
  }

  async function run(create: () => Promise<Job>) {
    setError(null);
    setBusy(true);
    try {
      setCreated(await create());
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  const inProgress = job && job.status !== "done" && job.status !== "failed";

  return (
    <div className="container">
      <h1>AI Virtual Try-On</h1>
      <p className="subtitle">
        Ссылка на товар или фото одежды → 3D-модель в одежде, которую можно крутить.
      </p>

      <div className="card">
        <div className="row">
          <input
            type="text"
            placeholder="https://… ссылка на товар или картинку"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            disabled={busy}
            onKeyDown={(e) => e.key === "Enter" && submitUrl()}
          />
          <button onClick={submitUrl} disabled={busy || !url.trim()}>
            Примерить
          </button>
        </div>
        <div className="divider">или</div>
        <input
          type="file"
          accept="image/*"
          disabled={busy}
          onChange={(e) => e.target.files?.[0] && submitFile(e.target.files[0])}
        />

        <div className="body-params">
          <label>
            Рост, см
            <input
              type="number" min={120} max={220} value={height}
              disabled={busy}
              onChange={(e) => setHeight(Number(e.target.value))}
            />
          </label>
          <label>
            Вес, кг
            <input
              type="number" min={30} max={250} value={weight}
              disabled={busy}
              onChange={(e) => setWeight(Number(e.target.value))}
            />
          </label>
          <span className="muted">Параметры 3D-модели тела</span>
        </div>
      </div>

      {error && <div className="card error">{error}</div>}

      {job && (
        <div className="card">
          <div className="status-line">
            <span>
              {STATUS_LABELS[job.status]}
              {inProgress && (
                <span className={`conn ${connected ? "live" : "off"}`}>
                  {connected ? "● live" : "○ переподключение"}
                </span>
              )}
            </span>
            <span className="muted">{job.progress}%</span>
          </div>

          <div className="progress-track">
            <div
              className={`progress-fill ${job.status === "failed" ? "fail" : ""}`}
              style={{ width: `${job.progress}%` }}
            />
          </div>

          {job.status !== "failed" && <StageStepper status={job.status} />}

          {job.status === "failed" && (
            <div className="error" style={{ marginTop: 12 }}>{job.error}</div>
          )}

          {inProgress && (
            <p className="muted" style={{ marginTop: 12 }}>
              Обработка обычно занимает 3–5 минут. Прогресс обновляется в реальном времени.
            </p>
          )}

          {job.status === "done" && job.output_glb_url && (
            <div style={{ marginTop: 16 }}>
              <ModelViewer url={job.output_glb_url} />

              {job.preview_urls.length > 0 && (
                <div className="previews">
                  {job.preview_urls.map((src) => (
                    <img key={src} src={src} alt="preview" />
                  ))}
                </div>
              )}

              <a className="download" href={job.output_glb_url} download>
                ⬇ Скачать .glb
              </a>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
