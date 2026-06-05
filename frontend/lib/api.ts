// Клиент API заданий (Фаза 0/4).

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

export type JobStatus =
  | "pending" | "scraping" | "segmenting" | "reconstructing"
  | "draping" | "rendering" | "uploading" | "done" | "failed";

export interface Job {
  id: string;
  status: JobStatus;
  progress: number;
  error: string | null;
  height_cm: number | null;
  weight_kg: number | null;
  output_glb_url: string | null;
  preview_urls: string[];
  created_at: string;
  updated_at: string;
}

// Параметры тела модели (рост/вес)
export interface BodyParams {
  height_cm?: number;
  weight_kg?: number;
}

// Подписи этапов для прогресс-бара
export const STATUS_LABELS: Record<JobStatus, string> = {
  pending: "В очереди",
  scraping: "Получаем фото",
  segmenting: "Убираем фон (SAM)",
  reconstructing: "Строим 3D (InstantMesh)",
  draping: "Надеваем на тело",
  rendering: "Рендерим превью",
  uploading: "Сохраняем результат",
  done: "Готово",
  failed: "Ошибка",
};

export async function createJobFromUrl(url: string, body: BodyParams = {}): Promise<Job> {
  const res = await fetch(`${API_BASE}/api/jobs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url, ...body }),
  });
  if (!res.ok) throw new Error(`Не удалось создать задание: ${res.status}`);
  return res.json();
}

export async function createJobFromFile(file: File, body: BodyParams = {}): Promise<Job> {
  const form = new FormData();
  form.append("file", file);
  if (body.height_cm) form.append("height_cm", String(body.height_cm));
  if (body.weight_kg) form.append("weight_kg", String(body.weight_kg));
  const res = await fetch(`${API_BASE}/api/jobs`, { method: "POST", body: form });
  if (!res.ok) throw new Error(`Не удалось создать задание: ${res.status}`);
  return res.json();
}

export async function getJob(id: string): Promise<Job> {
  const res = await fetch(`${API_BASE}/api/jobs/${id}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Задание не найдено: ${res.status}`);
  return res.json();
}

// WebSocket-адрес прогресса (http→ws, https→wss).
export function jobWsUrl(id: string): string {
  const base = API_BASE.replace(/^http/, "ws");
  return `${base}/api/ws/jobs/${id}`;
}

// Порядок этапов — для степпера на фронте.
export const STAGE_ORDER: JobStatus[] = [
  "scraping", "segmenting", "reconstructing", "draping", "rendering", "uploading", "done",
];
