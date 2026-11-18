"use client";

import { useCallback, useEffect, useState } from "react";
import { useLocale, useT } from "@/lib/i18n";
import { errorMessage, studio } from "@/lib/studio";
import AudioRecorder from "./AudioRecorder";
import { ErrorBox, btnCls, cardCls, inputCls, labelCls, primaryCls } from "./ui";

type Clone = { id: string; name: string; voice_id: string; created_at: string; consent: { basis: string; speaker: string } };

export default function VoiceCloneSection() {
  const t = useT();
  const locale = useLocale();
  const [clones, setClones] = useState<Clone[]>([]);
  const [enabled, setEnabled] = useState(false);
  const [name, setName] = useState("");
  const [basis, setBasis] = useState<"own" | "permission" | "">("");
  const [speaker, setSpeaker] = useState("");
  const [noDeception, setNoDeception] = useState(false);
  const [files, setFiles] = useState<File[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [preview, setPreview] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const data = await studio.clones();
      setClones(data.clones);
      setEnabled(data.enabled);
    } catch (e) {
      setError(errorMessage(e));
    }
  }, []);

  useEffect(() => {
    const first = setTimeout(load, 0);
    return () => clearTimeout(first);
  }, [load]);

  if (!enabled) return null;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const form = new FormData();
      form.append("name", name);
      form.append("basis", basis);
      form.append("speaker", speaker);
      form.append("no_deception", String(noDeception));
      files.forEach((f) => form.append("files", f));
      await studio.createClone(form);
      setName("");
      setFiles([]);
      await load();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section aria-labelledby="vc-h" className={`${cardCls} space-y-3`}>
      <h2 id="vc-h" className="text-lg font-semibold text-white">
        {t("vc.title")}
      </h2>
      <p className="text-xs text-neutral-300">{t("vc.hint")}</p>
      <ErrorBox message={error} />
      {clones.length === 0 ? (
        <p className="text-sm text-neutral-400">{t("vc.none")}</p>
      ) : (
        <ul className="space-y-1 text-sm text-neutral-200">
          {clones.map((c) => (
            <li key={c.id} className="flex items-center justify-between gap-3">
              <span>
                {c.name} <span className="text-xs text-neutral-500">({c.consent.speaker})</span>
              </span>
              <button
                type="button"
                className={btnCls}
                onClick={async () => {
                  if (!window.confirm(t("vc.previewCost"))) return;
                  setError(null);
                  try {
                    setPreview(await studio.voicePreview(locale, "elevenlabs", c.voice_id, true));
                  } catch (err) {
                    setError(errorMessage(err));
                  }
                }}
              >
                ▶ {t("ed.voicePreview")}
              </button>
              <button
                type="button"
                className={btnCls}
                onClick={async () => {
                  try {
                    await studio.deleteClone(c.id);
                    await load();
                  } catch (err) {
                    setError(errorMessage(err));
                  }
                }}
              >
                {t("common.delete")}
              </button>
            </li>
          ))}
        </ul>
      )}
      {preview && <audio src={preview} controls autoPlay className="w-full" aria-label={t("ed.voicePreview")} />}
      <p className="text-[11px] text-neutral-400">{t("vc.languages")}</p>
      <form onSubmit={submit} className="space-y-3">
        <div>
          <label htmlFor="vc-name" className={labelCls}>
            {t("vc.name")}
          </label>
          <input id="vc-name" required className={inputCls} value={name} onChange={(e) => setName(e.target.value)} />
        </div>
        <div>
          <label htmlFor="vc-files" className={labelCls}>
            {t("vc.samples")}
          </label>
          <input
            id="vc-files"
            type="file"
            multiple
            accept="audio/*"
            className={inputCls}
            onChange={(e) => setFiles((prev) => [...prev, ...Array.from(e.target.files ?? [])].slice(0, 5))}
          />
          <div className="mt-2">
            <AudioRecorder onRecorded={(f) => setFiles((prev) => [...prev, f].slice(0, 5))} />
          </div>
          {files.length > 0 && (
            <ul className="mt-2 space-y-1 text-xs text-neutral-300">
              {files.map((f, i) => (
                <li key={`${f.name}-${i}`} className="flex items-center justify-between gap-2">
                  <span className="truncate">
                    {f.name} ({Math.round(f.size / 1024)} KB)
                  </span>
                  <button
                    type="button"
                    className="underline"
                    onClick={() => setFiles((prev) => prev.filter((_, j) => j !== i))}
                  >
                    {t("common.delete")}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
        <fieldset className="space-y-2 text-sm text-neutral-200">
          <label className="flex items-start gap-2">
            <input type="radio" name="vc-basis" className="mt-1 accent-indigo-400" checked={basis === "own"} onChange={() => setBasis("own")} />
            {t("vc.own")}
          </label>
          <label className="flex items-start gap-2">
            <input
              type="radio"
              name="vc-basis"
              className="mt-1 accent-indigo-400"
              checked={basis === "permission"}
              onChange={() => setBasis("permission")}
            />
            {t("vc.permission")}
          </label>
          {basis === "permission" && (
            <div>
              <label htmlFor="vc-speaker" className={labelCls}>
                {t("vc.speaker")}
              </label>
              <input id="vc-speaker" required className={inputCls} value={speaker} onChange={(e) => setSpeaker(e.target.value)} />
            </div>
          )}
          <label className="flex items-start gap-2">
            <input type="checkbox" className="mt-1 accent-indigo-400" checked={noDeception} onChange={(e) => setNoDeception(e.target.checked)} />
            {t("vc.noDeception")}
          </label>
        </fieldset>
        <button type="submit" className={primaryCls} disabled={busy || !basis || !noDeception || files.length === 0}>
          {t("vc.create")}
        </button>
      </form>
    </section>
  );
}
