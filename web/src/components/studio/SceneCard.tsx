"use client";

import { useT, type TKey } from "@/lib/i18n";
import type { MediaItem, Scene } from "@/lib/studio";
import { btnCls, cardCls, inputCls, labelCls } from "./ui";

type Props = {
  scene: Scene;
  index: number;
  count: number;
  media: MediaItem[];
  busy: boolean;
  flagged: string[];
  onChange: (patch: Partial<Scene>) => void;
  onMove: (delta: number) => void;
  onDuplicate: () => void;
  onDelete: () => void;
  onRegenerate: () => void;
};

const MODES = ["motion", "static", "media", "ai_image", "split"] as const;

export default function SceneCard(p: Props) {
  const t = useT();
  const s = p.scene;
  const id = `scene-${s.id}`;
  const visuals = p.media.filter((m) => m.kind !== "audio");
  const setVisual = (patch: Partial<Scene["visual"]>) => p.onChange({ visual: { ...s.visual, ...patch } });

  return (
    <li className={cardCls} aria-label={`${t("ed.scene")} ${p.index + 1}`}>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className="grid h-7 w-7 place-items-center rounded-full bg-neutral-800 text-xs font-semibold text-white">
            {p.index + 1}
          </span>
          <label htmlFor={`${id}-kind`} className="sr-only">
            {t("ed.scene")} {p.index + 1}: Typ
          </label>
          <select
            id={`${id}-kind`}
            className="rounded-md border border-neutral-700 bg-neutral-900 px-2 py-1 text-xs text-neutral-100"
            value={s.kind}
            onChange={(e) => p.onChange({ kind: e.target.value as Scene["kind"] })}
          >
            {(["hook", "body", "cta"] as const).map((k) => (
              <option key={k} value={k}>
                {t(`ed.kind.${k}` as TKey)}
              </option>
            ))}
          </select>
          {s.audio_source && (
            <span className="rounded-full border border-sky-500/40 px-2 py-0.5 text-[11px] text-sky-300">
              {t("ed.originalAudio")} {s.audio_source.start.toFixed(1)}–{s.audio_source.end.toFixed(1)}s
            </span>
          )}
        </div>
        <div className="flex flex-wrap gap-1">
          <button type="button" className={btnCls} disabled={p.index === 0} onClick={() => p.onMove(-1)} aria-label={`${t("ed.up")} (${p.index + 1})`}>
            ↑
          </button>
          <button
            type="button"
            className={btnCls}
            disabled={p.index === p.count - 1}
            onClick={() => p.onMove(1)}
            aria-label={`${t("ed.down")} (${p.index + 1})`}
          >
            ↓
          </button>
          <button type="button" className={btnCls} onClick={p.onDuplicate}>
            {t("ed.duplicate")}
          </button>
          <button type="button" className={btnCls} disabled={p.busy} onClick={p.onRegenerate}>
            {t("ed.regenerate")}
          </button>
          <button type="button" className={btnCls} onClick={p.onDelete} aria-label={`${t("common.delete")} (${p.index + 1})`}>
            {t("common.delete")}
          </button>
        </div>
      </div>

      {p.flagged.map((msg) => (
        <p key={msg} className="mb-2 text-xs text-amber-300">
          ⚠ {msg}
        </p>
      ))}

      <div className="grid gap-3 md:grid-cols-2">
        <div>
          <label htmlFor={`${id}-text`} className={labelCls}>
            {t("ed.text")}
          </label>
          <textarea
            id={`${id}-text`}
            className={`${inputCls} min-h-24`}
            value={s.text}
            onChange={(e) => p.onChange({ text: e.target.value })}
          />
        </div>
        <div className="space-y-3">
          {!s.audio_source && (
            <div>
              <label htmlFor={`${id}-voice`} className={labelCls}>
                {t("ed.voiceText")}
              </label>
              <input
                id={`${id}-voice`}
                className={inputCls}
                value={s.voice_text ?? ""}
                onChange={(e) => p.onChange({ voice_text: e.target.value || null })}
              />
            </div>
          )}
          <div>
            <label htmlFor={`${id}-prompt`} className={labelCls}>
              {t("ed.visualPrompt")}
            </label>
            <input
              id={`${id}-prompt`}
              className={inputCls}
              value={s.visual_prompt}
              onChange={(e) => p.onChange({ visual_prompt: e.target.value })}
            />
          </div>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label htmlFor={`${id}-mode`} className={labelCls}>
              {t("ed.visual")}
            </label>
            <select
              id={`${id}-mode`}
              className={inputCls}
              value={s.visual.mode}
              onChange={(e) => {
                const mode = e.target.value as Scene["visual"]["mode"];
                setVisual({ mode, media: mode === "media" ? (s.visual.media ?? visuals[0]?.name ?? null) : s.visual.media });
              }}
            >
              {MODES.map((m) => (
                <option key={m} value={m} disabled={m === "media" && visuals.length === 0}>
                  {t(`ed.mode.${m}` as TKey)}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label htmlFor={`${id}-media`} className={labelCls}>
              {t("ed.media")}
            </label>
            <select
              id={`${id}-media`}
              className={inputCls}
              value={s.visual.media ?? ""}
              disabled={visuals.length === 0 || (s.visual.mode !== "media" && s.visual.mode !== "split")}
              onChange={(e) => setVisual({ media: e.target.value || null })}
            >
              <option value="">–</option>
              {visuals.map((m) => (
                <option key={m.name} value={m.name}>
                  {m.name}
                </option>
              ))}
            </select>
          </div>
        </div>
        <div className="grid grid-cols-3 gap-3">
          <div>
            <label htmlFor={`${id}-dur`} className={labelCls}>
              {t("ed.duration")}
            </label>
            <input
              id={`${id}-dur`}
              type="number"
              min={0.5}
              max={120}
              step={0.5}
              className={inputCls}
              value={s.duration ?? ""}
              onChange={(e) => p.onChange({ duration: e.target.value ? Number(e.target.value) : null })}
            />
          </div>
          <div>
            <label htmlFor={`${id}-pause`} className={labelCls}>
              {t("ed.pause")}
            </label>
            <input
              id={`${id}-pause`}
              type="number"
              min={0}
              max={5}
              step={0.25}
              className={inputCls}
              value={s.pause_after}
              onChange={(e) => p.onChange({ pause_after: Number(e.target.value) || 0 })}
            />
          </div>
          <div>
            <label htmlFor={`${id}-headline`} className={labelCls}>
              {t("ed.headline")}
            </label>
            <input
              id={`${id}-headline`}
              className={inputCls}
              maxLength={60}
              value={s.headline}
              onChange={(e) => p.onChange({ headline: e.target.value })}
            />
          </div>
        </div>
      </div>
    </li>
  );
}
