// Dünner API-Client für die ClipForge-FastAPI-Bridge.
// Ruft ausschließlich bestehende Endpoints auf — keine Backend-Logik hier.

import type {
  ClipsJson,
  HealthResponse,
  Job,
  JobSummary,
  ManualExport,
  RerenderRequest,
} from "./types";

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") ||
  "http://127.0.0.1:8000";

class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
    this.name = "ApiError";
  }
}

async function parseError(res: Response): Promise<never> {
  let detail = `${res.status} ${res.statusText}`;
  try {
    const data = await res.json();
    if (data && typeof data.detail === "string") detail = data.detail;
  } catch {
    /* kein JSON-Body */
  }
  throw new ApiError(detail, res.status);
}

async function getJson<T>(path: string): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, { cache: "no-store" });
  } catch {
    throw new ApiError(
      `Backend nicht erreichbar unter ${API_BASE}. Läuft FastAPI auf Port 8000?`,
      0,
    );
  }
  if (!res.ok) await parseError(res);
  return (await res.json()) as T;
}

export async function getHealth(): Promise<HealthResponse> {
  return getJson<HealthResponse>("/health");
}

export async function listJobs(): Promise<JobSummary[]> {
  const data = await getJson<{ jobs: JobSummary[] }>("/api/jobs");
  return data.jobs;
}

export async function getJob(jobId: string): Promise<Job> {
  return getJson<Job>(`/api/jobs/${jobId}`);
}

export async function getClips(jobId: string): Promise<ClipsJson> {
  return getJson<ClipsJson>(`/api/jobs/${jobId}/clips`);
}

export interface CreateJobInput {
  file: File;
  topN?: number;
  transcript?: File | null;
  removeSilence?: boolean;
  captionMode?: string;
  captionStyle?: string;
  reframeMode?: string;
}

export async function createJob({
  file,
  topN = 5,
  transcript = null,
  removeSilence = true,
  captionMode = "karaoke",
  captionStyle = "high_energy",
  reframeMode = "smart",
}: CreateJobInput): Promise<{ job_id: string; status: string }> {
  const form = new FormData();
  form.append("file", file);
  form.append("top_n", String(topN));
  form.append("remove_silence", String(removeSilence));
  form.append("caption_mode", captionMode);
  form.append("caption_style", captionStyle);
  form.append("reframe_mode", reframeMode);
  if (transcript) form.append("transcript", transcript);

  let res: Response;
  try {
    res = await fetch(`${API_BASE}/api/jobs`, { method: "POST", body: form });
  } catch {
    throw new ApiError(
      `Backend nicht erreichbar unter ${API_BASE}. Läuft FastAPI auf Port 8000?`,
      0,
    );
  }
  if (!res.ok) await parseError(res);
  return (await res.json()) as { job_id: string; status: string };
}

export async function getManualExports(jobId: string): Promise<ManualExport[]> {
  const data = await getJson<{ exports: ManualExport[] }>(
    `/api/jobs/${jobId}/manual-exports`,
  );
  return data.exports;
}

export async function rerenderClip(
  jobId: string,
  clipIndex: number,
  body: RerenderRequest,
): Promise<ManualExport> {
  let res: Response;
  try {
    res = await fetch(
      `${API_BASE}/api/jobs/${jobId}/clips/${clipIndex}/rerender`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      },
    );
  } catch {
    throw new ApiError(
      `Backend nicht erreichbar unter ${API_BASE}. Läuft FastAPI auf Port 8000?`,
      0,
    );
  }
  if (!res.ok) await parseError(res);
  return (await res.json()) as ManualExport;
}

export function manualExportPreviewUrl(jobId: string, exportId: string): string {
  return `${API_BASE}/api/jobs/${jobId}/manual-exports/${exportId}/preview`;
}

export function manualExportDownloadUrl(jobId: string, exportId: string): string {
  return `${API_BASE}/api/jobs/${jobId}/manual-exports/${exportId}/download`;
}

export function clipDownloadUrl(jobId: string, clipIndex: number): string {
  return `${API_BASE}/api/jobs/${jobId}/clips/${clipIndex}/download`;
}

export function clipPreviewUrl(jobId: string, clipIndex: number): string {
  return `${API_BASE}/api/jobs/${jobId}/clips/${clipIndex}/preview`;
}

export function exportsZipUrl(jobId: string): string {
  return `${API_BASE}/api/jobs/${jobId}/exports.zip`;
}

export { ApiError };
