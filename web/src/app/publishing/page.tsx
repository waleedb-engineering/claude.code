"use client";

// Globale Publishing-Übersicht — alle lokalen Drafts über alle Jobs.
// Kein echter Upload, kein Plattform-Login. Nur lokale Planung + Pack-Export.

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { API_BASE, getPublishingOverview } from "@/lib/api";
import DuplicateDraftButton from "@/components/DuplicateDraftButton";
import type {
  PublishingDraftRow,
  PublishingOverview,
  PublishingPlatform,
} from "@/lib/types";

const PLATFORM_LABELS: Record<PublishingPlatform, string> = {
  youtube_shorts: "YouTube Shorts",
  tiktok: "TikTok",
  instagram_reels: "Instagram Reels",
};

const STATUS_LABELS: Record<string, string> = {
  draft: "Entwurf",
  ready: "Bereit",
  scheduled: "Geplant",
  publishing: "Wird veröffentlicht",
  published: "Veröffentlicht",
  failed: "Fehlgeschlagen",
  canceled: "Abgebrochen",
};

const STATUS_COLORS: Record<string, string> = {
  draft: "bg-neutral-700/40 text-neutral-300",
  ready: "bg-emerald-500/15 text-emerald-300",
  scheduled: "bg-indigo-500/15 text-indigo-300",
  published: "bg-emerald-500/15 text-emerald-300",
  failed: "bg-red-500/15 text-red-300",
  canceled: "bg-neutral-700/40 text-neutral-500",
};

function SummaryCard({ label, value, tone }: { label: string; value: number; tone?: string }) {
  return (
    <div className="rounded-xl border border-neutral-800 bg-neutral-900/50 px-4 py-3">
      <p className="text-xs text-neutral-500">{label}</p>
      <p className={`text-xl font-semibold ${tone ?? "text-neutral-100"}`}>{value}</p>
    </div>
  );
}

function DraftRowCard({
  row,
  onChanged,
}: {
  row: PublishingDraftRow;
  onChanged: () => void;
}) {
  const vs = row.validation_summary;
  return (
    <article className="space-y-2 rounded-xl border border-neutral-800 bg-neutral-900/50 p-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="rounded-md bg-indigo-500/15 px-2 py-0.5 text-xs font-medium text-indigo-300">
          {PLATFORM_LABELS[row.platform] ?? row.platform}
        </span>
        <span
          className={`rounded-md px-2 py-0.5 text-xs ${STATUS_COLORS[row.status] ?? "bg-neutral-700/40 text-neutral-300"}`}
        >
          {STATUS_LABELS[row.status] ?? row.status}
        </span>
        <span
          className={`rounded-md px-2 py-0.5 text-xs ${vs.is_valid ? "bg-emerald-500/10 text-emerald-400" : "bg-amber-500/10 text-amber-300"}`}
        >
          {vs.is_valid ? "✓ gültig" : `✗ ${vs.blocking_issues_count} Problem(e)`}
        </span>
        {vs.warnings_count > 0 && (
          <span className="rounded-md bg-neutral-800 px-2 py-0.5 text-xs text-neutral-400">
            {vs.warnings_count} Hinweis(e)
          </span>
        )}
        {row.scheduled_at && (
          <span className="text-xs text-neutral-500">🗓 {row.scheduled_at}</span>
        )}
      </div>

      <div className="flex items-start gap-3">
        {row.source_preview_url && (
          <video
            src={`${API_BASE}${row.source_preview_url}`}
            preload="metadata"
            className="h-20 w-14 rounded-md border border-neutral-800 object-cover"
          />
        )}
        <div className="min-w-0 flex-1 space-y-0.5 text-sm">
          {row.title && (
            <p className="truncate font-medium text-neutral-100">{row.title}</p>
          )}
          {row.caption && (
            <p className="line-clamp-2 text-neutral-400">{row.caption}</p>
          )}
          {row.hashtags.length > 0 && (
            <p className="truncate text-xs text-indigo-300">
              {row.hashtags.join(" ")}
            </p>
          )}
          <p className="truncate text-xs text-neutral-600">
            Quelle: {row.job_filename} ·{" "}
            {row.source_type === "auto_clip"
              ? `Auto-Clip #${row.source_clip_index}`
              : `Export ${row.manual_export_id}`}
          </p>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2 pt-1">
        <Link
          href={row.planner_url}
          className="rounded-lg border border-neutral-700 px-3 py-1.5 text-xs font-medium text-neutral-200 hover:border-neutral-500"
        >
          Zum Planner
        </Link>
        <a
          href={`${API_BASE}${row.pack_url}`}
          download
          className="rounded-lg border border-indigo-500/40 bg-indigo-500/10 px-3 py-1.5 text-xs font-medium text-indigo-300 hover:bg-indigo-500/20"
        >
          Pack (ZIP)
        </a>
        <DuplicateDraftButton
          jobId={row.job_id}
          publishingId={row.publishing_id}
          currentPlatform={row.platform}
          plannerUrl={row.planner_url}
          onDuplicated={onChanged}
        />
      </div>
    </article>
  );
}

