// TypeScript-Typen, die die FastAPI-Antworten spiegeln.
// Quelle der Wahrheit bleibt das Backend (api/jobs.py, api/clipforge/models.py).
// Hier wird KEINE Logik dupliziert — nur Formen für die Anzeige.

export type JobStatus =
  | "queued"
  | "processing"
  | "completed"
  | "failed"
  | "interrupted"
  | "incomplete";

export interface JobSummary {
  id: string;
  status: JobStatus;
  filename: string;
  created_at: string;
  updated_at: string;
  clip_count: number | null;
  error: string | null;
  restored?: boolean;
  interrupted?: boolean;
  restore_warning?: string | null;
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
  input_file_exists?: boolean;
  transcript_exists?: boolean;
  clips_json_exists?: boolean;
  auto_export_count?: number;
  manual_export_count?: number;
  total_export_count?: number;
  has_manual_exports?: boolean;
  all_exports_ready?: boolean;
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
  reframe_mode?: string;
  progress: string[];
  error: string | null;
  result: JobResult | null;
  files?: JobFiles;
  restored?: boolean;
  restored_at?: string | null;
  interrupted?: boolean;
  restore_warning?: string | null;
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

export interface ReframeInfo {
  requested_mode: string;
  applied_mode: string;
  fallback: boolean;
  fallback_reason: string | null;
  detection_method: string | null;
  frames_analyzed: number;
  faces_detected_count: number;
  focus_x: number | null;
  crop_x: number | null;
  crop_strategy: string;
  smoothing_applied: boolean;
}

export interface PlatformText {
  caption: string;
  hashtags: string[];
  pinned_comment: string;
}

export interface YoutubeShortsText {
  title: string;
  description: string;
  hashtags: string[];
}

export interface ContentVariant {
  name: string;
  hook: string;
  caption: string;
  hashtags: string[];
}

export interface PlatformRecommendation {
  best_platform: string;
  reason: string;
}

export interface ContentPackage {
  primary_hook: string;
  hook_variants: Record<string, string>;
  youtube_shorts: YoutubeShortsText;
  tiktok: PlatformText;
  instagram_reels: PlatformText;
  platform_recommendation: PlatformRecommendation;
  variant_a: ContentVariant;
  variant_b: ContentVariant;
  variant_c: ContentVariant;
  safety_note: Record<string, string>;
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
  reframe_info?: ReframeInfo | null;
  content_package?: ContentPackage | null;
}

export interface ClipsJson {
  source: string;
  scorer: string;
  disclaimer: string;
  clips: ScoredClipDict[];
}

// Manueller Re-Render-Export (Web-Clip-Editor).
export interface ManualExport {
  export_id: string;
  source_clip_index: number;
  created_at: string;
  start_time: number;
  end_time: number;
  original_start_time: number | null;
  original_end_time: number | null;
  final_duration: number;
  title: string | null;
  caption_mode: string;
  caption_style: string;
  remove_silence: boolean;
  reframe_mode: string;
  score?: number;
  output_file: string;
  silence_info?: SilenceInfo | null;
  reframe_info?: ReframeInfo | null;
  caption_info?: CaptionInfo | null;
  warning?: string | null;
  available?: boolean;
  log?: string[];
}

export interface RerenderRequest {
  start_time: number;
  end_time: number;
  title?: string | null;
  caption_style?: string;
  caption_mode?: string;
  remove_silence?: boolean;
  reframe_mode?: string;
  export_name?: string | null;
}

export interface StorageJob {
  job_id: string;
  status: JobStatus;
  filename: string;
  files_count: number;
  bytes: number;
  human_size: string;
  auto_export_count: number;
  manual_export_count: number;
  restored: boolean;
  created_at: string;
  updated_at: string;
}

export interface StorageSummary {
  jobs_root: string;
  total_jobs: number;
  total_bytes: number;
  total_human: string;
  by_status: Record<string, number>;
  counts: {
    auto_exports: number;
    manual_exports: number;
    total_exports: number;
  };
  largest_jobs: StorageJob[];
  cleanup_candidates: {
    failed: string[];
    interrupted: string[];
    incomplete: string[];
    completed_without_exports: string[];
  };
}

export interface BulkDeleteResult {
  deleted_count: number;
  failed_count: number;
  removed_bytes: number;
  removed_human: string;
  results: {
    job_id: string;
    deleted: boolean;
    removed_files_count?: number;
    removed_bytes?: number;
    error?: string;
  }[];
}

export interface HealthResponse {
  status: string;
  service: string;
  version: string;
  ffmpeg: boolean;
  ffmpeg_error: string | null;
  jobs_dir: string;
}
