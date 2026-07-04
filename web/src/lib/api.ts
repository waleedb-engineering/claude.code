// Dünner API-Client für die ClipForge-FastAPI-Bridge.
// Ruft ausschließlich bestehende Endpoints auf — keine Backend-Logik hier.

import type {
  BatchUploadResult,
  BrandKit,
  BulkDeleteResult,
  CaptionStyleInfo,
  ClipForgeConfig,
  ClipsJson,
  HealthResponse,
  Job,
  JobSummary,
  ManualExport,
  PublishingDraft,
  PublishingOverview,
  PublishingPlatform,
  RerenderRequest,
  StorageSummary,
  YouTubeDryRun,
  YouTubeLogoutResult,
  YouTubeOAuthStart,
  YouTubeOAuthStatus,
  YouTubeReadiness,
  YouTubeUploadResult,
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

async function del<T>(path: string): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, { method: "DELETE" });
  } catch {
    throw new ApiError(
      `Backend nicht erreichbar unter ${API_BASE}. Läuft FastAPI auf Port 8000?`,
      0,
    );
  }
  if (!res.ok) await parseError(res);
  return (await res.json()) as T;
}

export interface DeleteJobResult {
  deleted: boolean;
  job_id: string;
  removed_files_count: number;
  removed_bytes: number;
}

export async function deleteJob(
  jobId: string,
  force = false,
): Promise<DeleteJobResult> {
  const q = force ? "?force=true" : "";
  return del<DeleteJobResult>(`/api/jobs/${jobId}${q}`);
}

export interface DeleteManualExportResult {
  deleted: boolean;
  export_id: string;
  removed_files: string[];
  removed_bytes: number;
}

export async function deleteManualExport(
  jobId: string,
  exportId: string,
): Promise<DeleteManualExportResult> {
  return del<DeleteManualExportResult>(
    `/api/jobs/${jobId}/manual-exports/${exportId}`,
  );
}

export async function getStorage(): Promise<StorageSummary> {
  return getJson<StorageSummary>("/api/storage");
}

export async function getConfig(): Promise<ClipForgeConfig> {
  return getJson<ClipForgeConfig>("/api/config");
}

export async function getCaptionStyles(): Promise<CaptionStyleInfo[]> {
  const data = await getJson<{ styles: CaptionStyleInfo[] }>("/api/caption-styles");
  return data.styles;
}

export async function getBrandKit(): Promise<BrandKit> {
  return getJson<BrandKit>("/api/brand-kit");
}

export async function saveBrandKit(kit: Partial<BrandKit>): Promise<BrandKit> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}/api/brand-kit`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(kit),
    });
  } catch {
    throw new ApiError(
      `Backend nicht erreichbar unter ${API_BASE}. Läuft FastAPI auf Port 8000?`,
      0,
    );
  }
  if (!res.ok) await parseError(res);
  return (await res.json()) as BrandKit;
}

export interface CancelJobResult {
  canceled: boolean;
  job_id: string;
  status: string;
  message: string;
}

export async function cancelJob(jobId: string): Promise<CancelJobResult> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}/api/jobs/${jobId}/cancel`, { method: "POST" });
  } catch {
    throw new ApiError(
      `Backend nicht erreichbar unter ${API_BASE}. Läuft FastAPI auf Port 8000?`,
      0,
    );
  }
  if (!res.ok) await parseError(res);
  return (await res.json()) as CancelJobResult;
}

