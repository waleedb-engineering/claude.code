// TypeScript-Typen, die die FastAPI-Antworten spiegeln.
// Quelle der Wahrheit bleibt das Backend (api/jobs.py, api/clipforge/models.py).
// Hier wird KEINE Logik dupliziert — nur Formen für die Anzeige.

export type JobStatus =
  | "queued"
  | "processing"
  | "completed"
  | "failed"
  | "interrupted"
  | "incomplete"
  | "canceled";

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
  cancel_requested?: boolean;
  canceled_at?: string | null;
}

export interface ClipForgeConfig {
  max_upload_mb: number;
  max_batch_files: number;
  max_workers: number;
  supported_video_types: string[];
  analyzer_version?: string;
  llm_analysis_available?: boolean;
  default_analyzer_mode?: string;
  advanced_analysis_enabled?: boolean;
}

export interface CaptionStyleInfo {
  style_id: string;
  name: string;
  description: string;
  recommended_for: string;
  preview_label: string;
}

export interface BrandKit {
  brand_name: string;
  primary_color: string;
  secondary_color: string;
  font_family: string | null;
  caption_style_default: string;
  highlight_keywords: string[];
  watermark_text: string;
  watermark_enabled: boolean;
  _exists?: boolean;
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
  cancel_requested?: boolean;
  canceled_at?: string | null;
  cancel_reason?: string | null;
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
  // Analyzer v2 (optional — alte Clips haben diese Felder nicht)
  analyzer_version?: string | null;
  analyzer_mode?: string | null;
  performance_score?: number | null;
  score_breakdown?: Record<string, number> | null;
  score_reason?: string | null;
  improvement_suggestions?: string[];
  risk_flags?: string[];
  best_platform?: string | null;
  platform_reason?: string | null;
  hook_type?: string | null;
  clip_type?: string | null;
  language?: string | null;
  duplicate_group?: number | null;
  transcript_excerpt?: string | null;
}

