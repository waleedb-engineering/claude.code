"use client";

import { useState } from "react";
import { errorMessage, studio, type RenderReport } from "@/lib/studio";
import { btnCls } from "./ui";

const ICON: Record<string, string> = { ok: "✓", warn: "⚠", fail: "✗" };
const COLOR: Record<string, string> = { ok: "text-emerald-400", warn: "text-amber-300", fail: "text-red-400" };

/** Automatische Ausgabeprüfung + menschliche Review-Stufe für einen Render. */
export default function RenderQuality({ projectId, render, onSaved }: { projectId: string; render: RenderReport; onSaved: () => void }) {
  const oc = render.output_checks;
  const items = oc?.review_items ?? {};
  const [open, setOpen] = useState(false);
  const [check, setCheck] = useState<Record<string, boolean>>(render.review?.checklist ?? {});
  const [note, setNote] = useState(render.review?.note ?? "");
  const [error, setError] = useState<string | null>(null);
  if (!oc || !oc.checks?.length) return null;
  async function save(verdict: "approved" | "changes_requested") {
    setError(null);
    try {
      await studio.reviewRender(projectId, render.render_id, { checklist: check, verdict, note });
      setOpen(false);
      onSaved();
    } catch (e) {
      setError(errorMessage(e));
    }
  }
  return (
    <div className="space-y-1 rounded-lg border border-neutral-800 p-2 text-xs" aria-label="Qualitätsprüfung" data-testid="render-quality">
      <p className="font-medium text-neutral-200">
        Prüfung: {oc.passed ? "bestanden" : "Fehler gefunden"}
        {oc.warnings ? ` · ${oc.warnings} Hinweis(e)` : ""}
        {render.review ? ` · Review: ${render.review.verdict === "approved" ? "freigegeben ✓" : "Änderungen gewünscht"}` : " · Review offen"}
      </p>
      <ul>
        {oc.checks.map((c) => (
          <li key={c.id} className={COLOR[c.level]}>
            {ICON[c.level]} {c.message}
          </li>
        ))}
      </ul>
      <button type="button" className={btnCls} onClick={() => setOpen((o) => !o)}>
        {open ? "Review schließen" : "Menschliche Review"}
      </button>
      {open && (
        <div className="space-y-1 pt-1">
          {Object.entries(items).map(([k, label]) => (
            <label key={k} className="flex items-center gap-2 text-neutral-300">
              <input type="checkbox" checked={!!check[k]} onChange={(e) => setCheck({ ...check, [k]: e.target.checked })} />
              {label}
            </label>
          ))}
          <textarea aria-label="Review-Notiz" className="w-full rounded border border-neutral-700 bg-neutral-950 p-1 text-neutral-200" value={note} onChange={(e) => setNote(e.target.value)} />
          <div className="flex gap-2">
            <button type="button" className={btnCls} onClick={() => void save("approved")}>
              Freigeben
            </button>
            <button type="button" className={btnCls} onClick={() => void save("changes_requested")}>
              Änderungen nötig
            </button>
          </div>
          {error && <p className="text-red-400">{error}</p>}
        </div>
      )}
    </div>
  );
}