export default function GlobalPublishingPage() {
  const [data, setData] = useState<PublishingOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState("");
  const [platform, setPlatform] = useState("");
  const [q, setQ] = useState("");
  const [scheduledOnly, setScheduledOnly] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(
        await getPublishingOverview({
          status: status || undefined,
          platform: platform || undefined,
          q: q || undefined,
          scheduled_only: scheduledOnly || undefined,
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [status, platform, q, scheduledOnly]);

  useEffect(() => {
    const t = setTimeout(() => void load(), 200); // Suche entprellen
    return () => clearTimeout(t);
  }, [load]);

  return (
    <main className="mx-auto max-w-4xl space-y-6 px-4 py-8">
      <div>
        <h1 className="text-xl font-semibold text-neutral-100">Publishing</h1>
        <p className="text-sm text-neutral-500">
          Alle lokalen Publishing-Drafts über alle Jobs —{" "}
          <span className="text-neutral-400">
            kein automatischer Upload, kein Plattform-Login.
          </span>
        </p>
      </div>

      {data && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <SummaryCard label="Gesamt" value={data.total_drafts} />
          <SummaryCard label="Bereit" value={data.ready_count} tone="text-emerald-400" />
          <SummaryCard label="Geplant" value={data.scheduled_count} tone="text-indigo-400" />
          <SummaryCard label="Ungültig" value={data.invalid_count} tone="text-amber-400" />
          <SummaryCard label="YouTube Shorts" value={data.by_platform.youtube_shorts ?? 0} />
          <SummaryCard label="TikTok" value={data.by_platform.tiktok ?? 0} />
          <SummaryCard label="Instagram Reels" value={data.by_platform.instagram_reels ?? 0} />
        </div>
      )}

      <div className="flex flex-wrap gap-2 rounded-xl border border-neutral-800 bg-neutral-900/50 p-3">
        <select
          value={status}
          onChange={(e) => setStatus(e.target.value)}
          className="rounded-lg border border-neutral-700 bg-neutral-900 px-3 py-1.5 text-sm text-neutral-200"
        >
          <option value="">Alle Status</option>
          {Object.entries(STATUS_LABELS).map(([v, l]) => (
            <option key={v} value={v}>
              {l}
            </option>
          ))}
        </select>
        <select
          value={platform}
          onChange={(e) => setPlatform(e.target.value)}
          className="rounded-lg border border-neutral-700 bg-neutral-900 px-3 py-1.5 text-sm text-neutral-200"
        >
          <option value="">Alle Plattformen</option>
          {Object.entries(PLATFORM_LABELS).map(([v, l]) => (
            <option key={v} value={v}>
              {l}
            </option>
          ))}
        </select>
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Suche in Titel/Caption…"
          className="min-w-40 flex-1 rounded-lg border border-neutral-700 bg-neutral-900 px-3 py-1.5 text-sm text-neutral-200"
        />
        <label className="flex items-center gap-1.5 rounded-lg border border-neutral-700 px-3 py-1.5 text-sm text-neutral-300">
          <input
            type="checkbox"
            checked={scheduledOnly}
            onChange={(e) => setScheduledOnly(e.target.checked)}
          />
          Nur geplante
        </label>
      </div>

      {error && (
        <p className="rounded-lg border border-red-500/40 bg-red-500/10 px-3 py-2 text-sm text-red-300">
          {error}
        </p>
      )}

      {data && data.warnings.length > 0 && (
        <p className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-300">
          ⚠ {data.warnings.length} Job(s)/Draft(s) übersprungen: {data.warnings.join(" · ")}
        </p>
      )}

      {loading && !data ? (
        <p className="text-sm text-neutral-500">Lade Drafts…</p>
      ) : !data || data.drafts.length === 0 ? (
        <p className="rounded-2xl border border-dashed border-neutral-800 px-4 py-8 text-center text-sm text-neutral-500">
          Keine Publishing-Drafts gefunden. Auf einer Job-Seite bei einem Clip
          „Publishing vorbereiten" wählen.
        </p>
      ) : (
        <div className="space-y-3">
          {data.drafts.map((row) => (
            <DraftRowCard
              key={row.publishing_id}
              row={row}
              onChanged={() => void load()}
            />
          ))}
        </div>
      )}
    </main>
  );
}
