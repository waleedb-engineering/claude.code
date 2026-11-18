"use client";

import { useState } from "react";
import { useT } from "@/lib/i18n";
import { errorMessage, studio, type BrollHit } from "@/lib/studio";
import { btnCls, inputCls } from "./ui";

type Props = {
  projectId: string;
  sceneId: string;
  onPick: (mediaName: string) => void;
  onMediaAdded: () => void;
};

/** B-Roll-Vorschläge für eine Szene: eigene Mediathek zuerst, Stock optional. */
export default function BrollPicker({ projectId, sceneId, onPick, onMediaAdded }: Props) {
  const t = useT();
  const [open, setOpen] = useState(false);
  const [data, setData] = useState<Awaited<ReturnType<typeof studio.brollSuggest>> | null>(null);
  const [stock, setStock] = useState("");
  const [kind, setKind] = useState("video");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function load(withStock: string) {
    setBusy(true);
    setError(null);
    try {
      setData(await studio.brollSuggest(projectId, sceneId, withStock || undefined, kind));
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  async function take(hit: BrollHit) {
    if (hit.source === "library" && hit.name) {
      onPick(hit.name);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const res = await studio.brollImport(projectId, hit, data?.query ?? "");
      onMediaAdded();
      onPick(res.name);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  if (!open) {
    return (
      <button
        type="button"
        className={btnCls}
        onClick={() => {
          setOpen(true);
          void load("");
        }}
      >
        🎞 {t("broll.find")}
      </button>
    );
  }

  return (
    <div className="space-y-2 rounded-xl border border-neutral-700 p-3" role="group" aria-label={t("broll.title")}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs font-semibold text-neutral-200">{t("broll.title")}</p>
        <button type="button" className="text-xs text-neutral-400 underline" onClick={() => setOpen(false)}>
          {t("common.close")}
        </button>
      </div>
      {data && <p className="text-[11px] text-neutral-400">{t("broll.keywords")}: {data.keywords.join(", ") || "–"}</p>}
      {error && (
        <p role="alert" className="text-xs text-rose-300">
          {error}
        </p>
      )}
      {busy && <p role="status" className="text-xs text-indigo-300">…</p>}
      <ul className="space-y-1 text-xs">
        {(data?.library ?? []).map((h) => (
          <li key={h.name} className="flex items-center justify-between gap-2">
            <span className="truncate text-neutral-200">
              {h.name} <span className="text-neutral-500">({h.matched?.join(", ")})</span>
            </span>
            <button type="button" className={btnCls} onClick={() => void take(h)}>
              {t("broll.use")}
            </button>
          </li>
        ))}
        {data && data.library.length === 0 && <li className="text-neutral-400">{t("broll.noLibrary")}</li>}
      </ul>
      <div className="flex flex-wrap items-center gap-2">
        <select aria-label={t("broll.stock")} className={inputCls} value={stock} onChange={(e) => setStock(e.target.value)}>
          <option value="">{t("broll.stockNone")}</option>
          {(data?.stock_available ?? []).map((s) => (
            <option key={s} value={s}>
              {s === "pexels" ? "Pexels" : "Pixabay"}
            </option>
          ))}
        </select>
        <select aria-label={t("broll.kind")} className={inputCls} value={kind} onChange={(e) => setKind(e.target.value)}>
          <option value="video">{t("broll.video")}</option>
          <option value="image">{t("broll.image")}</option>
        </select>
        <button type="button" className={btnCls} disabled={!stock || busy} onClick={() => void load(stock)}>
          {t("broll.search")}
        </button>
      </div>
      {data && data.stock_available.length === 0 && <p className="text-[11px] text-neutral-400">{t("broll.stockHint")}</p>}
      <ul className="grid grid-cols-3 gap-2">
        {(data?.stock ?? []).map((h) => (
          <li key={`${h.source}-${h.id}`} className="space-y-1">
            {h.preview && (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={h.preview} alt={`${h.source} ${h.id}`} className="aspect-[9/16] w-full rounded object-cover" />
            )}
            <p className="truncate text-[10px] text-neutral-400">
              {h.author} · {h.license?.name}
            </p>
            <button type="button" className={btnCls} disabled={busy} onClick={() => void take(h)}>
              {t("broll.import")}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
