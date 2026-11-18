"use client";

import { useEffect, useRef, useState } from "react";
import { useT } from "@/lib/i18n";
import {
  TRANSITION_IDS,
  errorMessage,
  studio,
  type Estimate,
  type MediaItem,
  type Project,
  type Template,
  type TransitionId,
  type VoiceOptions,
} from "@/lib/studio";
import BackgroundTool from "./BackgroundTool";
import { ErrorBox, Progress, btnCls, cardCls, inputCls, labelCls } from "./ui";

type Props = {
  project: Project;
  media: MediaItem[];
  estimate: Estimate | null;
  onChange: (patch: Partial<Project>) => void;
  onMediaChanged: () => void;
  onApplyTemplate?: (templateId: string) => Promise<void>;
};

export default function SettingsPanel({ project, media, estimate, onChange, onMediaChanged, onApplyTemplate }: Props) {
  const t = useT();
  const [voices, setVoices] = useState<VoiceOptions | null>(null);
  const [tracks, setTracks] = useState<{ id: string; name: string }[]>([]);
  const [upload, setUpload] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [captionText, setCaptionText] = useState("");
  const [templates, setTemplates] = useState<Template[]>([]);
  const [templatePick, setTemplatePick] = useState("");
  const [notice, setNotice] = useState<string | null>(null);
  const [bgTarget, setBgTarget] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const language = project.language;

  useEffect(() => {
    (async () => {
      try {
        const [v, m, tp] = await Promise.all([studio.voices(language), studio.music(), studio.templates()]);
        setVoices(v);
        setTracks(m.tracks);
        setTemplates(tp);
      } catch (e) {
        setError(errorMessage(e));
      }
    })();
  }, [language]);

  const provider = voices?.providers.find((p) => p.id === project.voice.provider);
  const audioMedia = media.filter((m) => m.kind === "audio");
  const videoMedia = media.filter((m) => m.kind === "video");
  const usesSpeech =
    project.voice.provider === "auto" ? (voices?.auto_selection.produces_speech ?? true) : (provider?.produces_speech ?? true);
  const sample = captionText || project.scenes[0]?.text || "";

  async function onFiles(list: FileList | null) {
    if (!list?.length) return;
    setError(null);
    try {
      for (const file of Array.from(list)) {
        setUpload(0);
        await studio.uploadMedia(project.id, file, setUpload);
      }
      onMediaChanged();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setUpload(null);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  async function saveAsTemplate() {
    const name = window.prompt(t("tpl.namePrompt"), project.title);
    if (!name) return;
    setError(null);
    try {
      const tpl = await studio.saveTemplate({ name, from_project: project.id });
      setTemplates((list) => [...list, tpl]);
      setNotice(t("tpl.saved"));
    } catch (e) {
      setError(errorMessage(e));
    }
  }

  async function removeTemplate(id: string) {
    setError(null);
    try {
      await studio.deleteTemplate(id);
      setTemplates((list) => list.filter((x) => x.id !== id));
      setTemplatePick("");
    } catch (e) {
      setError(errorMessage(e));
    }
  }

  const pickedTemplate = templates.find((x) => x.id === templatePick);

  async function playPreview() {
    setError(null);
    try {
      let confirmCost = false;
      if (provider?.paid) confirmCost = window.confirm(`${t("ed.voicePreview")}: ${provider.label} (${t("common.paid")})`);
      if (provider?.paid && !confirmCost) return;
      const urlObj = await studio.voicePreview(
        language,
        project.voice.provider,
        project.voice.voice_id,
        confirmCost,
        project.voice.speed,
      );
      setPreviewUrl(urlObj);
    } catch (e) {
      setError(errorMessage(e));
    }
  }

  return (
    <aside className={`${cardCls} space-y-5`} aria-label={t("ed.settings")}>
      <h2 className="text-sm font-semibold text-white">{t("ed.settings")}</h2>
      <ErrorBox message={error} />

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label htmlFor="s-lang" className={labelCls}>
            {t("common.language")}
          </label>
          <select id="s-lang" className={inputCls} value={project.language} onChange={(e) => onChange({ language: e.target.value as "de" | "en" })}>
            <option value="de">Deutsch</option>
            <option value="en">English</option>
          </select>
        </div>
        <div>
          <label htmlFor="s-style" className={labelCls}>
            {t("ed.style")}
          </label>
          <select id="s-style" className={inputCls} value={project.style} onChange={(e) => onChange({ style: e.target.value as Project["style"] })}>
            <option value="clean">Clean</option>
            <option value="cinematic">Cinematic</option>
          </select>
        </div>
        <div>
          <label htmlFor="s-aspect" className={labelCls}>
            {t("create.aspect")}
          </label>
          <select id="s-aspect" className={inputCls} value={project.aspect_ratio} onChange={(e) => onChange({ aspect_ratio: e.target.value })}>
            {["9:16", "16:9", "1:1", "4:5"].map((a) => (
              <option key={a}>{a}</option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="s-res" className={labelCls}>
            {t("create.resolution")}
          </label>
          <select id="s-res" className={inputCls} value={project.resolution} onChange={(e) => onChange({ resolution: e.target.value })}>
            {["720p", "1080p", "4k"].map((a) => (
              <option key={a}>{a}</option>
            ))}
          </select>
        </div>
      </div>

      <div className="space-y-2">
        <label htmlFor="s-cap" className={labelCls}>
          {t("create.captions")}
        </label>
        <select
          id="s-cap"
          className={inputCls}
          value={project.captions.style}
          onChange={(e) => onChange({ captions: { ...project.captions, style: e.target.value as Project["captions"]["style"] } })}
        >
          {["minimal", "bold", "karaoke", "dynamic", "none"].map((a) => (
            <option key={a}>{a}</option>
          ))}
        </select>
        <label className="flex items-center gap-2 text-xs text-neutral-300">
          <input
            type="checkbox"
            className="accent-indigo-400"
            checked={project.captions.use_brand}
            onChange={(e) => onChange({ captions: { ...project.captions, use_brand: e.target.checked } })}
          />
          {t("ed.useBrand")}
        </label>
        <label htmlFor="s-cap-text" className="sr-only">
          Caption-Vorschautext
        </label>
        <input
          id="s-cap-text"
          className={inputCls}
          placeholder="Vorschautext"
          value={captionText}
          onChange={(e) => setCaptionText(e.target.value)}
        />
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={studio.captionPreviewUrl(project.captions.style, project.aspect_ratio, sample.slice(0, 80), project.captions.use_brand)}
          alt={`Caption-Vorschau: ${project.captions.style}`}
          className="mx-auto max-h-56 rounded-lg border border-neutral-800"
        />
      </div>

      <div className="space-y-2">
        <label htmlFor="s-voice" className={labelCls}>
          {t("ed.voice")}
        </label>
        <select
          id="s-voice"
          className={inputCls}
          value={project.voice.provider}
          onChange={(e) => onChange({ voice: { ...project.voice, provider: e.target.value, voice_id: null } })}
        >
          <option value="auto">
            {t("ed.voiceAuto")}
            {voices ? ` (${voices.auto_selection.label})` : ""}
          </option>
          {(voices?.providers ?? []).map((p) => (
            <option key={p.id} value={p.id} disabled={p.status !== "ready"}>
              {p.label}
              {p.paid ? ` · ${t("common.paid")}` : ""}
              {p.status !== "ready" ? ` · ${t("status.not_configured")}` : ""}
            </option>
          ))}
        </select>
        {provider && provider.voices.length > 0 && (
          <>
            <label htmlFor="s-voice-id" className="sr-only">
              {t("ed.voice")} ID
            </label>
            <select
              id="s-voice-id"
              className={inputCls}
              value={project.voice.voice_id ?? ""}
              onChange={(e) => onChange({ voice: { ...project.voice, voice_id: e.target.value || null } })}
            >
              <option value="">{t("ed.voiceAuto")}</option>
              {provider.voices.map((v) => (
                <option key={v.id} value={v.id}>
                  {v.label} ({v.tone})
                </option>
              ))}
            </select>
          </>
        )}
        <label htmlFor="s-speed" className={labelCls}>
          {t("ed.speed")}: {project.voice.speed.toFixed(2)}×
        </label>
        <input
          id="s-speed"
          type="range"
          min={0.5}
          max={2}
          step={0.05}
          className="w-full accent-indigo-400"
          value={project.voice.speed}
          onChange={(e) => onChange({ voice: { ...project.voice, speed: Number(e.target.value) } })}
        />
        <label htmlFor="s-vvol" className={labelCls}>
          {t("ed.voiceVolume")}: {Math.round((project.voice.volume ?? 1) * 100)}%
        </label>
        <input
          id="s-vvol"
          type="range"
          min={0}
          max={2}
          step={0.05}
          className="w-full accent-indigo-400"
          value={project.voice.volume ?? 1}
          onChange={(e) => onChange({ voice: { ...project.voice, volume: Number(e.target.value) } })}
        />
        {!usesSpeech && <p className="text-xs text-amber-300">{t("ed.noSpeech")}</p>}
        <button type="button" className={btnCls} onClick={playPreview}>
          ▶ {t("ed.voicePreview")}
        </button>
        {previewUrl && <audio src={previewUrl} controls autoPlay className="w-full" aria-label={t("ed.voicePreview")} />}
      </div>

      <div className="space-y-2">
        <label htmlFor="s-template" className={labelCls}>
          {t("tpl.title")}
          {project.template_id ? ` · ${templates.find((x) => x.id === project.template_id)?.name ?? ""}` : ""}
        </label>
        <select
          id="s-template"
          className={inputCls}
          value={templatePick}
          onChange={(e) => setTemplatePick(e.target.value)}
        >
          <option value="">{t("tpl.none")}</option>
          {templates.map((x) => (
            <option key={x.id} value={x.id}>
              {x.name}
              {x.builtin ? "" : " ★"}
            </option>
          ))}
        </select>
        {pickedTemplate && <p className="text-xs text-neutral-400">{pickedTemplate.description}</p>}
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            className={btnCls}
            disabled={!templatePick || !onApplyTemplate}
            onClick={() => {
              if (templatePick && onApplyTemplate && window.confirm(t("tpl.applyConfirm"))) void onApplyTemplate(templatePick);
            }}
          >
            {t("tpl.apply")}
          </button>
          <button type="button" className={btnCls} onClick={() => void saveAsTemplate()}>
            {t("tpl.saveAs")}
          </button>
          {pickedTemplate && !pickedTemplate.builtin && (
            <button type="button" className={btnCls} onClick={() => void removeTemplate(pickedTemplate.id)}>
              {t("tpl.delete")}
            </button>
          )}
        </div>
        {notice && (
          <p role="status" className="text-xs text-emerald-300">
            {notice}
          </p>
        )}
      </div>

      <div className="space-y-2">
        <label htmlFor="s-transition" className={labelCls}>
          {t("ed.transitionDefault")}
        </label>
        <select
          id="s-transition"
          className={inputCls}
          value={project.transitions?.style ?? "cut"}
          onChange={(e) =>
            onChange({ transitions: { ...(project.transitions ?? { duration: 0.4 }), style: e.target.value as TransitionId } })
          }
        >
          {TRANSITION_IDS.map((id) => (
            <option key={id} value={id}>
              {t(`tr.${id}` as Parameters<typeof t>[0])}
            </option>
          ))}
        </select>
        <label htmlFor="s-tdur" className={labelCls}>
          {t("ed.transitionDuration")}: {(project.transitions?.duration ?? 0.4).toFixed(2)} s
        </label>
        <input
          id="s-tdur"
          type="range"
          min={0.1}
          max={1.5}
          step={0.05}
          className="w-full accent-indigo-400"
          value={project.transitions?.duration ?? 0.4}
          onChange={(e) =>
            onChange({ transitions: { ...(project.transitions ?? { style: "cut" }), duration: Number(e.target.value) } })
          }
        />
      </div>

      <div className="space-y-2">
        <label htmlFor="s-music" className={labelCls}>
          {t("ed.music")}
        </label>
        <select
          id="s-music"
          className={inputCls}
          value={project.music.track ?? ""}
          onChange={(e) => onChange({ music: { ...project.music, track: e.target.value || null } })}
        >
          <option value="">{t("common.none")}</option>
          {tracks.map((tr) => (
            <option key={tr.id} value={`library:${tr.id}`}>
              {tr.name}
            </option>
          ))}
          {audioMedia.map((m) => (
            <option key={m.name} value={`project:${m.name}`}>
              {m.name}
            </option>
          ))}
        </select>
        <label htmlFor="s-vol" className={labelCls}>
          {t("ed.volume")}: {Math.round(project.music.volume * 100)}%
        </label>
        <input
          id="s-vol"
          type="range"
          min={0}
          max={1}
          step={0.05}
          className="w-full accent-indigo-400"
          value={project.music.volume}
          onChange={(e) => onChange({ music: { ...project.music, volume: Number(e.target.value) } })}
        />
        <label className="flex items-center gap-2 text-xs text-neutral-300">
          <input
            type="checkbox"
            className="accent-indigo-400"
            checked={project.music.ducking}
            onChange={(e) => onChange({ music: { ...project.music, ducking: e.target.checked } })}
          />
          {t("ed.ducking")}
        </label>
        <label className="flex items-center gap-2 text-xs text-neutral-300">
          <input
            type="checkbox"
            className="accent-indigo-400"
            checked={project.music.beat_sync}
            onChange={(e) => onChange({ music: { ...project.music, beat_sync: e.target.checked } })}
          />
          {t("ed.beatSync")}
        </label>
      </div>

      <div className="space-y-2">
        <label htmlFor="s-media" className={labelCls}>
          {t("ed.uploadMedia")}
        </label>
        <input
          id="s-media"
          ref={fileRef}
          type="file"
          multiple
          accept="image/png,image/jpeg,image/webp,video/*,audio/*"
          className={inputCls}
          onChange={(e) => onFiles(e.target.files)}
        />
        {upload !== null && <Progress value={upload} label={t("create.uploading")} />}
        {media.length === 0 ? (
          <p className="text-xs text-neutral-400">{t("ed.mediaEmpty")}</p>
        ) : (
          <ul className="space-y-1 text-xs text-neutral-300">
            {media.map((m) => (
              <li key={m.name}>
                <div className="flex items-center justify-between gap-2">
                <span className="truncate">
                  {m.name} <span className="text-neutral-500">({m.kind})</span>
                </span>
                {m.kind !== "audio" && (
                  <button
                    type="button"
                    className="text-neutral-400 underline hover:text-white"
                    aria-expanded={bgTarget === m.name}
                    onClick={() => setBgTarget(bgTarget === m.name ? null : m.name)}
                  >
                    {t("bg.button")}
                  </button>
                )}
                <button
                  type="button"
                  className="text-neutral-400 underline hover:text-white"
                  aria-label={`${t("common.delete")}: ${m.name}`}
                  onClick={async () => {
                    try {
                      await studio.deleteMedia(project.id, m.name);
                      onMediaChanged();
                    } catch (e) {
                      setError(errorMessage(e));
                    }
                  }}
                >
                  {t("common.delete")}
                </button>
                </div>
                {bgTarget === m.name && (
                  <BackgroundTool
                    projectId={project.id}
                    item={m}
                    media={media}
                    onDone={onMediaChanged}
                    onClose={() => setBgTarget(null)}
                  />
                )}
              </li>
            ))}
          </ul>
        )}
        <label htmlFor="s-avatar" className={labelCls}>
          {t("ed.avatarImage")}
        </label>
        <select
          id="s-avatar"
          className={inputCls}
          value={project.visuals.avatar_image ?? ""}
          onChange={(e) => onChange({ visuals: { ...project.visuals, avatar_image: e.target.value || null } })}
        >
          <option value="">{t("common.none")}</option>
          {media
            .filter((m) => m.kind === "image")
            .map((m) => (
              <option key={m.name} value={m.name}>
                {m.name}
              </option>
            ))}
        </select>
        <label htmlFor="s-gameplay" className={labelCls}>
          {t("ed.gameplay")}
        </label>
        <select
          id="s-gameplay"
          className={inputCls}
          value={project.visuals.gameplay_media ?? ""}
          onChange={(e) => onChange({ visuals: { ...project.visuals, gameplay_media: e.target.value || null } })}
        >
          <option value="">{t("common.none")}</option>
          {videoMedia.map((m) => (
            <option key={m.name} value={m.name}>
              {m.name}
            </option>
          ))}
        </select>
      </div>

      <div className="space-y-2">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-neutral-400">{t("opt.title")}</h3>
        <label htmlFor="s-platform" className={labelCls}>
          {t("opt.platform")}
        </label>
        <select
          id="s-platform"
          className={inputCls}
          value={project.options.platform}
          onChange={(e) => onChange({ options: { ...project.options, platform: e.target.value } })}
        >
          {["generic", "youtube_shorts", "tiktok", "instagram_reels", "x"].map((p) => (
            <option key={p}>{p}</option>
          ))}
        </select>
        <label htmlFor="s-forbidden" className={labelCls}>
          {t("opt.forbidden")}
        </label>
        <input
          id="s-forbidden"
          className={inputCls}
          value={project.options.forbidden_topics.join(", ")}
          onChange={(e) =>
            onChange({
              options: {
                ...project.options,
                forbidden_topics: e.target.value.split(",").map((x) => x.trim().toLowerCase()).filter(Boolean),
              },
            })
          }
        />
        <label htmlFor="s-voice-model" className={labelCls}>
          {t("opt.voiceModel")}
        </label>
        <input
          id="s-voice-model"
          className={inputCls}
          value={project.options.voice_model}
          onChange={(e) => onChange({ options: { ...project.options, voice_model: e.target.value } })}
        />
        <label className="flex items-center gap-2 text-xs text-neutral-300">
          <input
            type="checkbox"
            className="accent-indigo-400"
            checked={project.options.image_animation}
            onChange={(e) => onChange({ options: { ...project.options, image_animation: e.target.checked } })}
          />
          {t("opt.imageAnimation")}
        </label>
        <label className="flex items-center gap-2 text-xs text-neutral-300">
          <input
            type="checkbox"
            className="accent-indigo-400"
            checked={project.options.music_mode === "none"}
            onChange={(e) =>
              onChange({ options: { ...project.options, music_mode: e.target.checked ? "none" : "track" } })
            }
          />
          {t("opt.musicNone")}
        </label>
      </div>

      <div className="space-y-1">
        <label htmlFor="s-budget" className={labelCls}>
          {t("ed.budget")}
        </label>
        <input
          id="s-budget"
          type="number"
          min={0}
          step={0.5}
          className={inputCls}
          value={project.budget_limit_usd}
          onChange={(e) => onChange({ budget_limit_usd: Math.max(0, Number(e.target.value) || 0) })}
        />
        <p className="text-xs text-neutral-400">{t("ed.budgetHint")}</p>
        {estimate && (
          <p className={`text-xs ${estimate.within_budget ? "text-neutral-300" : "text-rose-300"}`}>
            {t("ed.cost")}: {estimate.total_usd.toFixed(2)} USD ({t("common.estimate")}) · {estimate.spent_usd.toFixed(2)} USD verbraucht
          </p>
        )}
      </div>
    </aside>
  );
}
