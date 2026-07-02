"use client";

// YouTube OAuth Readiness Panel (Phase 2) — prüft NUR, ob ein späterer
// Upload/OAuth möglich WÄRE. Kein echter Upload, kein OAuth-Flow, kein Token
// wird angezeigt. Nur sichtbar bei youtube_shorts-Drafts.

import { useState } from "react";
import { youtubeLogout, youtubeReadiness } from "@/lib/api";
import type { YouTubeReadiness } from "@/lib/types";

const TOKEN_STATUS_LABELS: Record<string, string> = {
  blocked: "Kein Keychain verfügbar",
  not_authenticated: "Nicht angemeldet",
  authenticated: "Angemeldet",
  invalid_token: "Token ungültig/defekt",
};

function BoolRow({ label, val }: { label: string; val: boolean }) {
  return (
    <li className={`flex items-center gap-1.5 ${val ? "text-emerald-400" : "text-neutral-400"}`}>
      <span>{val ? "✓" : "✗"}</span>
      <span className="text-neutral-400">{label}</span>
    </li>
  );
}

export default function YouTubeReadinessPanel({
  jobId,
  publishingId,
}: {
  jobId: string;
  publishingId: string;
}) {
  const [data, setData] = useState<YouTubeReadiness | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);

  async function check() {
    setBusy(true);
    setError(null);
    setNote(null);
    try {
      setData(await youtubeReadiness(jobId, publishingId));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function clearToken() {
    setBusy(true);
    setError(null);
    try {
      const res = await youtubeLogout(jobId, publishingId);
      setNote(
        res.deleted
          ? "YouTube-Token gelöscht."
          : `Kein Token gelöscht (${res.reason ?? "kein Token"}).`,
      );
      await check();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-2 rounded-lg border border-neutral-800 bg-neutral-950/40 p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-xs font-medium text-neutral-300">
          YouTube-OAuth-Readiness (Phase 2)
        </span>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => void check()}
            disabled={busy}
            className="rounded-lg border border-neutral-700 px-3 py-1.5 text-xs font-medium text-neutral-200 hover:border-neutral-500 disabled:opacity-50"
          >
            {busy ? "Prüfe…" : "YouTube-Readiness prüfen"}
          </button>
          {data && data.token_store_available && (
            <button
              type="button"
              onClick={() => void clearToken()}
              disabled={busy}
              className="rounded-lg border border-red-500/30 px-3 py-1.5 text-xs text-red-300 hover:bg-red-500/10 disabled:opacity-50"
            >
              YouTube-Token löschen
            </button>
          )}
        </div>
      </div>

      {error && (
        <p className="rounded-md border border-red-500/40 bg-red-500/10 px-2 py-1 text-xs text-red-300">
          {error}
        </p>
      )}
      {note && <p className="text-xs text-neutral-400">{note}</p>}

      {data && (
        <div className="space-y-2 text-xs">
          <p className="rounded-md border border-amber-500/40 bg-amber-500/10 px-2 py-1.5 text-amber-300">
            Echter Upload ist <strong>nicht implementiert</strong> (Status:{" "}
            {data.upload_status}). Diese Prüfung sagt nur, ob OAuth/Upload
            später möglich <em>wäre</em> — sie veröffentlicht nichts.
          </p>

          <ul className="grid gap-x-4 gap-y-0.5 sm:grid-cols-2">
            <BoolRow label="Upload-Feature aktiv" val={data.enabled} />
            <BoolRow label="OAuth-Aktionen aktiv" val={data.oauth_enabled} />
            <BoolRow label="Credentials konfiguriert" val={data.credentials_configured} />
            <BoolRow label="Credentials-Datei vorhanden" val={data.credentials_file_exists} />
            <BoolRow label="Token-Store verfügbar" val={data.token_store_available} />
            <BoolRow label="Token vorhanden" val={data.token_present} />
          </ul>

          <div className="grid gap-x-4 gap-y-1 sm:grid-cols-2">
            <div>
              <p className="text-neutral-500">Token-Status</p>
              <p className="text-neutral-200">
                {TOKEN_STATUS_LABELS[data.token_status] ?? data.token_status}
              </p>
            </div>
            <div>
              <p className="text-neutral-500">Benötigter Scope</p>
              <p className="truncate text-neutral-200">youtube.upload</p>
            </div>
            <div>
              <p className="text-neutral-500">Credentials-Datei</p>
              <p className="truncate text-neutral-200">
                {data.credentials_file_basename ?? "—"}
              </p>
            </div>
            <div>
              <p className="text-neutral-500">OAuth-Flow</p>
              <p className="text-neutral-200">{data.oauth_flow_status}</p>
            </div>
          </div>

          {data.blocked_reasons.length > 0 && (
            <div>
              <p className="mb-0.5 text-[10px] uppercase tracking-wide text-red-400">
                Blocker
              </p>
              <ul className="space-y-0.5">
                {data.blocked_reasons.map((r, i) => (
                  <li key={i} className="text-red-300">
                    ✗ {r}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {data.next_steps.length > 0 && (
            <div>
              <p className="mb-0.5 text-[10px] uppercase tracking-wide text-neutral-500">
                Nächste Schritte
              </p>
              <ul className="space-y-0.5">
                {data.next_steps.map((s, i) => (
                  <li key={i} className="text-neutral-400">
                    · {s}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
