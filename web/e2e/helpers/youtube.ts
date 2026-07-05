import { expect, type Page } from "@playwright/test";

// ---------------------------------------------------------------------------
// YouTube-Mocks & DOM-Secret-Scan.
//
// Für Zustände, die das echte Backend ohne echten Upload/Token nicht erzeugen
// kann (uncertain/recovery, reauth), fangen wir NUR die /youtube/*-Endpoints per
// page.route ab. Es werden NIEMALS echte Google-Calls ausgelöst und in keiner
// Mock-Antwort stehen Tokens/Secrets.
// ---------------------------------------------------------------------------

// Verbotene Secret-Marker im DOM. Ziel sind Secret-WERTE, nicht harmlose
// UI-Begriffe: „Token“ (deutsch), das Label „Client Secrets“ oder der
// Standard-Dateiname „client_secrets.json“ (Googles OAuth-Client-Konfig) sind
// KEINE Secrets. Deshalb werden die Token-Schlüssel nur in Wert-tragender Form
// (Key:Value) sowie über bekannte Google-Token-Präfixe erkannt.
const SECRET_PATTERNS: RegExp[] = [
  // Token-/Secret-Schlüssel mit einem tatsächlichen Wert dahinter.
  /\b(access_token|refresh_token|id_token|client_secret)\b["']?\s*[:=]\s*["']?[A-Za-z0-9._\-/+]{6,}/i,
  // Bekannte Google-Wertformate.
  /GOCSPX-[A-Za-z0-9_-]{6,}/, // Client-Secret-Wert
  /ya29\.[A-Za-z0-9._-]{10,}/, // Access-Token
  /1\/\/[0-9A-Za-z._-]{20,}/, // Refresh-Token
  // Authorization-Header mit echtem Schema/Wert.
  /\bBearer\s+[A-Za-z0-9._-]{10,}/,
  /"?Authorization"?\s*[:=]\s*["']?(Bearer|Basic)\b/i,
];

/**
 * Scannt das gerenderte DOM (inkl. Input-Werte) auf Secret-WERTE. Der bekannte,
 * ungefährliche Dateiname „client_secrets.json“ wird vorab entfernt, damit er
 * nicht fälschlich als Leak gewertet wird.
 */
export async function expectNoSecretsInDom(page: Page): Promise<void> {
  const raw = await page.evaluate(() => {
    const inputs = Array.from(document.querySelectorAll("input, textarea"))
      .map((el) => (el as HTMLInputElement).value)
      .join("\n");
    return `${document.documentElement.outerHTML}\n${inputs}`;
  });
  const haystack = raw.replace(/client_secrets?\.json/gi, "");
  for (const re of SECRET_PATTERNS) {
    expect(
      re.test(haystack),
      `Secret-Marker ${re} wurde im DOM gefunden`,
    ).toBe(false);
  }
}

type Json = Record<string, unknown>;

async function fulfill(route: import("@playwright/test").Route, body: Json) {
  await route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify(body),
  });
}

// --- Bausteine (alle no_secrets:true, keine Tokens) ------------------------

export function dryRunDisabled(): Json {
  return {
    platform: "youtube_shorts",
    enabled: false,
    would_upload: false,
    video_file: "clip.mp4",
    title: "E2E",
    description: "",
    hashtags: [],
    privacy_status: "private",
    scheduled_at: null,
    checks: {
      mp4_exists: true,
      format_9_16: true,
      title_present: true,
      description_present: false,
      no_viral_guarantee: true,
      upload_feature_enabled: false,
      credentials_configured: false,
    },
    warnings: [],
    blocked_reasons: ["upload_disabled"],
    request_preview: { endpoint: "videos.insert", metadata: {}, video_body: "<omitted>", note: "no token" },
    upload_implemented: true,
    upload_readiness: uploadReadinessBlocked(),
  };
}

export function uploadReadinessBlocked(): Json {
  return {
    upload_feature_enabled: false,
    oauth_ready: false,
    token_present: false,
    token_refresh_possible: false,
    draft_valid: true,
    mp4_exists: true,
    idempotency_state: "uncertain",
    already_uploaded: false,
    publish_attempt_count: 1,
    can_attempt_private_upload: false,
    privacy_status: "private",
    blocked_reasons: ["upload_disabled"],
    warnings: [],
    no_secrets: true,
  };
}

function baseStatus(overrides: Json): Json {
  return {
    status: "uncertain",
    state: "uncertain",
    idempotency_state: "uncertain",
    is_stale: false,
    publish_attempt_count: 1,
    current_attempt: null,
    retry_count: 0,
    last_publish_error: "upload_result_uncertain",
    last_error_category: "uncertain",
    external_post_id_present: false,
    can_retry: false,
    can_reconcile: false,
    requires_manual_check: false,
    requires_reauth: false,
    last_activity_at: "2026-07-05T10:00:00Z",
    reconciliation_status: null,
    reconciliation_checked_at: null,
    upload_progress: null,
    attempt_history_summary: [],
    transition_history_summary: [],
    no_secrets: true,
    ...overrides,
  };
}