export interface ClipsJson {
  source: string;
  scorer: string;
  disclaimer: string;
  analyzer_version?: string | null;
  analyzer_mode?: string | null;
  candidate_count?: number | null;
  deduplicated_count?: number | null;
  filled_up?: number | null;
  llm_latency_ms?: number | null;
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
  brand_kit_used?: boolean;
  brand_kit_name?: string | null;
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

export interface BatchUploadRow {
  filename: string;
  accepted: boolean;
  job_id: string | null;
  error: string | null;
}

export interface BatchUploadResult {
  accepted_count: number;
  rejected_count: number;
  results: BatchUploadRow[];
}

export interface HealthResponse {
  status: string;
  service: string;
  version: string;
  ffmpeg: boolean;
  ffmpeg_error: string | null;
  jobs_dir: string;
}

// --- Publishing Planner (lokale Drafts — kein echter Upload) ---------------

export type PublishingPlatform = "youtube_shorts" | "tiktok" | "instagram_reels";

export type PublishingStatus =
  | "draft"
  | "ready"
  | "scheduled"
  | "publishing"
  | "published"
  | "failed"
  | "canceled";

export interface PublishingChecklist {
  mp4_exists: boolean;
  format_9_16: boolean | null;
  title_present: boolean;
  caption_present: boolean;
  hashtags_present: boolean;
  platform_selected: boolean;
  no_viral_guarantee: boolean;
  safe_status: boolean;
}

export type PublishingQualityHint =
  | "title_too_long"
  | "caption_too_long"
  | "too_many_hashtags"
  | "missing_pinned_comment"
  | "scheduled_in_past"
  | "weak_metadata";

export interface PublishingValidationSummary {
  is_valid: boolean;
  blocking_issues_count: number;
  blocking_issues: string[];
  warnings_count: number;
  checklist: PublishingChecklist;
  quality_hints: PublishingQualityHint[];
}

export interface PublishingValidation {
  passed: boolean;
  checks: {
    mp4_exists: boolean;
    format_9_16: boolean | null;
    file_size_bytes: number;
    platform_valid: boolean;
    title_present: boolean;
    caption_present: boolean;
    description_present: boolean;
    hashtags_present: boolean;
    no_virality_claim: boolean;
    required_text_present: boolean;
  };
  checked_at: string;
  summary?: PublishingValidationSummary;
}

export interface PublishingDraft {
  publishing_id: string;
  job_id: string;
  source_type: "auto_clip" | "manual_export";
  source_clip_index: number | null;
  manual_export_id: string | null;
  mp4_path: string;
  platform: PublishingPlatform;
  title: string;
  caption: string;
  description: string;
  hashtags: string[];
  pinned_comment: string;
  scheduled_at: string | null;
  status: PublishingStatus;
  validation: PublishingValidation | null;
  created_at: string;
  updated_at: string;
  published_at: string | null;
  external_post_id: string | null;
  error: string | null;
  duplicated_from?: string | null;
  warning?: string | null;
}

// Kompakte Zeile für die globale Übersicht (GET /api/publishing).
export interface PublishingDraftRow {
  publishing_id: string;
  job_id: string;
  job_filename: string;
  source_type: "auto_clip" | "manual_export";
  source_clip_index: number | null;
  manual_export_id: string | null;
  platform: PublishingPlatform;
  title: string;
  caption: string;
  hashtags: string[];
  status: PublishingStatus;
  scheduled_at: string | null;
  validation_summary: PublishingValidationSummary;
  mp4_exists: boolean;
  created_at: string;
  updated_at: string;
  source_preview_url: string | null;
  pack_url: string;
  job_url: string;
  planner_url: string;
}

export interface PublishingOverview {
  total_drafts: number;
  by_status: Record<string, number>;
  by_platform: Record<string, number>;
  scheduled_count: number;
  ready_count: number;
  invalid_count: number;
  drafts: PublishingDraftRow[];
  warnings: string[];
}

// --- YouTube Dry-Run (Phase 1 — kein echter Upload) ------------------------

export interface YouTubeDryRunChecks {
  mp4_exists: boolean;
  format_9_16: boolean | null;
  title_present: boolean;
  description_present: boolean;
  no_viral_guarantee: boolean;
  upload_feature_enabled: boolean;
  credentials_configured: boolean;
}

export interface YouTubeDryRun {
  platform: "youtube_shorts";
  enabled: boolean;
  would_upload: boolean;
  video_file: string | null;
  title: string;
  description: string;
  hashtags: string[];
  privacy_status: string;
  scheduled_at: string | null;
  checks: YouTubeDryRunChecks;
  warnings: string[];
  blocked_reasons: string[];
  request_preview: {
    endpoint: string;
    metadata: unknown;
    video_body: string;
    note: string;
  };
  upload_implemented: boolean;
}

// --- YouTube OAuth Readiness (Phase 2 — kein echter Upload) ----------------

export type YouTubeTokenStatus =
  | "blocked"
  | "not_authenticated"
  | "authenticated"
  | "invalid_token";

export interface YouTubeReadiness {
  platform: "youtube_shorts";
  enabled: boolean;
  oauth_enabled: boolean;
  credentials_configured: boolean;
  credentials_file_exists: boolean;
  credentials_file_basename: string | null;
  token_store_available: boolean;
  token_present: boolean;
  token_status: YouTubeTokenStatus;
  required_scope: string;
  redirect_uri: string;
  can_attempt_oauth: boolean;
  can_start_auth: boolean;
  can_attempt_upload: boolean;
  blocked_reasons: string[];
  warnings: string[];
  next_steps: string[];
  upload_status: "not_implemented";
  oauth_flow_status: string;
}

export interface YouTubeLogoutResult {
  deleted: boolean;
  reason?: string;
}

// --- YouTube OAuth-Flow-Skelett (Phase 2b — kein echter Upload) ------------

// Globaler OAuth-Status (nicht draft-gebunden). Enthält NIE Token/Secrets.
export interface YouTubeOAuthStatus {
  oauth_enabled: boolean;
  client_secrets_configured: boolean;
  client_secrets_basename: string | null;
  redirect_uri: string;
  scopes: string[];
  required_scope: string;
  state_ttl_seconds: number;
  token_store_available: boolean;
  token_present: boolean;
  token_status: YouTubeTokenStatus;
  can_start_auth: boolean;
  can_attempt_upload: boolean;
  blocked_reasons: string[];
  warnings: string[];
  no_secrets: boolean;
}

export interface YouTubeOAuthStart {
  enabled: boolean;
  state_created: boolean;
  auth_url: string | null;
  expires_at: number | null;
  blocked_reasons: string[];
  warnings: string[];
  message: string;
  no_secrets: boolean;
}
