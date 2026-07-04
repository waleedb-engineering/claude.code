"use client";

// Privater YouTube-Testupload (Phase 3/3b) — echter, aber ausschließlich
// PRIVATER Upload, mit Retry-/Recovery-Transparenz. KEIN public/unlisted,
// KEIN Auto-Posting, KEINE Tokens im DOM. Sichtbar/aktiv nur, wenn das Backend
// can_attempt_private_upload=true meldet. Nur bei youtube_shorts-Drafts.

import { useState } from "react";
import {
  youtubeDryRun,
  youtubeOAuthStart,
  youtubePublishPrivate,
  youtubeUploadStatus,
} from "@/lib/api";
import type {
  IdempotencyState,
  YouTubeUploadReadiness,
  YouTubeUploadResult,
  YouTubeUploadStatus,
} from "@/lib/types";

const REASON_LABELS: Record<string, string> = {
  upload_disabled: "Upload-Feature ist deaktiviert (CLIPFORGE_ENABLE_YOUTUBE_UPLOAD=true)",
  oauth_not_ready: "OAuth ist nicht bereit (Flag/Client-Secrets/Token-Store)",
  token_missing: "Kein YouTube-Token vorhanden — erst verbinden",
  reauth_required: "Erneute Anmeldung nötig (kein Refresh-Token)",
  token_refresh_failed: "Token konnte nicht aufgefrischt werden",
  invalid_credentials: "Anmeldedaten ungültig — erneut verbinden",
  upload_dependency_missing: "Google-Upload-Library fehlt (google-api-python-client)",
  invalid_draft: "Draft ist nicht valide",
  mp4_missing: "MP4-Datei fehlt",
  already_uploaded: "Bereits hochgeladen",
  upload_in_progress: "Ein Upload läuft bereits",
  upload_state_uncertain: "Vorheriges Ergebnis unklar — bitte Konto prüfen",
  quota_exceeded: "YouTube-Quota erschöpft (heute nicht erneut versuchen)",
  rate_limited: "Rate-Limit erreicht — später erneut versuchen",
  permission_denied: "Zugriff verweigert (Konto/Berechtigungen prüfen)",
  upload_failed: "Upload fehlgeschlagen",
  upload_result_uncertain: "Upload-Ergebnis unklar",
};
const reasonLabel = (c: string) => REASON_LABELS[c] ?? c;

// Fehlercodes, die eine erneute YouTube-Verbindung erfordern.
const REAUTH_CODES = new Set(["token_missing", "reauth_required", "invalid_credentials"]);

