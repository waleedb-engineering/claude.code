"use client";

// YouTube OAuth Readiness + Flow (Phase 3-Vorbereitung). Prüft, OB ein späterer
// Upload/OAuth möglich WÄRE, bereitet eine sichere Consent-URL vor und stößt den
// ECHTEN Token-Exchange (offizielle Google-Library) über den Callback an.
// KEIN echter Upload, KEIN Token wird angezeigt (auch nicht im DOM). Nur bei
// youtube_shorts-Drafts.

import { useState } from "react";
import {
  youtubeLogout,
  youtubeOAuthStart,
  youtubeOAuthStatus,
  youtubeReadiness,
} from "@/lib/api";
import type {
  YouTubeOAuthStart,
  YouTubeOAuthStatus,
  YouTubeReadiness,
} from "@/lib/types";

const TOKEN_STATUS_LABELS: Record<string, string> = {
  blocked: "Kein Keychain verfügbar",
  not_authenticated: "Nicht angemeldet",
  authenticated: "Angemeldet",
  invalid_token: "Token ungültig/defekt",
};

// Sichere, verständliche Labels für Blocker/Fehler-Codes (kein Secret, kein
// Rohtext). Deckt Voraussetzungen UND Callback-Fehler ab.
const REASON_LABELS: Record<string, string> = {
  oauth_disabled: "OAuth ist deaktiviert (CLIPFORGE_ENABLE_YOUTUBE_OAUTH=true setzen)",
  client_secrets_missing: "Client-Secrets-Datei fehlt",
  client_secrets_unreadable: "Client-Secrets-Datei ist unlesbar/unvollständig",
  token_store_unavailable: "Kein sicherer Token-Store (keyring) verfügbar",
  exchange_dependency_missing: "Google-Auth-Library fehlt (google-auth-oauthlib)",
  exchange_failed: "Token-Austausch mit Google fehlgeschlagen",
  invalid_scope: "Erteilter Scope deckt keinen YouTube-Upload ab",
  invalid_token_payload: "Token-Antwort ungültig",
};

function reasonLabel(code: string): string {
  return REASON_LABELS[code] ?? code;
}

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
  const [oauth, setOauth] = useState<YouTubeOAuthStatus | null>(null);
  const [start, setStart] = useState<YouTubeOAuthStart | null>(null);
  const [copied, setCopied] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);

  async function check() {
    setBusy(true);
    setError(null);
    setNote(null);
    setStart(null);
    try {
      // Draft-Readiness + globaler OAuth-Status (nutzt dieselbe Quelle).
      const [rd, st] = await Promise.all([
        youtubeReadiness(jobId, publishingId),
        youtubeOAuthStatus(),
      ]);
      setData(rd);
      setOauth(st);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function prepareConnect() {
    setBusy(true);
    setError(null);
    setNote(null);
    setCopied(false);
    try {
      const res = await youtubeOAuthStart();
      setStart(res);
      if (!res.auth_url && res.blocked_reasons.length > 0) {
        setNote(`Nicht möglich: ${res.blocked_reasons.join(", ")}`);
      }
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

  async function copyAuthUrl() {
    if (!start?.auth_url) return;
    try {
      await navigator.clipboard.writeText(start.auth_url);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  }

  const canStart = oauth?.can_start_auth === true;

  return (
    <div className="space-y-2 rounded-lg border border-neutral-800 bg-neutral-950/40 p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-xs font-medium text-neutral-300">
          YouTube-OAuth-Readiness &amp; Verbindung vorbereiten (Phase 2b)
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
            <BoolRow label="Client Secrets konfiguriert" val={data.credentials_configured} />
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
                    ✗ {reasonLabel(r)}
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

          {/* OAuth-Verbindung vorbereiten — nur wenn alle Voraussetzungen stehen. */}
          <div className="space-y-2 rounded-md border border-neutral-800 bg-neutral-900/40 p-2">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="text-[11px] font-medium text-neutral-300">
                YouTube verbinden (Consent-URL vorbereiten)
              </span>
              <button
                type="button"
                onClick={() => void prepareConnect()}
                disabled={busy || !canStart}
                title={
                  canStart
                    ? "Erzeugt eine sichere Consent-URL (kein Browser wird geöffnet)."
                    : "Voraussetzungen fehlen (OAuth aktiv + Client Secrets + Token-Store)."
                }
                className="rounded-lg border border-emerald-500/30 px-3 py-1.5 text-[11px] font-medium text-emerald-300 hover:bg-emerald-500/10 disabled:cursor-not-allowed disabled:opacity-40"
              >
                YouTube verbinden vorbereiten
              </button>
            </div>

            {!canStart && (
              <p className="text-[11px] text-neutral-500">
                Button ist deaktiviert, bis OAuth aktiv, Client Secrets
                konfiguriert und der Token-Store verfügbar sind.
                {oauth && oauth.blocked_reasons.length > 0 && (
                  <> Blocker: {oauth.blocked_reasons.map(reasonLabel).join(", ")}.</>
                )}
              </p>
            )}

            {start?.auth_url && (
              <div className="space-y-1">
                <p className="text-[11px] text-neutral-400">
                  Öffne diese URL <strong>manuell</strong> im Browser und melde
                  dich bei Google an. Nach der Freigabe leitet Google{" "}
                  <strong>automatisch</strong> auf den Callback zurück, der den
                  Code sicher gegen ein Token tauscht und es nur im Keychain
                  speichert. Es wird <strong>kein</strong> Browser automatisch
                  geöffnet und <strong>kein</strong> Token hier angezeigt.
                </p>
                <div className="flex items-center gap-2">
                  <input
                    readOnly
                    value={start.auth_url}
                    onFocus={(e) => e.currentTarget.select()}
                    className="min-w-0 flex-1 rounded-md border border-neutral-700 bg-neutral-950 px-2 py-1 font-mono text-[11px] text-neutral-300"
                  />
                  <button
                    type="button"
                    onClick={() => void copyAuthUrl()}
                    className="shrink-0 rounded-md border border-neutral-700 px-2 py-1 text-[11px] text-neutral-200 hover:border-neutral-500"
                  >
                    {copied ? "Kopiert ✓" : "Kopieren"}
                  </button>
                </div>
                {start.expires_at && (
                  <p className="text-[10px] text-neutral-500">
                    Der Link/State läuft ab (einmalig verwendbar,
                    CSRF-geschützt).
                  </p>
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
