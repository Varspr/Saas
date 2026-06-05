"use client";

// Хук живого прогресса задания через WebSocket (вместо polling).
//
// WS-first: открываем сокет на /api/ws/jobs/{id}, каждое сообщение — полный
// Job. Если сокет не открылся/упал до завершения — мягкая деградация на
// разовый fetch getJob (не постоянный polling).

import { useEffect, useRef, useState } from "react";
import { Job, getJob, jobWsUrl } from "./api";

function isTerminal(j: Job | null): boolean {
  return j?.status === "done" || j?.status === "failed";
}

export function useJobStream(initial: Job | null) {
  const [job, setJob] = useState<Job | null>(initial);
  const [connected, setConnected] = useState(false);
  const jobId = initial?.id ?? null;
  const wsRef = useRef<WebSocket | null>(null);

  // Сбрасываем состояние при создании нового задания
  useEffect(() => {
    setJob(initial);
  }, [initial?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!jobId || isTerminal(initial)) return;

    let closed = false;
    let fallbackTimer: ReturnType<typeof setTimeout> | null = null;

    const stop = () => {
      closed = true;
      if (fallbackTimer) clearTimeout(fallbackTimer);
      wsRef.current?.close();
      wsRef.current = null;
    };

    // Разовый дозабор статуса, если WS недоступен
    const fallbackFetch = async () => {
      try {
        const fresh = await getJob(jobId);
        setJob(fresh);
        if (!isTerminal(fresh) && !closed) {
          fallbackTimer = setTimeout(fallbackFetch, 3000);
        }
      } catch {
        if (!closed) fallbackTimer = setTimeout(fallbackFetch, 3000);
      }
    };

    try {
      const ws = new WebSocket(jobWsUrl(jobId));
      wsRef.current = ws;

      ws.onopen = () => setConnected(true);
      ws.onmessage = (e) => {
        try {
          const data = JSON.parse(e.data) as Job;
          if ((data as any).error) return;
          setJob(data);
          if (isTerminal(data)) stop();
        } catch {
          /* ignore malformed frame */
        }
      };
      ws.onerror = () => setConnected(false);
      ws.onclose = () => {
        setConnected(false);
        // если закрылись до финала не по нашей воле — добираем статусом
        if (!closed) fallbackFetch();
      };
    } catch {
      fallbackFetch();
    }

    return stop;
  }, [jobId]); // eslint-disable-line react-hooks/exhaustive-deps

  return { job, connected };
}
