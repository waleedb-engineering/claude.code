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
  mode: "motion" | "static" | "media" | "ai_image" | "split" | "ai_video" | "avatar";
  media: string | null;
  color: string | null;
  seed: number;
  start?: number;
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
  transition?: TransitionId;
  source_text?: string;
  voice_media?: string | null;
  fit_speech?: boolean;
  visual: SceneVisual;
  audio_source?: { start: number; end: number };
  words?: { text: string; start: number; end: number }[];
  zoom?: { factor: number; focus: ZoomFocus; ramp: boolean };
  sfx?: { track: string; at: number; volume: number }[];
};

export type Ease = "linear" | "ease_in" | "ease_out" | "ease_in_out";
export type Keyframe = { t: number; v: number; ease: Ease };
export type TimelineItem = {
  id: string;
  start: number;
  duration: number;
  group?: string;
  src?: string;
  in?: number;
  x?: number;
  y?: number;
  scale?: number;
  rotation?: number;
  opacity?: number;
  volume?: number;
  fade_in?: number;
  fade_out?: number;
  blur?: number;
  audio?: boolean;
  text?: string;
  color?: string;
  size?: number;
  position?: "top" | "middle" | "bottom";
  keyframes?: Record<string, Keyframe[]>;
};
export type TrackKind = "video" | "overlay" | "audio" | "caption";
export type TimelineTrack = { id: string; kind: TrackKind; name: string; muted: boolean; locked: boolean; hidden: boolean; items: TimelineItem[] };
export type Timeline = { version: number; tracks: TimelineTrack[] };
export type TimelineOp = Record<string, unknown> & { op: string };

export type ZoomFocus = "center" | "face" | "top" | "bottom" | "left" | "right";
export const CAPTION_FONTS = ["Arial", "Helvetica", "Verdana", "Impact", "Georgia", "DejaVu Sans", "Liberation Sans"] as const;

export type TransitionId =
  | "auto" | "cut" | "fade" | "fadeblack" | "zoom" | "slide" | "slideup" | "smooth" | "wipe" | "dissolve" | "circle";
export const TRANSITION_IDS: TransitionId[] = [
  "auto", "cut", "fade", "fadeblack", "zoom", "slide", "slideup", "smooth", "wipe", "dissolve", "circle",
];

export type Template = {
  id: string;
  builtin: boolean;
  name: string;
  name_en: string;
  description: string;
  settings: Record<string, unknown>;
  structure: { kind: string; hint: string }[];
};

export type LocalModel = {
  id: string;
  label: string;
  group: "background" | "face" | "piper" | string;
  language: string | null;
  size_mb: number;
  license: string;
  commercial_use: boolean | null;
  installed: boolean;
};

export type StreamMeta = {
  id: string;
  title: string;
  platform: "twitch" | "youtube" | "kick" | "obs" | "upload";
  status: string;
  created_at: string;
  how_to_get: string;
  video: { original_name: string; duration: number; width: number; height: number } | null;
  chat: { format: string; messages: number; users: number } | null;
  live?: { task_id: string; status: string; channel: string | null } | null;
  jobs?: { job_id: string; highlights: string[] }[];
  error?: string;
};

export type Highlight = {
  id: string;
  t: number;
  start: number;
  end: number;
  score: number;
  reasons: string[];
  components: Record<string, number>;
  chat_categories: Record<string, number>;
  top_terms: string[];
  text: string;
  edited?: boolean;
  variant?: string;
  variants?: ClipVariant[];
};

export type ClipVariant = {
  variant: "short" | "balanced" | "context";
  label: string;
  start: number;
  end: number;
  duration: number;
  suitability: number;
  suitability_reasons: string[];
};

export type StreamEvaluation = {
  tp: number;
  fp: number;
  fn: number;
  precision: number;
  recall: number;
  f1: number;
  time_offset_mean_s: number | null;
  event_fully_contained: number | null;
  labels: number;
  note: string;
  missed: { start: number; end: number; label: string }[];
};

export type StreamAnalysis = {
  duration: number;
  signals: string[];
  weights: Record<string, number>;
  chat_delay: number;
  chat_delay_note: string;
  chat_messages: number;
  heatmap: { step: number; score: number[] };
  highlights: Highlight[];
  disclaimer: string;
  judged?: Record<string, "hit" | "miss">;
  weights_source?: string;
  clip_limits?: { min_len: number; max_len: number };
};