export function uncertainStatus(): Json {
  return baseStatus({
    state: "uncertain",
    idempotency_state: "uncertain",
    requires_manual_check: true,
    can_reconcile: true,
  });
}

export function reconcilingStatus(): Json {
  return baseStatus({
    status: "reconciling",
    state: "reconciling",
    idempotency_state: "in_progress",
    last_publish_error: null,
    can_reconcile: true,
    reconciliation_status: "pending",
  });
}

export function publishedStatus(): Json {
  return baseStatus({
    status: "published",
    state: "published",
    idempotency_state: "succeeded",
    last_publish_error: null,
    external_post_id_present: true,
    can_reconcile: false,
    reconciliation_status: "confirmed_present",
  });
}

export function reauthStatus(): Json {
  return baseStatus({
    status: "reauth_required",
    state: "reauth_required",
    idempotency_state: "failed",
    last_publish_error: "reauth_required",
    last_error_category: "auth",
    requires_reauth: true,
    can_retry: false,
  });
}

export function readinessWithTokenStore(overrides: Json = {}): Json {
  return {
    platform: "youtube_shorts",
    enabled: false,
    oauth_enabled: true,
    credentials_configured: true,
    credentials_file_exists: true,
    credentials_file_basename: "client_secrets.json",
    token_store_available: true,
    token_present: true,
    token_status: "invalid_token",
    required_scope: "youtube.upload",
    redirect_uri: "http://127.0.0.1:8000/api/youtube/oauth/callback",
    can_attempt_oauth: true,
    can_start_auth: true,
    can_attempt_upload: false,
    blocked_reasons: ["reauth_required"],
    warnings: [],
    next_steps: ["YouTube erneut verbinden"],
    upload_status: "not_implemented",
    oauth_flow_status: "reauth_required",
    ...overrides,
  };
}

export function oauthStatusReady(): Json {
  return {
    oauth_enabled: true,
    client_secrets_configured: true,
    client_secrets_basename: "client_secrets.json",
    redirect_uri: "http://127.0.0.1:8000/api/youtube/oauth/callback",
    scopes: ["https://www.googleapis.com/auth/youtube.upload"],
    required_scope: "youtube.upload",
    state_ttl_seconds: 600,
    token_store_available: true,
    token_present: true,
    token_status: "invalid_token",
    can_start_auth: true,
    can_attempt_upload: false,
    blocked_reasons: [],
    warnings: [],
    no_secrets: true,
  };
}

export function oauthStartUrl(): Json {
  return {
    enabled: true,
    state_created: true,
    // Consent-URL ohne Token/Secret — nur client_id + Redirect (öffentlich).
    auth_url:
      "https://accounts.google.com/o/oauth2/v2/auth?response_type=code&scope=youtube.upload&state=e2e-csrf",
    expires_at: 4102444800,
    blocked_reasons: [],
    warnings: [],
    message: "Consent-URL vorbereitet.",
    no_secrets: true,
  };
}

export interface YouTubeMockConfig {
  dryRun?: Json;
  readiness?: Json;
  oauthStatus?: Json;
  oauthStart?: Json;
  logout?: Json;
  /** Ein oder mehrere upload-status-Antworten (nacheinander pro Aufruf). */
  uploadStatus?: Json | Json[];
  /** Antworten auf POST /youtube/reconcile (nacheinander pro Aufruf). */
  reconcile?: Json | Json[];
}

/** Installiert Route-Mocks NUR für /youtube/*. Alles andere geht echt zum Backend. */
export async function installYouTubeMocks(
  page: Page,
  cfg: YouTubeMockConfig,
): Promise<void> {
  const seq = (v: Json | Json[] | undefined) => {
    if (v === undefined) return undefined;
    const arr = Array.isArray(v) ? [...v] : [v];
    return () => (arr.length > 1 ? arr.shift()! : arr[0]);
  };
  const nextStatus = seq(cfg.uploadStatus);
  const nextReconcile = seq(cfg.reconcile);

  if (cfg.dryRun) {
    await page.route("**/youtube/dry-run", (r) => fulfill(r, cfg.dryRun!));
  }
  if (cfg.readiness) {
    await page.route("**/youtube/readiness", (r) => fulfill(r, cfg.readiness!));
  }
  if (cfg.oauthStatus) {
    await page.route("**/youtube/oauth/status", (r) =>
      fulfill(r, cfg.oauthStatus!),
    );
  }
  if (cfg.oauthStart) {
    await page.route("**/youtube/oauth/start", (r) =>
      fulfill(r, cfg.oauthStart!),
    );
  }
  if (cfg.logout) {
    await page.route("**/youtube/auth/logout", (r) => fulfill(r, cfg.logout!));
  }
  if (nextStatus) {
    await page.route("**/youtube/upload-status", (r) => fulfill(r, nextStatus()));
  }
  if (nextReconcile) {
    await page.route("**/youtube/reconcile", (r) => fulfill(r, nextReconcile()));
  }
}
