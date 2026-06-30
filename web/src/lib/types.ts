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

export interface JobFiles {
  clip_count: number;
  mp4_count: number;
  has_transcript: boolean;
  has_clips_json: boolean;
  exports_ready: boolean;
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
  remove_silence?: boolean;
  caption_mode?: string;
  caption_style?: string;
  progress: string[];
  error: string | null;
  result: JobResult | null;
  files?: JobFiles;
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

export interface SilenceInfo {
  remove_silence: boolean;
  n_silences: number;
  removed_seconds: number;
  original_duration: number;
  final_duration: number;
  applied: boolean;
  audio_smoothing: boolean;
  fallback: boolean;
}

export interface CaptionInfo {
  requested_mode: string;
  applied_mode: string;
  caption_style: string;
  word_level_available: boolean;
  fallback: boolean;
  fallback_reason: string | null;
  caption_blocks_count: number;
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
  silence_info?: SilenceInfo | null;
  caption_info?: CaptionInfo | null;
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
