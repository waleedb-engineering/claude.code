// Dünner API-Client für das Creator Studio (/api/studio/*).
// Keine Fachlogik hier — nur Typen, Aufrufe und einheitliche Fehler.

import { API_BASE } from "./api";
import { TOKEN_HEADER, apiFetch, getToken } from "./session";

export type StudioErrorDetail = {
  code: string;
  message: string;
  details?: Record<string, unknown>;
};

export class StudioApiError extends Error {
  status: number;
  code: string;
  details: Record<string, unknown>;
  constructor(status: number, detail: StudioErrorDetail) {
    super(detail.message);
    this.name = "StudioApiError";
    this.status = status;
    this.code = detail.code;
    this.details = detail.details ?? {};
  }
}

export type SceneVisual = {
  mode: "motion" | "static" | "media" | "ai_image" | "split";
  media: string | null;
  color: string | null;
  seed: number;
};

export type Scene = {
  id: string;
  kind: "hook" | "body" | "cta";
  text: string;
  voice_text: string | null;
  visual_prompt: string;
  headline: string;
  duration: number | null;
  pause_after: number;
  visual: SceneVisual;
  audio_source?: { start: number; end: number };
  words?: { text: string; start: number; end: number }[];
};

export type CaptionStyleId = "minimal" | "bold" | "karaoke" | "dynamic" | "none";

export type Project = {
  id: string;
  title: string;
  workflow: string;
  language: "de" | "en";
  tone: string;
  style: "clean" | "cinematic";
  aspect_ratio: string;
  resolution: string;
  status: "draft" | "ingesting" | "ready" | "failed";
  status_error: StudioErrorDetail | null;
  source: Record<string, unknown>;
  script: { generator?: string; needs_review?: boolean; notes?: string[] };
  scenes: Scene[];
  voice: { provider: string; voice_id: string | null; tone: string; speed: number };
  music: { track: string | null; volume: number; ducking: boolean; beat_sync: boolean };
  captions: { style: CaptionStyleId; use_brand: boolean };
  visuals: { image_provider: string; gameplay_media: string | null; headlines: boolean };
  budget_limit_usd: number;
  options: ProductionOptions;
  lineage: Record<string, unknown>;
  linked_job_id: string | null;
  exports: { job_id: string; render_id: string; exported_at: string }[];
  version: number;
  created_at: string;
  updated_at: string;
};

export type ProjectSummary = {
  id: string;
  title: string;
  workflow: string;
  language: string;
  status: Project["status"];
  status_error: StudioErrorDetail | null;
  aspect_ratio: string;
  resolution: string;
  scene_count: number;
  version: number;
  linked_job_id: string | null;
  export_count: number;
  created_at: string;
  updated_at: string;
};

export type Task = {
  id: string;
  kind: string;
  project_id: string | null;
  status: "queued" | "running" | "succeeded" | "failed" | "canceled" | "interrupted";
  progress: string[];
  result: Record<string, unknown> | null;
  error: StudioErrorDetail | null;
  attempts: number;
  created_at: string;
};

export type QualityCheck = {
  id: string;
  level: "ok" | "warn" | "fail";
  message: string;
  scene_id?: string;
};

export type RenderReport = {
  render_id: string;
  file: string;
  mode: "final" | "preview" | "scene";
  rendered_at: string;
  width: number;
  height: number;
  duration: number;
  has_audio: boolean;
  bytes: number;
  word_timing: string[];
  warnings: string[];
  fallbacks: { scene_id: string; kind: string; provider: string; reason: string }[];
  quality?: { checks: QualityCheck[]; passed: boolean };
  scene_id?: string;
};

export type MediaItem = { name: string; kind: "image" | "video" | "audio"; bytes: number };

export type ProjectView = {
  project: Project;
  tasks: Task[];
  renders: RenderReport[];
  media: MediaItem[];
  artifacts: { name: string; created_at: string | null; bytes: number }[];
};

export type Workflow = {
  id: string;
  needs: "text" | "url" | "file" | "job" | "product" | "youtube";
  available: boolean;
  reason: string;
  local: boolean;
};

export type Overview = {
  flags: Record<string, boolean>;
  workflows: Workflow[];
  project_count: number;
  recent_projects: ProjectSummary[];
  automation_count: number;
  idea_count: number;
  worker: { running: boolean; last_tick_at: string | null; last_error: string | null };
  llm_available: boolean;
};

export type ProviderInfo = {
  id: string;
  kind: string;
  label: string;
  local: boolean;
  paid: boolean;
  status: "ready" | "not_configured" | "disabled" | "unavailable";
  hint: string;
  requires_env: string[];
};

export type CredentialStatus = { provider: string; label: string; env: string; configured: boolean };

