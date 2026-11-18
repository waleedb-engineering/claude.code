"use client";

import { useState } from "react";
import { useT } from "@/lib/i18n";
import { errorMessage, studio, waitForTask, type MediaItem } from "@/lib/studio";
import { btnCls, inputCls, labelCls, primaryCls } from "./ui";

type Props = {
  projectId: string;
  item: MediaItem;
  media: MediaItem[];
  onDone: () => void;
  onClose: () => void;
};

/** Hintergrund entfernen/ersetzen — lokal, kostenlos, Ergebnis als neue Mediendatei. */
export default function BackgroundTool({ projectId, item, media, onDone, onClose }: Props) {
  const t = useT();
  const isVideo = item.kind === "video";
  const [mode, setMode] = useState(isVideo ? "color" : "transparent");
  const [model, setModel] = useState(isVideo ? "bg_person" : "bg_quality");
  const [color, setColor] = useState("#00b140");
  const [background, setBackground] = useState("");
  const [preview, setPreview] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const modes = isVideo ? ["color", "image", "video", "blur"] : ["transparent", "color", "image", "blur"];
  const bgChoices = media.filter((m) => m.name !== item.name && (mode === "video" ? m.kind === "video" : m.kind === "image"));
  const body = { mode, model, color, background: background || undefined };

  async function run(kind: "preview" | "apply") {
    setError(null);
    setBusy(kind === "preview" ? t("bg.previewing") : t("bg.working"));
    try {
      if (kind === "preview") {
        setPreview(await studio.backgroundPreview(projectId, item.name, body));
      } else {
        const task = await studio.startBackground(projectId, item.name, body);
        const done = await waitForTask(task.id, (tk) => setBusy(tk.progress[tk.progress.length - 1] ?? t("bg.working")));
        if (done.status !== "succeeded") throw new Error(done.error?.message ?? t("bg.failed"));
        onDone();
        onClose();
      }
    } catch (e) {
      const msg = errorMessage(e);
      setError(msg);
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="mt-2 space-y-2 rounded-xl border border-neutral-700 p-3" role="group" aria-label={t("bg.title")}>
      <p className="text-xs font-semibold text-neutral-200">
        {t("bg.title")}: {item.name}
      </p>
      <p className="text-[11px] text-neutral-400">{t("bg.hint")}</p>
      <label className={labelCls} htmlFor={`bg-mode-${item.name}`}>
        {t("bg.mode")}
      </label>
      <select id={`bg-mode-${item.name}`} className={inputCls} value={mode} onChange={(e) => setMode(e.target.value)}>
        {modes.map((m) => (
          <option key={m} value={m}>
            {t(`bg.mode.${m}` as Parameters<typeof t>[0])}
          </option>
        ))}
      </select>
      {mode === "color" && (
        <input aria-label={t("bg.color")} type="color" value={color} onChange={(e) => setColor(e.target.value)} />
      )}
      {(mode === "image" || mode === "video") && (
        <select aria-label={t("bg.background")} className={inputCls} value={background} onChange={(e) => setBackground(e.target.value)}>
          <option value="">{t("bg.pick")}</option>
          {bgChoices.map((m) => (
            <option key={m.name} value={m.name}>
              {m.name}
            </option>
          ))}
        </select>
      )}
      <label className={labelCls} htmlFor={`bg-model-${item.name}`}>
        {t("bg.model")}
      </label>
      <select id={`bg-model-${item.name}`} className={inputCls} value={model} onChange={(e) => setModel(e.target.value)}>
        <option value="bg_fast">{t("bg.model.fast")}</option>
        <option value="bg_quality">{t("bg.model.quality")}</option>
        <option value="bg_person">{t("bg.model.person")}</option>
      </select>
      {error && (
        <p role="alert" className="text-xs text-rose-300">
          {error}
          {error.includes("Einrichtung") && (
            <>
              {" "}
              <a className="underline" href="/studio/setup#models">
                {t("bg.openSetup")}
              </a>
            </>
          )}
        </p>
      )}
      {busy && (
        <p role="status" className="text-xs text-indigo-300">
          {busy}
        </p>
      )}
      {preview && (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={preview} alt={t("bg.preview")} className="max-h-48 rounded-lg bg-[repeating-conic-gradient(#333_0_25%,#555_0_50%)] bg-[length:16px_16px]" />
      )}
      <div className="flex flex-wrap gap-2">
        <button type="button" className={btnCls} disabled={!!busy} onClick={() => void run("preview")}>
          {t("bg.preview")}
        </button>
        <button type="button" className={primaryCls} disabled={!!busy} onClick={() => void run("apply")}>
          {isVideo ? t("bg.applyVideo") : t("bg.apply")}
        </button>
        <button type="button" className={btnCls} onClick={onClose}>
          {t("common.cancel")}
        </button>
      </div>
    </div>
  );
}
