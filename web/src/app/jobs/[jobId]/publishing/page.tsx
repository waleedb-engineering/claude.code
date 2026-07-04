"use client";

// Publishing Planner — plant Veröffentlichungen als LOKALE Drafts.
// Kein echter Upload, kein OAuth, kein Token: Export als Publishing Pack (ZIP).

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import {
  clipPreviewUrl,
  createPublishingDraft,
  deletePublishingDraft,
  getClips,
  getManualExports,
  listPublishingDrafts,
  manualExportPreviewUrl,
  publishingPackUrl,
  updatePublishingDraft,
  validatePublishingDraft,
} from "@/lib/api";
import DuplicateDraftButton from "@/components/DuplicateDraftButton";
import YouTubeDryRunPanel from "@/components/YouTubeDryRunPanel";
import YouTubePrivateUploadPanel from "@/components/YouTubePrivateUploadPanel";
import YouTubeReadinessPanel from "@/components/YouTubeReadinessPanel";
import type {
  ClipsJson,
  ManualExport,
  PublishingDraft,
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

const CHECKLIST_LABELS: [string, string][] = [
  ["mp4_exists", "MP4 bereit"],
  ["format_9_16", "9:16-Format"],
  ["title_present", "Titel vorhanden"],
  ["caption_present", "Caption vorhanden"],
  ["hashtags_present", "Hashtags vorhanden"],
  ["platform_selected", "Plattform gewählt"],
  ["no_viral_guarantee", "Keine Viralitätsversprechen"],
  ["safe_status", "Sicherer Status (kein Upload aktiv)"],
];

const QUALITY_HINT_LABELS: Record<string, string> = {
  title_too_long: "Titel ist ungewöhnlich lang",
  caption_too_long: "Caption ist ungewöhnlich lang",
  too_many_hashtags: "Viele Hashtags — ggf. reduzieren",
  missing_pinned_comment: "Kein Pinned Comment gesetzt",
  scheduled_in_past: "Geplanter Termin liegt in der Vergangenheit",
  weak_metadata: "Titel und Caption sind beide leer",
};

// Fallback für alte, gespeicherte Checks ohne `summary` (Rückwärtskompatibilität).
const LEGACY_CHECK_LABELS: [string, string][] = [
  ["mp4_exists", "MP4 bereit"],
  ["format_9_16", "9:16-Format"],
  ["platform_valid", "Plattform gewählt"],
  ["title_present", "Titel vorhanden"],
  ["caption_present", "Caption vorhanden"],
  ["hashtags_present", "Hashtags vorhanden"],
  ["no_virality_claim", "Keine Viralitätsversprechen"],
];

function CheckRow({
  label,
  val,
}: {
  label: string;
  val: boolean | null | undefined;
}) {
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

function Checklist({ draft }: { draft: PublishingDraft }) {
  const v = draft.validation;
  if (!v) {
    return (
      <p className="text-xs text-neutral-500">
        Noch nicht validiert — „Prüfen“ klicken.
      </p>
    );
  }
  const summary = v.summary;
  if (!summary) {
    // Rückwärtskompatibel: alte Drafts ohne summary zeigen die Rohchecks.
    const checks = v.checks as unknown as Record<string, boolean | null>;
    return (
      <ul className="grid gap-x-4 gap-y-0.5 text-xs sm:grid-cols-2">
        {LEGACY_CHECK_LABELS.map(([key, label]) => (
          <CheckRow key={key} label={label} val={checks[key]} />
        ))}
      </ul>
    );
  }
  const checklist = summary.checklist as unknown as Record<
    string,
    boolean | null
  >;
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <span
          className={
            summary.is_valid ? "text-emerald-400" : "text-red-400"
          }
        >
          {summary.is_valid
            ? "✓ Gültig — bereit fürs Pack"
            : `✗ ${summary.blocking_issues_count} blockierende(s) Problem(e)`}
        </span>
        {summary.warnings_count > 0 && (
          <span className="text-amber-400">
            ⚠ {summary.warnings_count} Hinweis(e)
          </span>
        )}
      </div>
      <ul className="grid gap-x-4 gap-y-0.5 text-xs sm:grid-cols-2">
        {CHECKLIST_LABELS.map(([key, label]) => (
          <CheckRow key={key} label={label} val={checklist[key]} />
        ))}
      </ul>
      {summary.quality_hints.length > 0 && (
        <ul className="space-y-0.5 text-xs">
          {summary.quality_hints.map((h) => (
            <li
              key={h}
              className={
                h === "scheduled_in_past"
                  ? "flex items-center gap-1.5 rounded-md bg-amber-500/10 px-2 py-1 text-amber-300"
                  : "flex items-center gap-1.5 text-amber-400"
              }
            >
              <span>⚠</span>
              <span>{QUALITY_HINT_LABELS[h] ?? h}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function DraftCard({
  jobId,
  draft,
  onChanged,
  onDeleted,
  highlighted,
}: {
  jobId: string;
  draft: PublishingDraft;
  onChanged: (d: PublishingDraft) => void;
  onDeleted: (id: string) => void;
  highlighted?: boolean;
}) {
  const [edit, setEdit] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState({
    platform: draft.platform,
    title: draft.title,
    caption: draft.caption,
    description: draft.description,
    hashtags: draft.hashtags.join(" "),
    pinned_comment: draft.pinned_comment,
    scheduled_at: draft.scheduled_at ?? "",
  });

  const previewSrc =
    draft.source_type === "manual_export" && draft.manual_export_id
      ? manualExportPreviewUrl(jobId, draft.manual_export_id)
      : draft.source_clip_index
        ? clipPreviewUrl(jobId, draft.source_clip_index)
        : null;

  async function run(action: () => Promise<PublishingDraft | void>) {
    setBusy(true);
    setError(null);
    try {
      const res = await action();
      if (res) onChanged(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <article
      id={`draft-${draft.publishing_id}`}
      className={`space-y-3 rounded-2xl border p-4 transition ${
        highlighted
          ? "border-indigo-500/70 bg-indigo-500/5 ring-1 ring-indigo-500/40"
          : "border-neutral-800 bg-neutral-900/50"
      }`}
    >
      <div className="flex flex-wrap items-center gap-2">
        <span className="rounded-md bg-indigo-500/15 px-2 py-0.5 text-xs font-medium text-indigo-300">
          {PLATFORM_LABELS[draft.platform] ?? draft.platform}
        </span>
        <span
          className={`rounded-md px-2 py-0.5 text-xs ${STATUS_COLORS[draft.status] ?? "bg-neutral-700/40 text-neutral-300"}`}
        >
          {STATUS_LABELS[draft.status] ?? draft.status}
        </span>
        <span
          className="rounded-md border border-neutral-700 px-2 py-0.5 text-xs text-neutral-500"
          title="Lokaler Draft — kein automatischer Plattform-Upload"
        >
          🔒 lokal
        </span>
        <span className="text-xs text-neutral-500">
          {draft.source_type === "auto_clip"
            ? `Auto-Clip #${draft.source_clip_index}`
            : `Manueller Export ${draft.manual_export_id}`}
        </span>
        {draft.scheduled_at && (
          <span className="text-xs text-neutral-500">
            🗓 {draft.scheduled_at}
          </span>
        )}
      </div>
      {draft.warning && (
        <p className="rounded-md bg-amber-500/10 px-2 py-1 text-xs text-amber-300">
          ⚠ {draft.warning}
        </p>
      )}

      {previewSrc && (
        <video
          src={previewSrc}
          controls
          preload="metadata"
          className="max-h-64 rounded-lg border border-neutral-800"
        />
      )}

      {!edit ? (
        <div className="space-y-1 text-sm">
          {draft.title && (
            <p className="font-medium text-neutral-100">{draft.title}</p>
          )}
          {draft.caption && <p className="text-neutral-300">{draft.caption}</p>}
          {draft.hashtags.length > 0 && (
            <p className="text-xs text-indigo-300">{draft.hashtags.join(" ")}</p>
          )}
        </div>
      ) : (
        <div className="grid gap-2">
          <select
            value={form.platform}
            onChange={(e) =>
              setForm({ ...form, platform: e.target.value as PublishingPlatform })
            }
            className="rounded-lg border border-neutral-700 bg-neutral-900 px-3 py-1.5 text-sm text-neutral-200"
          >
            {Object.entries(PLATFORM_LABELS).map(([v, l]) => (
              <option key={v} value={v}>
                {l}
              </option>
            ))}
          </select>
          <input
            value={form.title}
            onChange={(e) => setForm({ ...form, title: e.target.value })}
            placeholder="Titel"
            className="rounded-lg border border-neutral-700 bg-neutral-900 px-3 py-1.5 text-sm text-neutral-200"
          />
          <textarea
            value={form.caption}
            onChange={(e) => setForm({ ...form, caption: e.target.value })}
            placeholder="Caption"
            rows={2}
            className="rounded-lg border border-neutral-700 bg-neutral-900 px-3 py-1.5 text-sm text-neutral-200"
          />
          <textarea
            value={form.description}
            onChange={(e) => setForm({ ...form, description: e.target.value })}
            placeholder="Beschreibung"
            rows={2}
            className="rounded-lg border border-neutral-700 bg-neutral-900 px-3 py-1.5 text-sm text-neutral-200"
          />
          <input
            value={form.hashtags}
            onChange={(e) => setForm({ ...form, hashtags: e.target.value })}
            placeholder="#hashtags (mit Leerzeichen getrennt)"
            className="rounded-lg border border-neutral-700 bg-neutral-900 px-3 py-1.5 text-sm text-neutral-200"
          />
          <input
            value={form.pinned_comment}
            onChange={(e) => setForm({ ...form, pinned_comment: e.target.value })}
            placeholder="Pinned Comment (optional)"
            className="rounded-lg border border-neutral-700 bg-neutral-900 px-3 py-1.5 text-sm text-neutral-200"
          />
          <input
            value={form.scheduled_at}
            onChange={(e) => setForm({ ...form, scheduled_at: e.target.value })}
            placeholder="Geplant (optional, z. B. 2026-07-10T18:00)"
            className="rounded-lg border border-neutral-700 bg-neutral-900 px-3 py-1.5 text-sm text-neutral-200"
          />
        </div>
      )}

      <Checklist draft={draft} />

      {draft.platform === "youtube_shorts" && (
        <YouTubeDryRunPanel jobId={jobId} publishingId={draft.publishing_id} />
      )}

      {draft.platform === "youtube_shorts" && (
        <YouTubeReadinessPanel jobId={jobId} publishingId={draft.publishing_id} />
      )}

      {draft.platform === "youtube_shorts" && (
        <YouTubePrivateUploadPanel
          jobId={jobId}
          publishingId={draft.publishing_id}
        />
      )}

      {error && (
        <p className="rounded-lg border border-red-500/40 bg-red-500/10 px-3 py-1.5 text-xs text-red-300">
          {error}
        </p>
      )}

      <div className="flex flex-wrap items-center gap-2 pt-1">
        {!edit ? (
          <button
            type="button"
            onClick={() => setEdit(true)}
            className="rounded-lg border border-neutral-700 px-3 py-1.5 text-xs font-medium text-neutral-200 hover:border-neutral-500"
          >
            Bearbeiten
          </button>
        ) : (
          <button
            type="button"
            disabled={busy}
            onClick={() =>
              run(async () => {
                const d = await updatePublishingDraft(jobId, draft.publishing_id, {
                  platform: form.platform,
                  title: form.title,
                  caption: form.caption,
                  description: form.description,
                  hashtags: form.hashtags
                    .split(/\s+/)
                    .map((h) => h.trim())
                    .filter(Boolean),
                  pinned_comment: form.pinned_comment,
                  scheduled_at: form.scheduled_at || null,
                });
                setEdit(false);
                return d;
              })
            }
            className="rounded-lg bg-white px-3 py-1.5 text-xs font-medium text-neutral-900 hover:bg-neutral-200 disabled:opacity-50"
          >
            Speichern
          </button>
        )}
        <button
          type="button"
          disabled={busy}
          onClick={() =>
            run(() => validatePublishingDraft(jobId, draft.publishing_id))
          }
          className="rounded-lg border border-neutral-700 px-3 py-1.5 text-xs font-medium text-neutral-200 hover:border-neutral-500 disabled:opacity-50"
        >
          Prüfen
        </button>
        <a
          href={publishingPackUrl(jobId, draft.publishing_id)}
          className="rounded-lg border border-indigo-500/40 bg-indigo-500/10 px-3 py-1.5 text-xs font-medium text-indigo-300 hover:bg-indigo-500/20"
          download
        >
          Publishing Pack (ZIP)
        </a>
        <DuplicateDraftButton
          jobId={jobId}
          publishingId={draft.publishing_id}
          currentPlatform={draft.platform}
          onDuplicated={onChanged}
        />
        <button
          type="button"
          disabled={busy}
          onClick={() =>
            run(async () => {
              await deletePublishingDraft(jobId, draft.publishing_id);
              onDeleted(draft.publishing_id);
            })
          }
          className="ml-auto rounded-lg border border-red-500/30 px-3 py-1.5 text-xs text-red-300 hover:bg-red-500/10 disabled:opacity-50"
        >
          Löschen
        </button>
      </div>
    </article>
  );
}

export default function PublishingPage() {
  const params = useParams<{ jobId: string }>();
  const search = useSearchParams();
  const jobId = params.jobId;

  const [drafts, setDrafts] = useState<PublishingDraft[]>([]);
  const [clips, setClips] = useState<ClipsJson | null>(null);
  const [manualExports, setManualExports] = useState<ManualExport[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

  // Neuer-Draft-Formular (mit Prefill aus ?clip= / ?export=)
  const [source, setSource] = useState<string>(() => {
    const clip = search.get("clip");
    const exp = search.get("export");
    if (clip) return `clip:${clip}`;
    if (exp) return `export:${exp}`;
    return "";
  });
  const [platform, setPlatform] = useState<PublishingPlatform>("youtube_shorts");
  const highlightId = search.get("draft");

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [d, me] = await Promise.all([
        listPublishingDrafts(jobId),
        getManualExports(jobId).catch(() => [] as ManualExport[]),
      ]);
      setDrafts(d);
      setManualExports(me);
      try {
        setClips(await getClips(jobId));
      } catch {
        setClips(null);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [jobId]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (!highlightId || drafts.length === 0) return;
    document
      .getElementById(`draft-${highlightId}`)
      ?.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [highlightId, drafts]);

  const sourceOptions = useMemo(() => {
    const opts: { value: string; label: string }[] = [];
    (clips?.clips ?? []).forEach((c, i) => {
      opts.push({
        value: `clip:${i + 1}`,
        label: `Auto-Clip #${i + 1} (Score ${Math.round(c.performance_score ?? c.score)})`,
      });
    });
    manualExports.forEach((e) => {
      opts.push({
        value: `export:${e.export_id}`,
        label: `Manueller Export ${e.title || e.export_id}`,
      });
    });
    return opts;
  }, [clips, manualExports]);

  async function handleCreate() {
    if (!source) return;
    setCreating(true);
    setError(null);
    try {
      const [kind, id] = source.split(":", 2);
      const draft = await createPublishingDraft(jobId, {
        platform,
        source_type: kind === "clip" ? "auto_clip" : "manual_export",
        ...(kind === "clip"
          ? { source_clip_index: Number(id) }
          : { manual_export_id: id }),
      });
      setDrafts((prev) => [draft, ...prev]);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setCreating(false);
    }
  }

  return (
    <main className="mx-auto max-w-3xl space-y-6 px-4 py-8">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-neutral-100">
            Publishing Planner
          </h1>
          <p className="text-sm text-neutral-500">
            Plant Veröffentlichungen als lokale Drafts —{" "}
            <span className="text-neutral-400">
              kein automatischer Upload, kein Login bei Plattformen.
            </span>
          </p>
        </div>
        <Link
          href={`/jobs/${jobId}`}
          className="rounded-lg border border-neutral-700 px-3 py-1.5 text-sm text-neutral-300 hover:border-neutral-500"
        >
          ← Zum Job
        </Link>
      </div>

      <section className="space-y-3 rounded-2xl border border-neutral-800 bg-neutral-900/50 p-4">
        <h2 className="text-sm font-medium text-neutral-200">Neuer Draft</h2>
        <div className="flex flex-wrap gap-2">
          <select
            value={source}
            onChange={(e) => setSource(e.target.value)}
            className="min-w-52 flex-1 rounded-lg border border-neutral-700 bg-neutral-900 px-3 py-2 text-sm text-neutral-200"
          >
            <option value="">Clip wählen…</option>
            {sourceOptions.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
          <select
            value={platform}
            onChange={(e) => setPlatform(e.target.value as PublishingPlatform)}
            className="rounded-lg border border-neutral-700 bg-neutral-900 px-3 py-2 text-sm text-neutral-200"
          >
            {Object.entries(PLATFORM_LABELS).map(([v, l]) => (
              <option key={v} value={v}>
                {l}
              </option>
            ))}
          </select>
          <button
            type="button"
            disabled={!source || creating}
            onClick={() => void handleCreate()}
            className="rounded-lg bg-white px-4 py-2 text-sm font-medium text-neutral-900 hover:bg-neutral-200 disabled:opacity-50"
          >
            {creating ? "Erstelle…" : "Draft anlegen"}
          </button>
        </div>
        <p className="text-xs text-neutral-500">
          Titel, Caption und Hashtags werden aus dem Content-Paket des Clips
          übernommen und sind danach frei editierbar.
        </p>
      </section>

      {error && (
        <p className="rounded-lg border border-red-500/40 bg-red-500/10 px-3 py-2 text-sm text-red-300">
          {error}
        </p>
      )}

      {loading ? (
        <p className="text-sm text-neutral-500">Lade Drafts…</p>
      ) : drafts.length === 0 ? (
        <p className="rounded-2xl border border-dashed border-neutral-800 px-4 py-8 text-center text-sm text-neutral-500">
          Noch keine Publishing-Drafts. Oben einen Clip und eine Plattform
          wählen.
        </p>
      ) : (
        <div className="space-y-4">
          {drafts.map((d) => (
            <DraftCard
              key={d.publishing_id}
              jobId={jobId}
              draft={d}
              onChanged={(nd) =>
                setDrafts((prev) =>
                  prev.some((x) => x.publishing_id === nd.publishing_id)
                    ? prev.map((x) =>
                        x.publishing_id === nd.publishing_id ? nd : x,
                      )
                    : [nd, ...prev],
                )
              }
              highlighted={highlightId === d.publishing_id}
              onDeleted={(id) =>
                setDrafts((prev) => prev.filter((x) => x.publishing_id !== id))
              }
            />
          ))}
        </div>
      )}

      <p className="text-xs text-neutral-600">
        Hinweis: Das Publishing Pack (MP4 + Texte) ist für den manuellen Upload
        gedacht. Echte Plattform-Anbindung kommt erst nach offizieller
        API-Prüfung — Details in docs/PUBLISHING_AGENT_PLAN.md.
      </p>
    </main>
  );
}
