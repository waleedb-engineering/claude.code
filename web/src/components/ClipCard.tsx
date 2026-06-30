import type { ScoredClipDict } from "@/lib/types";
import { clipDownloadUrl, clipPreviewUrl } from "@/lib/api";
import { clipTitle, fmtTime, fmtDuration } from "@/lib/format";
import ScoreRing from "./ScoreRing";

const BREAKDOWN_LABELS: { key: keyof BreakdownVals; label: string }[] = [
  { key: "hook", label: "Hook" },
  { key: "clarity", label: "Klarheit" },
  { key: "emotion", label: "Emotion" },
  { key: "pacing", label: "Tempo" },
  { key: "payoff", label: "Pointe" },
];

interface BreakdownVals {
  hook: number;
  clarity: number;
  emotion: number;
  pacing: number;
  payoff: number;
}

function Bar({ label, value }: { label: string; value: number }) {
  const v = Math.max(0, Math.min(100, value));
  return (
    <div className="flex items-center gap-2">
      <span className="w-16 shrink-0 text-xs text-neutral-400">{label}</span>
      <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-neutral-800">
        <div
          className="h-full rounded-full bg-gradient-to-r from-indigo-500 to-fuchsia-500"
          style={{ width: `${v}%` }}
        />
      </div>
      <span className="w-8 shrink-0 text-right text-xs tabular-nums text-neutral-500">
        {Math.round(v)}
      </span>
    </div>
  );
}

export default function ClipCard({
  clip,
  index,
  jobId,
  downloadable,
}: {
  clip: ScoredClipDict;
  index: number;
  jobId: string;
  downloadable: boolean;
}) {
  const title = clipTitle(clip.metadata, index);

  return (
    <article className="flex flex-col gap-4 rounded-2xl border border-neutral-800 bg-neutral-900/60 p-5 transition hover:border-neutral-700">
      <div className="flex items-start gap-4">
        <ScoreRing score={clip.score} />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="rounded-md bg-neutral-800 px-1.5 py-0.5 text-[11px] font-medium text-neutral-400">
              #{index}
            </span>
            <h3 className="truncate font-semibold text-neutral-100">{title}</h3>
          </div>
          <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-xs text-neutral-400">
            <span>Start {fmtTime(clip.start)}</span>
            <span>Ende {fmtTime(clip.end)}</span>
            <span>Länge {fmtDuration(clip.duration)}</span>
            <span className="text-neutral-600">·</span>
            <span className="text-neutral-500">{clip.scorer}</span>
          </div>
        </div>
      </div>

      {downloadable && (
        <div className="overflow-hidden rounded-xl border border-neutral-800 bg-black">
          <video
            controls
            preload="metadata"
            playsInline
            src={clipPreviewUrl(jobId, index)}
            className="mx-auto max-h-80 w-auto"
          />
        </div>
      )}

      {clip.silence_info?.applied && (
        <div className="rounded-lg border border-neutral-800 bg-neutral-800/30 px-3 py-2 text-xs">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-neutral-400">
            <span>
              Original{" "}
              <span className="text-neutral-200">
                {fmtDuration(clip.silence_info.original_duration)}
              </span>
            </span>
            <span className="text-neutral-600">→</span>
            <span>
              Final{" "}
              <span className="text-neutral-200">
                {fmtDuration(clip.silence_info.final_duration)}
              </span>
            </span>
            <span className="text-neutral-600">·</span>
            <span className="text-emerald-400">
              −{clip.silence_info.removed_seconds.toFixed(1)}s Stille
            </span>
            <span className="text-neutral-600">·</span>
            <span>
              Schnitt-Optimierung{" "}
              {clip.silence_info.audio_smoothing ? "aktiv" : "inaktiv"}
            </span>
          </div>
          {clip.silence_info.fallback && (
            <p className="mt-1 text-amber-400">
              ⚠ Fallback: Silence-Removal nicht vollständig angewandt.
            </p>
          )}
        </div>
      )}

      <div className="space-y-1.5">
        {BREAKDOWN_LABELS.map(({ key, label }) => (
          <Bar key={key} label={label} value={clip.breakdown[key]} />
        ))}
      </div>

      {clip.reason && (
        <p className="rounded-lg bg-neutral-800/40 px-3 py-2 text-sm text-neutral-300">
          {clip.reason}
        </p>
      )}

      <div>
        <p className="mb-1 text-[11px] uppercase tracking-wide text-neutral-500">
          Transkript-Ausschnitt
        </p>
        <p className="line-clamp-3 text-sm leading-relaxed text-neutral-400">
          {clip.text}
        </p>
      </div>

      <div className="mt-auto flex items-center gap-2 pt-1">
        {downloadable ? (
          <a
            href={clipDownloadUrl(jobId, index)}
            className="inline-flex items-center gap-2 rounded-lg bg-white px-3.5 py-2 text-sm font-medium text-neutral-900 transition hover:bg-neutral-200"
            download
          >
            <svg
              className="h-4 w-4"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
            >
              <path
                d="M12 3v12m0 0 4-4m-4 4-4-4M5 21h14"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
            MP4 herunterladen
          </a>
        ) : (
          <span className="rounded-lg border border-neutral-800 px-3.5 py-2 text-sm text-neutral-500">
            Nicht gerendert
          </span>
        )}
      </div>
    </article>
  );
}
