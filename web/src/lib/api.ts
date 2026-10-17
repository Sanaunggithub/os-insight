import type { MetricSample, OsInfo, StressJob } from "@/lib/types";

const API_BASE = "/backend";

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`API request failed (${response.status})`);
  }
  return response.json() as Promise<T>;
}

export function getLiveMetrics(): Promise<MetricSample> {
  return getJson("/metrics/live");
}

export function getMetricHistory(service: string): Promise<MetricSample[]> {
  const params = new URLSearchParams({ service, minutes: "60" });
  return getJson(`/metrics/history?${params.toString()}`);
}

export function getStressJobs(): Promise<StressJob[]> {
  return getJson("/stress?limit=50");
}

export function getOsInfo(): Promise<OsInfo> {
  return getJson("/os-info");
}

export async function createStressJob(input: {
  kind: "cpu" | "memory";
  intensity: number;
  duration_s: number;
}): Promise<StressJob> {
  const response = await fetch(`${API_BASE}/stress`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  if (!response.ok) {
    const detail = await response.json().catch(() => null);
    throw new Error(
      detail?.detail
        ? `Could not create job: ${JSON.stringify(detail.detail)}`
        : `Could not create job (${response.status})`,
    );
  }
  return response.json() as Promise<StressJob>;
}