export type ProductionOptions = {
  platform: string;
  duration_target: number;
  goal: string;
  audience: string;
  cta: string;
  creative_instructions: string;
  forbidden_topics: string[];
  visual_style: string;
  media_type: "motion" | "static" | "ai_image";
  image_animation: boolean;
  voice_model: string;
  video_provider: string;
  video_model: string;
  music_mode: "track" | "none";
};

export type PlatformReadiness = {
  platform: string;
  state: "ready" | "not_connected";
  adapter: string | null;
  setup_steps: string[];
  fallback: string;
  note: string;
};

export type VoiceOptions = {
  language: string;
  providers: {
    id: string;
    label: string;
    status: string;
    hint: string;
    paid: boolean;
    produces_speech: boolean;
    voices: { id: string; label: string; tone: string }[];
  }[];
  auto_selection: { provider: string; voice_id: string; label: string; produces_speech: boolean };
};

export type Estimate = {
  total_usd: number;
  spent_usd: number;
  budget_limit_usd: number;
  within_budget: boolean;
  items: { provider: string; what: string; amount_usd: number }[];
  note: string;
};

export type AutomationRun = {
  id: string;
  status: string;
  trigger: string;
  scheduled_for: string | null;
  started_at: string | null;
  finished_at: string | null;
  project_id: string | null;
  job_id: string | null;
  draft_ids: string[];
  cost_usd: number;
  attempt: number;
  error: StudioErrorDetail | null;
  retried?: boolean;
};

export type Automation = {
  id: string;
  name: string;
  workflow: string;
  enabled: boolean;
  schedule: { frequency: string; time: string; timezone: string; weekday?: number; day?: number };
  items: string[];
  language: string;
  publishing: { mode: "none" | "draft"; platforms: string[] };
  budget_per_run_usd: number;
  monthly_budget_usd: number;
  next_run_at: string | null;
  last_run_at: string | null;
  runs: AutomationRun[];
  month_spend_usd: number;
  active: boolean;
};

export type AnalyticsRow = {
  job_id: string;
  publishing_id: string;
  platform: string;
  title: string;
  published_at: string | null;
  publish_source: string;
  external_url: string | null;
  studio_project_id: string | null;
  performance_potential: { value: number; source: "estimated" } | null;
  metrics: {
    views: number | null;
    likes: number | null;
    comments: number | null;
    source: "manual" | "synced";
    captured_at: string;
  } | null;
  metric_entries: number;
};

export type AnalyticsOverview = {
  rows: AnalyticsRow[];
  hook_comparisons: {
    group: string;
    best_publishing_id: string | null;
    note: string | null;
    variants: { publishing_id: string; platform: string; hook: string; views: number | null; source: string | null }[];
  }[];
  potential_vs_actual: {
    pairs: { publishing_id: string; title: string; potential: number; views: number }[];
    rank_agreement: number | null;
    note: string;
  };
  legend: Record<string, string>;
};

export type DraftState = {
  job_id: string;
  publishing_id: string;
  platform: string;
  title: string;
  status: string;
  state: "not_connected" | "ready" | "scheduled" | "due" | "published" | "failed";
  scheduled_at: string | null;
  published_at: string | null;
  publish_source: string | null;
  external_url: string | null;
};

export type Idea = {
  id: string;
  title: string;
  url: string;
  notes: string;
  niche: string;
  tags: string[];
  hook_type: string;
  format: string;
  platform: string;
  metrics: { views: number | null; likes: number | null; comments: number | null; source: string | null };
  created_at: string;
};