export type AgentMessage = {
  id: string;
  at: string;
  role: "user" | "assistant";
  text: string;
  engine?: string;
  notes?: string[];
  cost_usd?: number;
  plan?: {
    status: "pending" | "done" | "partial" | "discarded" | "empty";
    needs_confirmation: boolean;
    steps: { tool: string; args: Record<string, unknown>; label: string; confirm: boolean; cost: string }[];
    results?: { tool: string; ok: boolean; change?: string; error?: string; task_id?: string }[];
    undone?: boolean;
  };
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
  voice: { provider: string; voice_id: string | null; tone: string; speed: number; volume: number };
  transitions: { style: TransitionId; duration: number };
  template_id?: string;
  music: { track: string | null; volume: number; ducking: boolean; beat_sync: boolean };
  captions: {
    style: CaptionStyleId;
    use_brand: boolean;
    position?: "bottom" | "middle" | "top";
    font?: string | null;
    color?: string | null;
    highlight_color?: string | null;
    size?: number;
  };
  audio?: { loudnorm: boolean; target_lufs: number };
  timeline?: Timeline;
  visuals: {
    image_provider: string;
    gameplay_media: string | null;
    avatar_image: string | null;
    video_provider: string;
    avatar_provider: string;
    avatar_layout?: string;
    headlines: boolean;
  };
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

export type MediaItem = {
  name: string;
  kind: "image" | "video" | "audio";
  bytes: number;
  tags?: string[];
  origin?: { source: string; author?: string; page?: string; license?: { name: string; url: string } } | null;
};

export type BrollHit = {
  source: "library" | "pexels" | "pixabay";
  name?: string;
  kind: "image" | "video";
  score?: number;
  matched?: string[];
  id?: string;
  preview?: string;
  download?: string;
  author?: string;
  page?: string;
  duration?: number;
  license?: { name: string; url: string };
};

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
  live_verified: boolean;
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
    shares?: number | null;
    reach?: number | null;
    saves?: number | null;
    engagement_rate?: number | null;
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
  state: "not_connected" | "ready" | "scheduled" | "due" | "published" | "failed" | "uploading" | "in_platform_drafts";
  scheduled_at: string | null;
  published_at: string | null;
  publish_source: string | null;
  external_url: string | null;
  auto_publish?: boolean;
  error?: string | null;
};

