"use client";

// Wiederverwendbarer "Duplizieren"-Button für Publishing-Drafts.
// Erstellt einen neuen LOKALEN Draft (ggf. andere Plattform) — kein Upload.

import { useState } from "react";
import { duplicatePublishingDraft } from "@/lib/api";
import type { PublishingDraft, PublishingPlatform } from "@/lib/types";

const PLATFORM_LABELS: Record<PublishingPlatform, string> = {
  youtube_shorts: "YouTube Shorts",
  tiktok: "TikTok",
  instagram_reels: "Instagram Reels",
};

export default function DuplicateDraftButton({
  jobId,
  publishingId,
  currentPlatform,
  onDuplicated,
  plannerUrl,
}: {
  jobId: string;
  publishingId: string;
  currentPlatform: PublishingPlatform;
  onDuplicated: (draft: PublishingDraft) => void;
  plannerUrl?: string;
}) {
  const [open, setOpen] = useState(false);
  const [platform, setPlatform] = useState<PublishingPlatform>(currentPlatform);
  const [copySchedule, setCopySchedule] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<PublishingDraft | null>(null);

  async function handleDuplicate() {
    setBusy(true);
    setError(null);
    try {
      const draft = await duplicatePublishingDraft(jobId, publishingId, {
        platform,
        copy_schedule: copySchedule,
      });
      setSuccess(draft);
      onDuplicated(draft);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => {
          setOpen(true);
          setSuccess(null);
          setError(null);
        }}
        className="rounded-lg border border-neutral-700 px-3 py-1.5 text-xs font-medium text-neutral-200 hover:border-neutral-500"
      >
        Duplizieren
      </button>
    );
  }

  return (
    <div className="flex flex-col gap-1.5 rounded-lg border border-neutral-700 bg-neutral-900 p-2">
      <div className="flex flex-wrap items-center gap-1.5">
        <select
          value={platform}
          onChange={(e) => setPlatform(e.target.value as PublishingPlatform)}
          className="rounded-md border border-neutral-700 bg-neutral-950 px-2 py-1 text-xs text-neutral-200"
        >
          {Object.entries(PLATFORM_LABELS).map(([v, l]) => (
            <option key={v} value={v}>
              {l}
            </option>
          ))}
        </select>
        <label className="flex items-center gap-1 text-xs text-neutral-400">
          <input
            type="checkbox"
            checked={copySchedule}
            onChange={(e) => setCopySchedule(e.target.checked)}
          />
          Zeitplanung übernehmen
        </label>
        <button
          type="button"
          disabled={busy}
          onClick={() => void handleDuplicate()}
          className="rounded-md bg-white px-2.5 py-1 text-xs font-medium text-neutral-900 hover:bg-neutral-200 disabled:opacity-50"
        >
          {busy ? "…" : "Bestätigen"}
        </button>
        <button
          type="button"
          onClick={() => setOpen(false)}
          className="rounded-md px-2 py-1 text-xs text-neutral-500 hover:text-neutral-300"
        >
          Abbrechen
        </button>
      </div>
      {error && <p className="text-xs text-red-400">{error}</p>}
      {success && (
        <p className="text-xs text-emerald-400">
          ✓ Dupliziert als {PLATFORM_LABELS[success.platform]}
          {success.warning ? ` — ⚠ ${success.warning}` : ""}
          {plannerUrl && (
            <>
              {" · "}
              <a
                href={`${plannerUrl}?draft=${success.publishing_id}`}
                className="underline hover:text-emerald-300"
              >
                Neuen Draft öffnen
              </a>
            </>
          )}
        </p>
      )}
    </div>
  );
}
