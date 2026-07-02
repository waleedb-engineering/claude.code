"use client";

// YouTube Dry-Run Panel — zeigt, was hochgeladen WÜRDE. Kein echter Upload,
// kein OAuth, keine Tokens. Nur sichtbar bei YouTube-Shorts-Drafts.

import { useState } from "react";
import { youtubeDryRun } from "@/lib/api";
import type { YouTubeDryRun } from "@/lib/types";

const CHECK_LABELS: [keyof YouTubeDryRun["checks"], string][] = [
  ["mp4_exists", "MP4 vorhanden"],
  ["format_9_16", "9:16-Format"],
  ["title_present", "Titel vorhanden"],
  ["description_present", "Beschreibung vorhanden"],
  ["no_viral_guarantee", "Keine Viralitätsgarantie"],
  ["upload_feature_enabled", "Upload-Feature aktiv"],
  ["credentials_configured", "Credentials konfiguriert"],
];

function CheckRow({ label, val }: { label: string; val: boolean | null }) {
  const icon = val === true ? "✓" : val === false ? "✗" : "•";
  const color =
    val === true
      ? "text-emerald-400"
      : val === false
        ? "text-red-400"
        : "text-neutral-500";
  return (
    <li className={`flex items-center gap-1.5 ${color}`}>
      <span>{icon}</span>
      <span className="text-neutral-400">{label}</span>
      {val === null && <span className="text-neutral-600">(nicht prüfbar)</span>}
    </li>
  );
}

export default function YouTubeDryRunPanel({
  jobId,
  publishingId,
}: {
  jobId: string;
  publishingId: string;
}) {
  const [result, setResult] = useState<YouTubeDryRun | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run() {
    setBusy(true);
    setError(null);
    try {
      setResult(await youtubeDryRun(jobId, publishingId));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-2 rounded-lg border border-neutral-800 bg-neutral-950/40 p-3">
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs font-medium text-neutral-300">
          YouTube-Upload (Vorschau)
        </span>
        <button
          type="button"
          onClick={() => void run()}
          disabled={busy}
          className="rounded-lg border border-red-500/40 bg-red-500/10 px-3 py-1.5 text-xs font-medium text-red-200 hover:bg-red-500/20 disabled:opacity-50"
        >
          {busy ? "Prüfe…" : "YouTube Dry-Run prüfen"}
        </button>
      </div>

      {error && (
        <p className="rounded-md border border-red-500/40 bg-red-500/10 px-2 py-1 text-xs text-red-300">
          {error}
        </p>
      )}

      {result && (
        <div className="space-y-2 text-xs">
          {/* Feature-Flag-Status: immer klar sichtbar */}
          {!result.enabled ? (
            <p className="rounded-md border border-amber-500/40 bg-amber-500/10 px-2 py-1.5 text-amber-300">
              🔒 Echter YouTube Upload ist deaktiviert. Dry-Run only.
            </p>
          ) : (
            <p className="rounded-md border border-emerald-500/40 bg-emerald-500/10 px-2 py-1.5 text-emerald-300">
              Upload-Feature ist aktiv — echte Uploads erfordern trotzdem
              Credentials und eine explizite Bestätigung.
            </p>
          )}

          <div className="grid gap-x-4 gap-y-1 sm:grid-cols-2">
            <div>
              <p className="text-neutral-500">Würde hochladen</p>
              <p className={result.would_upload ? "text-emerald-400" : "text-neutral-300"}>
                {result.would_upload ? "ja (Vorbedingungen erfüllt)" : "nein"}
              </p>
            </div>
            <div>
              <p className="text-neutral-500">Privacy-Status</p>
              <p className="text-neutral-200">{result.privacy_status}</p>
            </div>
            <div>
              <p className="text-neutral-500">Video-Datei</p>
              <p className="truncate text-neutral-200">
                {result.video_file ?? "—"}
              </p>
            </div>
            <div>
              <p className="text-neutral-500">Geplant</p>
              <p className="text-neutral-200">{result.scheduled_at ?? "—"}</p>
            </div>
          </div>

          <div>
            <p className="mb-0.5 text-[10px] uppercase tracking-wide text-neutral-500">
              Checks
            </p>
            <ul className="grid gap-x-4 gap-y-0.5 sm:grid-cols-2">
              {CHECK_LABELS.map(([key, label]) => (
                <CheckRow key={key} label={label} val={result.checks[key]} />
              ))}
            </ul>
          </div>

          {result.blocked_reasons.length > 0 && (
            <div>
              <p className="mb-0.5 text-[10px] uppercase tracking-wide text-red-400">
                Blockiert
              </p>
              <ul className="space-y-0.5">
                {result.blocked_reasons.map((r, i) => (
                  <li key={i} className="text-red-300">
                    ✗ {r}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {result.warnings.length > 0 && (
            <div>
              <p className="mb-0.5 text-[10px] uppercase tracking-wide text-amber-400">
                Hinweise
              </p>
              <ul className="space-y-0.5">
                {result.warnings.map((w, i) => (
                  <li key={i} className="text-amber-300">
                    ⚠ {w}
                  </li>
                ))}
              </ul>
            </div>
          )}

          <details className="rounded-md border border-neutral-800 bg-neutral-900/40">
            <summary className="cursor-pointer px-2 py-1 text-neutral-400">
              Request-Vorschau (Metadaten, kein Token, kein Video-Body)
            </summary>
            <pre className="overflow-x-auto px-2 pb-2 text-[10px] text-neutral-400">
              {JSON.stringify(result.request_preview, null, 2)}
            </pre>
          </details>

          {/* KEIN "Live veröffentlichen"-Button: Upload ist Phase 1 = Dry-Run.
              Auch bei enabled=true bleibt hier bewusst nur der Hinweis. */}
          <p className="text-[11px] text-neutral-600">
            Echter Upload ist noch nicht implementiert (Phase 1: Dry-Run). Es
            wird garantiert nichts hochgeladen.
          </p>
        </div>
      )}
    </div>
  );
}