export default function YouTubePrivateUploadPanel({
  jobId,
  publishingId,
}: {
  jobId: string;
  publishingId: string;
}) {
  const [readiness, setReadiness] = useState<YouTubeUploadReadiness | null>(null);
  const [uploadStatus, setUploadStatus] = useState<YouTubeUploadStatus | null>(null);
  const [result, setResult] = useState<YouTubeUploadResult | null>(null);
  const [authUrl, setAuthUrl] = useState<string | null>(null);
  const [understood, setUnderstood] = useState(false);
  const [confirmText, setConfirmText] = useState("");
  const [checking, setChecking] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function check() {
    setChecking(true);
    setError(null);
    setResult(null);
    setAuthUrl(null);
    try {
      const [dry, status] = await Promise.all([
        youtubeDryRun(jobId, publishingId),
        youtubeUploadStatus(jobId, publishingId),
      ]);
      setReadiness(dry.upload_readiness ?? null);
      setUploadStatus(status);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setChecking(false);
    }
  }

  async function upload() {
    if (uploading) return; // kein Doppelklick
    setUploading(true);
    setError(null);
    try {
      const res = await youtubePublishPrivate(jobId, publishingId);
      setResult(res);
      await check(); // Idempotenz/Status/History aktualisieren
      setUnderstood(false);
      setConfirmText("");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setUploading(false);
    }
  }

  async function reconnect() {
    setError(null);
    try {
      const res = await youtubeOAuthStart();
      setAuthUrl(res.auth_url);
      if (!res.auth_url) {
        setError(`Verbinden nicht möglich: ${res.blocked_reasons.join(", ")}`);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  const canAttempt = readiness?.can_attempt_private_upload === true;
  const idem: IdempotencyState | undefined =
    uploadStatus?.idempotency_state ?? readiness?.idempotency_state;
  const confirmOk = confirmText === "UPLOAD_PRIVATE";
  const attemptCount =
    uploadStatus?.publish_attempt_count ?? readiness?.publish_attempt_count ?? 0;

  // Reauth nötig? (aus Status oder letztem Ergebnis)
  const needsReauth =
    uploadStatus?.requires_reauth === true ||
    (result?.error_code != null && REAUTH_CODES.has(result.error_code)) ||
    (readiness?.blocked_reasons ?? []).some((r) => REAUTH_CODES.has(r));

  const progress = uploadStatus?.upload_progress;

  return (
    <div className="space-y-2 rounded-lg border border-neutral-800 bg-neutral-950/40 p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-xs font-medium text-neutral-300">
          Privater YouTube-Testupload (Phase 3)
        </span>
        <button
          type="button"
          onClick={() => void check()}
          disabled={checking || uploading}
          className="rounded-lg border border-neutral-700 px-3 py-1.5 text-xs font-medium text-neutral-200 hover:border-neutral-500 disabled:opacity-50"
        >
          {checking ? "Prüfe…" : "Upload-Bereitschaft prüfen"}
        </button>
      </div>

      {error && (
        <p className="rounded-md border border-red-500/40 bg-red-500/10 px-2 py-1 text-xs text-red-300">
          {error}
        </p>
      )}

      {/* Status-/Attempt-Übersicht */}
      {uploadStatus && (
        <p className="text-[11px] text-neutral-500">
          Zustand: <span className="text-neutral-300">{idem}</span> · Versuche:{" "}
          <span className="text-neutral-300">{attemptCount}</span>
          {uploadStatus.last_publish_error && (
            <>
              {" "}· letzter Fehler:{" "}
              <span className="text-neutral-400">
                {reasonLabel(uploadStatus.last_publish_error)}
              </span>
            </>
          )}
        </p>
      )}

      {/* Fortschritt (nur falls Backend echten Fortschritt liefert) */}
      {progress && progress.progress_percent != null && idem === "in_progress" && (
        <p className="text-[11px] text-neutral-400">
          Upload läuft … {progress.progress_percent}%
        </p>
      )}

      {/* Reauth-Hinweis */}
      {needsReauth && (
        <div className="space-y-1 rounded-md border border-sky-500/40 bg-sky-500/10 px-2 py-1.5 text-xs text-sky-200">
          <p>YouTube muss erneut verbunden werden.</p>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => void reconnect()}
              className="rounded-md border border-sky-500/40 px-2 py-1 text-[11px] hover:bg-sky-500/10"
            >
              YouTube erneut verbinden
            </button>
            <button
              type="button"
              onClick={() => void check()}
              className="rounded-md border border-neutral-700 px-2 py-1 text-[11px] text-neutral-200 hover:border-neutral-500"
            >
              Readiness neu laden
            </button>
          </div>
          {authUrl && (
            <div className="flex items-center gap-2">
              <input
                readOnly
                value={authUrl}
                onFocus={(e) => e.currentTarget.select()}
                className="min-w-0 flex-1 rounded-md border border-neutral-700 bg-neutral-950 px-2 py-1 font-mono text-[11px] text-neutral-300"
              />
            </div>
          )}
          <p className="text-[10px] text-sky-300/80">
            Öffne die URL manuell — es wird kein Browser automatisch geöffnet,
            kein Token im Browser angezeigt.
          </p>
        </div>
      )}

      {readiness && !canAttempt && !needsReauth && (
        <div className="space-y-1 text-xs">
          <p className="text-neutral-400">
            Privater Upload aktuell <strong>nicht möglich</strong>. Blocker:
          </p>
          <ul className="space-y-0.5">
            {readiness.blocked_reasons.map((r, i) => (
              <li key={i} className="text-red-300">
                ✗ {reasonLabel(r)}
              </li>
            ))}
          </ul>
        </div>
      )}

      {readiness && canAttempt && (
        <div className="space-y-2 text-xs">
          <div className="rounded-md border border-amber-500/40 bg-amber-500/10 px-2 py-1.5 text-amber-200">
            <ul className="space-y-0.5">
              <li>• Das Video bleibt <strong>PRIVATE</strong> (nur du siehst es).</li>
              <li>• Dies ist ein <strong>echter</strong> Upload auf dein YouTube-Konto.</li>
              <li>• <strong>Kein</strong> automatisches öffentliches Posten.</li>
              <li>• Es wird das bei OAuth verbundene Google-Konto verwendet.</li>
            </ul>
          </div>

          <label className="flex items-start gap-2 text-neutral-300">
            <input
              type="checkbox"
              checked={understood}
              onChange={(e) => setUnderstood(e.target.checked)}
              className="mt-0.5"
            />
            <span>
              Ich verstehe, dass das Video real auf mein YouTube-Konto
              hochgeladen wird und privat bleibt.
            </span>
          </label>

          <div className="flex flex-col gap-1">
            <span className="text-neutral-500">
              Zur Bestätigung tippe <code className="text-neutral-300">UPLOAD_PRIVATE</code>:
            </span>
            <input
              value={confirmText}
              onChange={(e) => setConfirmText(e.target.value)}
              placeholder="UPLOAD_PRIVATE"
              className="rounded-md border border-neutral-700 bg-neutral-900 px-2 py-1 font-mono text-neutral-200"
            />
          </div>

          <button
            type="button"
            onClick={() => void upload()}
            disabled={!understood || !confirmOk || uploading}
            className="rounded-lg border border-red-500/40 bg-red-500/10 px-3 py-1.5 text-xs font-medium text-red-200 hover:bg-red-500/20 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {uploading
              ? "Lädt hoch…"
              : idem === "failed"
                ? "Erneut privat hochladen"
                : "Privat zu YouTube hochladen"}
          </button>
        </div>
      )}

      {/* Ergebnis eines echten Uploadversuchs */}
      {result && result.success && (
        <div className="space-y-1 rounded-md border border-emerald-500/40 bg-emerald-500/10 px-2 py-1.5 text-xs text-emerald-200">
          <p>
            ✓ Status: <strong>{result.status}</strong> (privat). Das Video ist
            <strong> nicht öffentlich</strong>.
          </p>
          {result.external_post_id && (
            <p className="text-neutral-300">
              Video-ID:{" "}
              <code className="text-neutral-200">{result.external_post_id}</code>{" "}
              —{" "}
              <a
                href={`https://www.youtube.com/watch?v=${encodeURIComponent(result.external_post_id)}`}
                target="_blank"
                rel="noopener noreferrer"
                className="underline hover:text-emerald-100"
              >
                im YouTube Studio öffnen
              </a>{" "}
              (nur für dich sichtbar).
            </p>
          )}
        </div>
      )}

      {result && !result.success && idem === "uncertain" && (
        <p className="rounded-md border border-orange-500/50 bg-orange-500/10 px-2 py-1.5 text-xs text-orange-200">
          ⚠ Upload-Ergebnis <strong>unklar</strong>. Bitte prüfe zuerst dein
          <strong> YouTube Studio</strong>, ob bereits ein Video existiert, bevor
          du erneut hochlädst. Ein automatischer Retry ist blockiert.
        </p>
      )}

      {result && !result.success && idem !== "uncertain" && !needsReauth &&
        result.error_code && (
          <div className="space-y-1 rounded-md border border-red-500/40 bg-red-500/10 px-2 py-1.5 text-xs text-red-300">
            <p>✗ {reasonLabel(result.error_code)}.</p>
            {uploadStatus?.can_retry && (
              <p className="text-neutral-400">
                Du kannst es nach Behebung erneut versuchen.
              </p>
            )}
          </div>
        )}
    </div>
  );
}
