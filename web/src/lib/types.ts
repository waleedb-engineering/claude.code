// TypeScript-Typen, die die FastAPI-Antworten spiegeln.
// Quelle der Wahrheit bleibt das Backend (api/jobs.py, api/clipforge/models.py).
// Hier wird KEINE Logik dupliziert — nur Formen für die Anzeige.

export type JobStatus = "queued" | "processing" | "completed" | "failed";

export interface JobSummary {
  id: string;
  status: JobStatus;
  filename: string;
  created_at: string;
  updated_at: string;
  clip_count: number | null;
  error: string | null;
}

export interface ResultClip {
  index: number;
  score: number;
  start: number;
  end: number;
  duration: number;
  scorer: string;
  output_file: string | null;
  downloadable: boolean;
}

export interface JobResult {
  clip_count: number;
  rendered_count: number;
  language: string;
  duration: number;
  clips: ResultClip[];
  warning?: string;
}

export interface Job {
  id: string;
  status: JobStatus;
  filename: string;
  job_dir: string;
  top_n: number;
  created_at: string;
  updated_at: string;
  input_path: string | null;
  transcript_path: string | null;
  progress: string[];
  error: string | null;
  result: JobResult | null;
}

export interface ScoreBreakdown {
  hook: number;
  clarity: number;
  emotion: number;
  pacing: number;
  payoff: number;
  weights: Record<string, number>;
}

export interface PlatformMetadata {
  title: string;
  description: string;
  hashtags: string[];
}

export interface HookVariant {
  label: string;
  text: string;
}

// Entspricht ScoredClip.to_dict() aus dem Kern.
export interface ScoredClipDict {
  start: number;
  end: number;
  duration: number;
  text: string;
  score: number;
  breakdown: ScoreBreakdown;
  reason: string;
  metadata: Record<string, PlatformMetadata>;
  hook_variants: HookVariant[];
  scorer: string;
  output_path: string | null;
}

export interface ClipsJson {
  source: string;
  scorer: string;
  disclaimer: string;
  clips: ScoredClipDict[];
}

export interface HealthResponse {
  status: string;
  service: string;
  version: string;
  ffmpeg: boolean;
  ffmpeg_error: string | null;
  jobs_dir: string;
}
