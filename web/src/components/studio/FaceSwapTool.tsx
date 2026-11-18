"use client";

import { useEffect, useState } from "react";
import { useT } from "@/lib/i18n";
import { errorMessage, studio, waitForTask, type MediaItem } from "@/lib/studio";
import { btnCls, inputCls, primaryCls } from "./ui";

/** Face Swap auf ein Medium — nur mit registriertem Referenzgesicht, Ergebnis gekennzeichnet. */
export default function FaceSwapTool({ projectId, item, onDone, onClose }: { projectId: string; item: MediaItem; onDone: () => void; onClose: () => void }) {
  const t = useT();
  const [faces, setFaces] = useState<{ id: string; name: string }[] | null>(null);
  const [reason, setReason] = useState("");
  const [faceId, setFaceId] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const first = setTimeout(async () => {
      try {
        const d = await studio.faces();
        setFaces(d.faces);
        setReason(d.enabled ? "" : d.reason);
      } catch (e) {
        setError(errorMessage(e));
      }
    }, 0);
    return () => clearTimeout(first);
  }, []);

  async function run() {
    setError(null);
    try {
      let task;
      try {
        task = await studio.faceSwap(projectId, item.name, faceId, false);
      } catch (e) {
        const msg = errorMessage(e);
        if (!msg.includes("USD") || !window.confirm(`${msg}\n\n${t("fs.confirmLabel")}`)) throw e;
        task = await studio.faceSwap(projectId, item.name, faceId, true);
      }
      setBusy(t("bg.working"));
      const done = await waitForTask(task.id, (tk) => setBusy(tk.progress[tk.progress.length - 1] ?? t("bg.working")));
      if (done.status !== "succeeded") throw new Error(done.error?.message ?? t("bg.failed"));
      onDone();
      onClose();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="mt-2 space-y-2 rounded-xl border border-neutral-700 p-3" role="group" aria-label={t("fs.swap")}>
      <p className="text-xs font-semibold text-neutral-200">
        {t("fs.swap")}: {item.name}
      </p>
      <p className="text-[11px] text-neutral-400">{t("fs.swapHint")}</p>
      {reason && <p className="text-xs text-amber-300">{reason}</p>}
      {faces && faces.length === 0 && !reason && <p className="text-xs text-amber-300">{t("fs.needFace")}</p>}
      {faces && faces.length > 0 && (
        <select aria-label={t("fs.name")} className={inputCls} value={faceId} onChange={(e) => setFaceId(e.target.value)}>
          <option value="">{t("pub.choose")}</option>
          {faces.map((f) => (
            <option key={f.id} value={f.id}>
              {f.name}
            </option>
          ))}
        </select>
      )}
      {error && (
        <p role="alert" className="text-xs text-rose-300">
          {error}
        </p>
      )}
      {busy && <p className="text-xs text-indigo-300">{busy}</p>}
      <div className="flex gap-2">
        <button type="button" className={primaryCls} disabled={!faceId || !!busy} onClick={() => void run()}>
          {t("fs.start")}
        </button>
        <button type="button" className={btnCls} onClick={onClose}>
          {t("common.cancel")}
        </button>
      </div>
    </div>
  );
}