async function request<T>(method: string, path: string, body?: unknown, headers?: Record<string, string>): Promise<T> {
  let res: Response;
  try {
    res = await apiFetch(`${API_BASE}/api/studio${path}`, {
      method,
      cache: "no-store",
      headers: { ...(body !== undefined ? { "Content-Type": "application/json" } : {}), ...headers },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new StudioApiError(0, {
      code: "api_unreachable",
      message: `Backend nicht erreichbar unter ${API_BASE}.`,
    });
  }
  if (!res.ok) {
    let detail: StudioErrorDetail = { code: "http_error", message: `${res.status} ${res.statusText}` };
    try {
      const data = await res.json();
      if (data?.detail?.code) detail = data.detail;
      else if (typeof data?.detail === "string") detail = { code: "http_error", message: data.detail };
      else if (Array.isArray(data?.detail)) detail = { code: "validation_error", message: "Ungültige Eingabe." };
    } catch {
      /* kein JSON */
    }
    throw new StudioApiError(res.status, detail);
  }
  return (await res.json()) as T;
}

const get = <T,>(path: string) => request<T>("GET", path);
const post = <T,>(path: string, body: unknown = {}) => request<T>("POST", path, body);

/** Datei-Upload mit Fortschritt (XHR, weil fetch keinen Upload-Fortschritt kennt). */
export function uploadFile<T>(
  path: string,
  file: File,
  onProgress?: (fraction: number) => void,
  fields: Record<string, string> = {},
): Promise<T> {
  return getToken().then((token) => uploadWithToken<T>(path, file, onProgress, fields, token));
}

function uploadWithToken<T>(
  path: string,
  file: File,
  onProgress: ((fraction: number) => void) | undefined,
  fields: Record<string, string>,
  token: string | null,
): Promise<T> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const form = new FormData();
    form.append("file", file);
    Object.entries(fields).forEach(([k, v]) => form.append(k, v));
    xhr.open("POST", `${API_BASE}/api/studio${path}`);
    if (token) xhr.setRequestHeader(TOKEN_HEADER, token);
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && onProgress) onProgress(e.loaded / e.total);
    };
    xhr.onerror = () =>
      reject(new StudioApiError(0, { code: "api_unreachable", message: "Upload fehlgeschlagen: Backend nicht erreichbar." }));
    xhr.onload = () => {
      let data: unknown = null;
      try {
        data = JSON.parse(xhr.responseText);
      } catch {
        /* kein JSON */
      }
      if (xhr.status >= 200 && xhr.status < 300) return resolve(data as T);
      const detail = (data as { detail?: StudioErrorDetail })?.detail;
      reject(
        new StudioApiError(
          xhr.status,
          detail?.code ? detail : { code: "http_error", message: `Upload fehlgeschlagen (${xhr.status}).` },
        ),
      );
    };
    xhr.send(form);
  });
}