export async function bulkDeleteJobs(
  jobIds: string[],
  confirm: string,
  force = false,
): Promise<BulkDeleteResult> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}/api/jobs/bulk-delete`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ job_ids: jobIds, confirm, force }),
    });
  } catch {
    throw new ApiError(
      `Backend nicht erreichbar unter ${API_BASE}. Läuft FastAPI auf Port 8000?`,
      0,
    );
  }
  if (!res.ok) await parseError(res);
  return (await res.json()) as BulkDeleteResult;
}

export interface CreateJobInput {
  file: File;
  topN?: number;
  transcript?: File | null;
  removeSilence?: boolean;
  captionMode?: string;
  captionStyle?: string;
  reframeMode?: string;
  advancedAnalysis?: boolean;
}

export async function createJob({
  file,
  topN = 5,
  transcript = null,
  removeSilence = true,
  captionMode = "karaoke",
  captionStyle = "high_energy",
  reframeMode = "smart",
  advancedAnalysis = true,
}: CreateJobInput): Promise<{ job_id: string; status: string }> {
  const form = new FormData();
  form.append("file", file);
  form.append("top_n", String(topN));
  form.append("remove_silence", String(removeSilence));
  form.append("caption_mode", captionMode);
  form.append("caption_style", captionStyle);
  form.append("reframe_mode", reframeMode);
  form.append("advanced_analysis", String(advancedAnalysis));
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

export interface BatchUploadInput {
  files: File[];
  topN?: number;
  removeSilence?: boolean;
  captionMode?: string;
  captionStyle?: string;
  reframeMode?: string;
  advancedAnalysis?: boolean;
}

export async function batchUpload({
  files,
  topN = 5,
  removeSilence = true,
  captionMode = "karaoke",
  captionStyle = "high_energy",
  reframeMode = "smart",
  advancedAnalysis = true,
}: BatchUploadInput): Promise<BatchUploadResult> {
  const form = new FormData();
  for (const f of files) form.append("files", f);
  form.append("top_n", String(topN));
  form.append("remove_silence", String(removeSilence));
  form.append("caption_mode", captionMode);
  form.append("caption_style", captionStyle);
  form.append("reframe_mode", reframeMode);
  form.append("advanced_analysis", String(advancedAnalysis));

  let res: Response;
  try {
    res = await fetch(`${API_BASE}/api/jobs/batch`, { method: "POST", body: form });
  } catch {
    throw new ApiError(
      `Backend nicht erreichbar unter ${API_BASE}. Läuft FastAPI auf Port 8000?`,
      0,
    );
  }
  if (!res.ok) await parseError(res);
  return (await res.json()) as BatchUploadResult;
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

export function allExportsZipUrl(jobId: string): string {
  return `${API_BASE}/api/jobs/${jobId}/all-exports.zip`;
}

export { ApiError };

// --- Publishing Planner (lokale Drafts — kein echter Upload) ---------------

async function sendJson<T>(
  path: string,
  method: "POST" | "PATCH" | "DELETE",
  body?: unknown,
): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      method,
      headers: body !== undefined ? { "Content-Type": "application/json" } : undefined,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new ApiError(
      `Backend nicht erreichbar unter ${API_BASE}. Läuft FastAPI auf Port 8000?`,
      0,
    );
  }
  if (!res.ok) await parseError(res);
  return (await res.json()) as T;
}

export interface PublishingCreateBody {
  platform: PublishingPlatform;
  source_type: "auto_clip" | "manual_export";
  source_clip_index?: number;
  manual_export_id?: string;
}

export async function listPublishingDrafts(
  jobId: string,
): Promise<PublishingDraft[]> {
  const data = await getJson<{ drafts: PublishingDraft[] }>(
    `/api/jobs/${jobId}/publishing`,
  );
  return data.drafts;
}

export async function createPublishingDraft(
  jobId: string,
  body: PublishingCreateBody,
): Promise<PublishingDraft> {
  return sendJson<PublishingDraft>(`/api/jobs/${jobId}/publishing`, "POST", body);
}

export async function updatePublishingDraft(
  jobId: string,
  publishingId: string,
  patch: Partial<
    Pick<
      PublishingDraft,
      | "platform"
      | "title"
      | "caption"
      | "description"
      | "hashtags"
      | "pinned_comment"
      | "scheduled_at"
      | "status"
    >
  >,
): Promise<PublishingDraft> {
  return sendJson<PublishingDraft>(
    `/api/jobs/${jobId}/publishing/${publishingId}`,
    "PATCH",
    patch,
  );
}

export async function deletePublishingDraft(
  jobId: string,
  publishingId: string,
): Promise<void> {
  await sendJson<{ deleted: boolean }>(
    `/api/jobs/${jobId}/publishing/${publishingId}`,
    "DELETE",
  );
}

export async function validatePublishingDraft(
  jobId: string,
  publishingId: string,
): Promise<PublishingDraft> {
  return sendJson<PublishingDraft>(
    `/api/jobs/${jobId}/publishing/${publishingId}/validate`,
    "POST",
  );
}

export function publishingPackUrl(jobId: string, publishingId: string): string {
  return `${API_BASE}/api/jobs/${jobId}/publishing/${publishingId}/pack.zip`;
}

export interface PublishingDuplicateBody {
  platform?: PublishingPlatform;
  copy_schedule?: boolean;
}

export async function duplicatePublishingDraft(
  jobId: string,
  publishingId: string,
  body: PublishingDuplicateBody,
): Promise<PublishingDraft> {
  return sendJson<PublishingDraft>(
    `/api/jobs/${jobId}/publishing/${publishingId}/duplicate`,
    "POST",
    body,
  );
}

export interface PublishingOverviewFilters {
  status?: string;
  platform?: string;
  job_id?: string;
  q?: string;
  scheduled_only?: boolean;
}

export async function getPublishingOverview(
  filters: PublishingOverviewFilters = {},
): Promise<PublishingOverview> {
  const params = new URLSearchParams();
  if (filters.status) params.set("status", filters.status);
  if (filters.platform) params.set("platform", filters.platform);
  if (filters.job_id) params.set("job_id", filters.job_id);
  if (filters.q) params.set("q", filters.q);
  if (filters.scheduled_only) params.set("scheduled_only", "true");
  const qs = params.toString();
  return getJson<PublishingOverview>(`/api/publishing${qs ? `?${qs}` : ""}`);
}

// YouTube Dry-Run (Phase 1) — löst niemals einen echten Upload aus.
export async function youtubeDryRun(
  jobId: string,
  publishingId: string,
): Promise<YouTubeDryRun> {
  return sendJson<YouTubeDryRun>(
    `/api/jobs/${jobId}/publishing/${publishingId}/youtube/dry-run`,
    "POST",
  );
}

// YouTube OAuth-Readiness (Phase 2) — nur Status, nie Tokens/Secrets.
export async function youtubeReadiness(
  jobId: string,
  publishingId: string,
): Promise<YouTubeReadiness> {
  return getJson<YouTubeReadiness>(
    `/api/jobs/${jobId}/publishing/${publishingId}/youtube/readiness`,
  );
}

// Echter PRIVATER Upload (Phase 3). Antwort enthält NIE Tokens/Secrets; der
// Endpoint liefert immer HTTP 200 mit strukturiertem Ergebnis (success/
// error_code/idempotency_state). Nur privacy_status='private'.
export async function youtubePublishPrivate(
  jobId: string,
  publishingId: string,
): Promise<YouTubeUploadResult> {
  return sendJson<YouTubeUploadResult>(
    `/api/jobs/${jobId}/publishing/${publishingId}/youtube/publish`,
    "POST",
    { confirm: "UPLOAD_PRIVATE", privacy_status: "private" },
  );
}

export async function youtubeLogout(
  jobId: string,
  publishingId: string,
): Promise<YouTubeLogoutResult> {
  return sendJson<YouTubeLogoutResult>(
    `/api/jobs/${jobId}/publishing/${publishingId}/youtube/auth/logout`,
    "POST",
  );
}

// YouTube OAuth-Flow-Skelett (Phase 2b) — app-global, nicht draft-gebunden.
// Gibt NIE Tokens/Secrets zurück; kein echter Upload, kein Browser-Auto-Open.
export async function youtubeOAuthStatus(): Promise<YouTubeOAuthStatus> {
  return getJson<YouTubeOAuthStatus>(`/api/youtube/oauth/status`);
}

export async function youtubeOAuthStart(): Promise<YouTubeOAuthStart> {
  return sendJson<YouTubeOAuthStart>(`/api/youtube/oauth/start`, "POST");
}
