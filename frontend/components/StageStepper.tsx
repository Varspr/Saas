"use client";

// Визуализация этапов пайплайна (Фазы 1-4) с подсветкой текущего.

import { JobStatus, STAGE_ORDER, STATUS_LABELS } from "@/lib/api";

const STEPS: { key: JobStatus; short: string }[] = [
  { key: "scraping", short: "Фото" },
  { key: "segmenting", short: "Фон" },
  { key: "reconstructing", short: "3D" },
  { key: "draping", short: "Примерка" },
  { key: "rendering", short: "Рендер" },
  { key: "uploading", short: "Сохранение" },
];

export default function StageStepper({ status }: { status: JobStatus }) {
  const failed = status === "failed";
  const currentIdx =
    status === "done"
      ? STEPS.length
      : STAGE_ORDER.indexOf(status === "pending" ? "scraping" : status);

  return (
    <div className="stepper">
      {STEPS.map((step, i) => {
        const done = i < currentIdx;
        const active = i === currentIdx && !failed && status !== "done";
        const cls = done ? "done" : active ? "active" : "todo";
        return (
          <div key={step.key} className={`step ${cls}`} title={STATUS_LABELS[step.key]}>
            <div className="dot">{done ? "✓" : i + 1}</div>
            <span>{step.short}</span>
          </div>
        );
      })}
    </div>
  );
}