export type SocialCopy = {
  engine: string;
  keywords: string[];
  cost_usd: number;
  platforms: Record<string, { title: string; description: string; hashtags: string[]; cta: string }>;
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
  clones: () =>
    get<{ clones: { id: string; name: string; voice_id: string; created_at: string; consent: { basis: string; speaker: string } }[]; enabled: boolean }>(
      "/voices/clones",
    ),
  async createClone(form: FormData) {
    // apiFetch hängt das Sicherheits-Token bei Änderungen selbst an
    const res = await apiFetch(`${API_BASE}/api/studio/voices/clones`, { method: "POST", body: form });
    const data = await res.json().catch(() => null);
    if (!res.ok) throw new StudioApiError(res.status, data?.detail?.code ? data.detail : { code: "http_error", message: "Stimmklon fehlgeschlagen." });
    return data;
  },
  deleteClone: (id: string) => request<{ deleted: boolean }>("DELETE", `/voices/clones/${id}`),
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

  templates: () => get<{ templates: Template[] }>("/templates").then((d) => d.templates),
  saveTemplate: (body: Record<string, unknown>) =>
    post<{ template: Template }>("/templates", body).then((d) => d.template),
  deleteTemplate: (id: string) => request<{ deleted: boolean }>("DELETE", `/templates/${id}`),
  applyTemplate: (id: string, templateId: string, expectedVersion: number) =>
    post<{ project: Project }>(`/projects/${id}/apply-template`, {
      template_id: templateId,
      expected_version: expectedVersion,
    }).then((d) => d.project),

  brollSuggest: (id: string, sceneId: string, stock?: string, kind = "video") =>
    get<{ keywords: string[]; query: string; library: BrollHit[]; stock: BrollHit[]; stock_available: string[] }>(
      `/projects/${id}/scenes/${sceneId}/broll?kind=${kind}${stock ? `&stock=${stock}` : ""}`,
    ),
  brollImport: (id: string, item: BrollHit, query: string) =>
    post<{ name: string }>(`/projects/${id}/broll/import`, { item, query }),
  brollAuto: (id: string, stock?: string) =>
    post<{ task: Task }>(`/projects/${id}/broll/auto`, { stock: stock || null }).then((d) => d.task),
  setMediaTags: (id: string, name: string, tags: string[]) =>
    request<{ tags: string[] }>("PUT", `/projects/${id}/media/${encodeURIComponent(name)}/tags`, { tags }),
  translationEngines: () =>
    get<{ engines: { id: string; label: string; paid: boolean; ready: boolean | Record<string, boolean> }[] }>(
      "/translation/engines",
    ),
  streams: () => get<{ streams: StreamMeta[] }>("/streams").then((d) => d.streams),
  createStream: (body: Record<string, unknown>) => post<{ stream: StreamMeta }>("/streams", body).then((d) => d.stream),
  stream: (id: string) => get<{ stream: StreamMeta; analysis: StreamAnalysis | null }>(`/streams/${id}`),
  deleteStream: (id: string) => request<{ deleted: boolean }>("DELETE", `/streams/${id}`),
  uploadStreamVideo: (id: string, file: File, onProgress?: (f: number) => void) =>
    uploadFile<{ stream: StreamMeta }>(`/streams/${id}/video`, file, onProgress),
  uploadStreamChat: (id: string, file: File) => uploadFile<{ stream: StreamMeta }>(`/streams/${id}/chat`, file),
  analyzeStream: (id: string, body: Record<string, unknown>) =>
    post<{ task: Task }>(`/streams/${id}/analyze`, body).then((d) => d.task),
  patchHighlight: (id: string, hid: string, body: Record<string, unknown>) =>
    request<{ highlight: Highlight }>("PATCH", `/streams/${id}/highlights/${hid}`, body).then((d) => d.highlight),
  judgeHighlight: (id: string, hid: string, verdict: "hit" | "miss" | "clear") =>
    post<{ labels: unknown }>(`/streams/${id}/highlights/${hid}/judge`, { verdict }),
  streamLabels: (id: string) =>
    get<{ highlights: { start: number; end: number; peak: number; label: string; from?: string }[] }>(`/streams/${id}/labels`),
  putStreamLabels: (id: string, highlights: Record<string, unknown>[]) =>
    request<unknown>("PUT", `/streams/${id}/labels`, { highlights }),
  streamEvaluation: (id: string) => get<StreamEvaluation>(`/streams/${id}/evaluation`),
  tuneStreamWeights: (apply: boolean) =>
    post<{ f1_default: number; f1_tuned: number; f1_leave_one_out: number | null; cases: number; applied: boolean; best_group_factors: Record<string, number> }>(
      "/stream-weights/tune",
      { apply },
    ),
  previewHighlight: (id: string, hid: string) =>
    post<{ task: Task }>(`/streams/${id}/highlights/${hid}/preview`).then((d) => d.task),
  highlightPreviewUrl: (id: string, hid: string) => `${API_BASE}/api/studio/streams/${id}/highlights/${hid}/preview`,
  renderHighlights: (id: string, body: Record<string, unknown>) =>
    post<{ task: Task }>(`/streams/${id}/render`, body).then((d) => d.task),
  startLive: (id: string, body: Record<string, unknown>) => post<{ task: Task }>(`/streams/${id}/live`, body).then((d) => d.task),
  liveState: (id: string) =>
    get<{
      state: {
        messages: number;
        elapsed: number;
        chat_connected: boolean;
        chat_error: string | null;
        pending?: number;
        skipped?: number;
        youtube?: { connected: boolean; error: string | null; polls: number; quota_units_used: number } | null;
        events: { id: string; event: number; start: number; end: number; reason: string; status: string; file?: string; queue_position?: number; note?: string }[];
      } | null;
      availability: Record<string, { realtime: boolean; note?: string; verified?: string }>;
    }>(`/streams/${id}/live`),
  liveClipUrl: (id: string, lid: string) => `${API_BASE}/api/studio/streams/${id}/live/${lid}`,
  cancelTask: (id: string) => post<unknown>(`/tasks/${id}/cancel`),
  thumbnails: (id: string, renderId: string) =>
    post<{ thumbnails: { file: string; t: number; score: number; reasons: string[] }[] }>(`/projects/${id}/renders/${renderId}/thumbnails`).then((d) => d.thumbnails),
  thumbnailUrl: (id: string, renderId: string, file: string) => `${API_BASE}/api/studio/projects/${id}/renders/${renderId}/thumbnails/${file}`,
  skills: () =>
    get<{ skills: { name: string; description: string; version: string; license: string | null; enabled: boolean; blocked: boolean; warnings: string[]; rejected: string[]; tools: string[]; source: { type: string; repo?: string; commit?: string; name?: string }; changed: boolean; requires?: string[]; author?: string | null; imported_by?: string | null }[] }>(
      "/skills",
    ).then((d) => d.skills),
  importSkillGithub: (url: string, path: string) => post<{ skills: unknown[] }>("/skills/import/github", { url, path }),
  importSkillZip: (file: File) => uploadFile<{ skills: unknown[] }>("/skills/import/zip", file),
  toggleSkill: (name: string, enabled: boolean) => request<unknown>("PATCH", `/skills/${name}`, { enabled }),
  deleteSkill: (name: string) => request<unknown>("DELETE", `/skills/${name}`),
  providerMatrix: () =>
    get<{ providers: { id: string; label: string; category: string; status: string; paid: boolean; cost: string; limits: string; live_verified: boolean; fallback: string }[] }>(
      "/provider-matrix",
    ).then((d) => d.providers),
  ollamaStatus: () =>
    get<{
      reachable: boolean;
      version: string | null;
      models: { name: string; size_gb: number; tool_calling: boolean }[];
      model: string | null;
      model_reason: string;
      hint?: string;
      hardware: { os: string; arch: string; cpus: number; ram_gb: number | null; apple_silicon: boolean; nvidia_gpu: boolean };
      recommendation: { model?: string; download_gb?: number; reason?: string; acceleration?: string; command?: string; note?: string };
    }>("/agent/ollama"),
  ollamaTest: () => post<{ ok: boolean; stage: string; message: string; model?: string; seconds?: number }>("/agent/ollama/test"),
  agentEngines: () =>
    get<{ engines: { id: string; label: string; ready: boolean; paid: boolean; hint?: string; cost_per_message_usd?: number | null; model?: string }[] }>(
      "/agent/engines",
    ),
  agentHistory: (kind: string, id: string) => get<{ messages: AgentMessage[] }>(`/agent/${kind}/${id}`).then((d) => d.messages),
  agentSend: (kind: string, id: string, message: string, engine: string, confirmCost = false) =>
    post<{ message: AgentMessage }>(`/agent/${kind}/${id}`, { message, engine, confirm_cost: confirmCost }).then((d) => d.message),
  agentExecute: (kind: string, id: string, entryId: string, confirm = false) =>
    post<{ message: AgentMessage }>(`/agent/${kind}/${id}/${entryId}/execute`, { confirm }).then((d) => d.message),
  agentDiscard: (kind: string, id: string, entryId: string) => post<unknown>(`/agent/${kind}/${id}/${entryId}/discard`),
  agentUndo: (kind: string, id: string) => post<{ project: Project }>(`/agent/${kind}/${id}/undo`),
  hardware: () =>
    get<{ system: string; nvidia_gpus: { name: string; vram_gb: number }[]; apple_silicon: boolean; ram_gb: number | null; local_ai_video: string; note: string; free_alternatives: string[]; paid_alternative: string }>(
      "/hardware",
    ),
  faces: () =>
    get<{
      enabled: boolean;
      reason: string;
      label: string;
      faces: { id: string; name: string; created_at: string; consent: { basis: string; person: string } }[];
    }>("/faces"),
  async registerFace(form: FormData) {
    const res = await apiFetch(`${API_BASE}/api/studio/faces`, { method: "POST", body: form });
    const data = await res.json().catch(() => null);
    if (!res.ok) throw new StudioApiError(res.status, data?.detail?.code ? data.detail : { code: "http_error", message: "Registrierung fehlgeschlagen." });
    return data;
  },
  deleteFace: (id: string) => request<{ deleted: boolean }>("DELETE", `/faces/${id}`),
  faceAudit: () => get<{ entries: { at: string; event: string; result?: string; target?: string }[] }>("/faces/audit"),
  faceSwap: (id: string, name: string, faceId: string, confirmCost: boolean) =>
    post<{ task: Task }>(`/projects/${id}/media/${encodeURIComponent(name)}/faceswap`, {
      face_id: faceId,
      confirm_cost: confirmCost,
    }).then((d) => d.task),
  models: (group?: string) =>
    get<{ models: LocalModel[] }>(`/models${group ? `?group=${group}` : ""}`).then((d) => d.models),
  downloadModel: (id: string) =>
    post<{ task: Task }>(`/models/${id}/download`, { accept_license: true }).then((d) => d.task),
  deleteModel: (id: string) => request<{ deleted: boolean }>("DELETE", `/models/${id}`),
  async backgroundPreview(id: string, name: string, body: Record<string, unknown>): Promise<string> {
    const res = await apiFetch(`${API_BASE}/api/studio/projects/${id}/media/${encodeURIComponent(name)}/background/preview`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!res.ok) {
      const data = await res.json().catch(() => null);
      throw new StudioApiError(res.status, data?.detail?.code ? data.detail : { code: "http_error", message: "Vorschau fehlgeschlagen." });
    }
    return URL.createObjectURL(await res.blob());
  },
  startBackground: (id: string, name: string, body: Record<string, unknown>) =>
    post<{ task: Task }>(`/projects/${id}/media/${encodeURIComponent(name)}/background`, body).then((d) => d.task),

  projects: () => get<{ projects: ProjectSummary[] }>("/projects").then((d) => d.projects),
  createProject: (body: Record<string, unknown>, idempotencyKey: string) =>
    request<{ project: Project; task_id: string | null; needs_upload: boolean }>("POST", "/projects", body, {
      "Idempotency-Key": idempotencyKey,
    }),
  project: (id: string) => get<ProjectView>(`/projects/${id}`),
  timelineOps: (id: string, ops: TimelineOp[], expectedVersion: number) =>
    post<{ project: Project; results: Record<string, string>[] }>(`/projects/${id}/timeline/ops`, { ops, expected_version: expectedVersion }),
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
  accounts: () =>
    get<{
      accounts: { platform: string; label: string; state: string; account: string | null; requires_env: string[] }[];
      not_supported: Record<string, string>;
    }>("/accounts"),
  connectAccount: (platform: string) => post<{ auth_url: string }>(`/accounts/${platform}/connect`),
  disconnectAccount: (platform: string) => request<{ disconnected: boolean }>("DELETE", `/accounts/${platform}`),
  tiktokUpload: (jobId: string, pubId: string) =>
    post<{ task: Task | null; already: boolean }>(`/publishing/${jobId}/${pubId}/tiktok`, { confirm: true }),
  tiktokStatus: (jobId: string, pubId: string) => post<unknown>(`/publishing/${jobId}/${pubId}/tiktok/status`),
  directPublish: (jobId: string, pubId: string, options: Record<string, unknown>, confirmCost = false) =>
    post<{ task: Task | null; already: boolean }>(`/publishing/${jobId}/${pubId}/publish`, {
      confirm: true,
      confirm_cost: confirmCost,
      options,
    }),
  schedulePublish: (jobId: string, pubId: string, at: string, options: Record<string, unknown>, confirmCost = false) =>
    post<unknown>(`/publishing/${jobId}/${pubId}/schedule`, { at, approve: true, confirm_cost: confirmCost, options }),
  unschedule: (jobId: string, pubId: string) => request<unknown>("DELETE", `/publishing/${jobId}/${pubId}/schedule`),
  tiktokCreatorInfo: () =>
    get<{ nickname: string; privacy_level_options: string[]; audited_app: boolean; max_video_post_duration_sec: number }>(
      "/publishing/tiktok/creator-info",
    ),
  socialCopy: (id: string, engine: "local" | "anthropic", confirmCost = false) =>
    post<SocialCopy>(`/projects/${id}/social-copy`, { engine, confirm_cost: confirmCost }),
  trends: () =>
    get<{ platforms: Record<string, { available: boolean; note: string }>; categories: Record<string, string> }>("/trends"),
  trendsYoutube: (region: string, category: string) =>
    get<{
      source: string;
      note: string;
      videos: { id: string; title: string; channel: string; views: number | null; url: string }[];
      keywords: { keyword: string; count: number }[];
    }>(`/trends/youtube?region=${encodeURIComponent(region)}&category=${encodeURIComponent(category)}`),
  markPublished: (jobId: string, pubId: string, url: string) =>
    post<unknown>(`/publishing/${jobId}/${pubId}/mark-published`, { confirm: true, url: url || null }),

  analytics: () => get<AnalyticsOverview>("/analytics"),
  addMetrics: (jobId: string, pubId: string, m: Record<string, number | null>) =>
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