export const studio = {
  overview: () => get<Overview>("/overview"),
  providers: () => get<{ providers: ProviderInfo[]; platforms: PlatformReadiness[] }>("/providers"),
  credentials: () =>
    get<{ credentials: CredentialStatus[] }>("/credentials").then((d) => d.credentials),
  setCredential: (provider: string, apiKey: string) =>
    request<CredentialStatus>("PUT", `/credentials/${provider}`, { api_key: apiKey }),
  deleteCredential: (provider: string) => request<CredentialStatus>("DELETE", `/credentials/${provider}`),
  testCredential: (provider: string) =>
    post<{ ok: boolean; reason: string; message: string }>(`/credentials/${provider}/test`),
  voices: (language: string, tone = "") =>
    get<VoiceOptions>(`/voices?language=${encodeURIComponent(language)}&tone=${encodeURIComponent(tone)}`),
  async voicePreview(
    language: string,
    provider: string,
    voiceId: string | null,
    confirmCost = false,
    speed = 1,
  ): Promise<string> {
    const res = await apiFetch(`${API_BASE}/api/studio/voices/preview`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ language, provider, voice_id: voiceId, confirm_cost: confirmCost, speed }),
    });
    if (!res.ok) {
      const data = await res.json().catch(() => null);
      throw new StudioApiError(res.status, data?.detail?.code ? data.detail : { code: "http_error", message: "Hörprobe fehlgeschlagen." });
    }
    return URL.createObjectURL(await res.blob());
  },
  captionPreviewUrl: (style: string, aspect: string, text: string, useBrand: boolean) =>
    `${API_BASE}/api/studio/caption-preview?style=${style}&aspect_ratio=${encodeURIComponent(aspect)}&text=${encodeURIComponent(text)}&use_brand=${useBrand}`,
  music: () => get<{ tracks: { id: string; name: string; duration: number }[]; note: string }>("/music"),
  uploadMusic: (file: File, onProgress?: (f: number) => void) => uploadFile<{ id: string }>("/music", file, onProgress),

  projects: () => get<{ projects: ProjectSummary[] }>("/projects").then((d) => d.projects),
  createProject: (body: Record<string, unknown>, idempotencyKey: string) =>
    request<{ project: Project; task_id: string | null; needs_upload: boolean }>("POST", "/projects", body, {
      "Idempotency-Key": idempotencyKey,
    }),
  project: (id: string) => get<ProjectView>(`/projects/${id}`),
  patchProject: (id: string, patch: Record<string, unknown>) =>
    request<{ project: Project }>("PATCH", `/projects/${id}`, patch).then((d) => d.project),
  deleteProject: (id: string) => request<{ deleted: boolean }>("DELETE", `/projects/${id}`),
  duplicate: (id: string) => post<{ project: Project }>(`/projects/${id}/duplicate`).then((d) => d.project),
  remix: (id: string) => post<{ project: Project }>(`/projects/${id}/remix`).then((d) => d.project),
  uploadSource: (id: string, file: File, onProgress?: (f: number) => void, kind = "source") =>
    uploadFile<{ file: string }>(`/projects/${id}/source`, file, onProgress, { kind }),
  uploadMedia: (id: string, file: File, onProgress?: (f: number) => void) =>
    uploadFile<MediaItem>(`/projects/${id}/media`, file, onProgress),
  deleteMedia: (id: string, name: string) =>
    request<{ deleted: boolean }>("DELETE", `/projects/${id}/media/${encodeURIComponent(name)}`),
  mediaUrl: (id: string, name: string) => `${API_BASE}/api/studio/projects/${id}/media/${encodeURIComponent(name)}`,
  ingest: (id: string) => post<{ task: Task }>(`/projects/${id}/ingest`).then((d) => d.task),
  regenerateScene: (id: string, sceneId: string, expectedVersion: number, visualPrompt?: string) =>
    post<{ project: Project; task: Task }>(`/projects/${id}/scenes/${sceneId}/regenerate`, {
      expected_version: expectedVersion,
      visual_prompt: visualPrompt,
    }),
  estimate: (id: string) => get<Estimate>(`/projects/${id}/estimate`),
  quality: (id: string) => get<{ checks: QualityCheck[]; estimated_seconds: number; blocking: boolean }>(`/projects/${id}/quality`),
  render: (id: string, mode: "final" | "preview") =>
    post<{ task: Task }>(`/projects/${id}/render`, { mode }).then((d) => d.task),
  renderUrl: (id: string, renderId: string, download = false) =>
    `${API_BASE}/api/studio/projects/${id}/renders/${renderId}/file${download ? "?download=true" : ""}`,
  exportToJob: (id: string, renderId?: string) =>
    post<{ job_id: string; render_id: string; already_exported: boolean }>(`/projects/${id}/export`, {
      render_id: renderId,
    }),
  versions: (id: string) =>
    get<{ versions: { version: number; updated_at: string; scene_count: number }[] }>(`/projects/${id}/versions`).then((d) => d.versions),
  restoreVersion: (id: string, version: number) =>
    post<{ project: Project }>(`/projects/${id}/versions/${version}/restore`).then((d) => d.project),
  task: (id: string) => get<Task>(`/tasks/${id}`),
  retryTask: (id: string) => post<{ task: Task }>(`/tasks/${id}/retry`).then((d) => d.task),

  automations: () => get<{ automations: Automation[]; worker: Overview["worker"]; safety: string }>("/automations"),
  createAutomation: (body: Record<string, unknown>) =>
    post<{ automation: Automation }>("/automations", body).then((d) => d.automation),
  automationAction: (id: string, action: "pause" | "resume" | "run") => post<unknown>(`/automations/${id}/${action}`),
  retryRun: (id: string, runId: string) => post<unknown>(`/automations/${id}/runs/${runId}/retry`),
  deleteAutomation: (id: string) => request<{ deleted: boolean }>("DELETE", `/automations/${id}`),

  platforms: () => get<{ platforms: PlatformReadiness[]; safety: string }>("/publishing/platforms"),
  drafts: () => get<{ drafts: DraftState[] }>("/publishing/drafts").then((d) => d.drafts),
  markPublished: (jobId: string, pubId: string, url: string) =>
    post<unknown>(`/publishing/${jobId}/${pubId}/mark-published`, { confirm: true, url: url || null }),

  analytics: () => get<AnalyticsOverview>("/analytics"),
  addMetrics: (jobId: string, pubId: string, m: { views: number | null; likes: number | null; comments: number | null }) =>
    post<unknown>(`/analytics/${jobId}/${pubId}/metrics`, m),
  syncMetrics: (jobId: string, pubId: string) => post<unknown>(`/analytics/${jobId}/${pubId}/sync`),

  ideas: (query: string) =>
    get<{ ideas: Idea[]; options: { hook_types: string[]; formats: string[]; platforms: string[] }; notice: Record<string, string> }>(
      `/ideas${query ? `?${query}` : ""}`,
    ),
  createIdea: (body: Record<string, unknown>) => post<{ idea: Idea }>("/ideas", body).then((d) => d.idea),
  deleteIdea: (id: string) => request<{ deleted: boolean }>("DELETE", `/ideas/${id}`),
  useIdea: (id: string, topic: string, language: string) =>
    post<{ project: Project; task_id: string; originality_notice: string }>(`/ideas/${id}/use`, { topic, language }),
};

/** Wartet auf das Ende einer Aufgabe und meldet Zwischenstände. */
export async function waitForTask(taskId: string, onUpdate?: (t: Task) => void, signal?: { cancelled: boolean }): Promise<Task> {
  for (;;) {
    const task = await studio.task(taskId);
    onUpdate?.(task);
    if (task.status !== "queued" && task.status !== "running") return task;
    if (signal?.cancelled) return task;
    await new Promise((r) => setTimeout(r, 1000));
  }
}

export function errorMessage(e: unknown): string {
  return e instanceof Error ? e.message : "Unbekannter Fehler.";
}
