"use client";

import { useCallback, useEffect, useState } from "react";
import { StudioApiError, errorMessage, studio, type LibraryItem, type ProjectSummary } from "@/lib/studio";
import { ErrorBox, Progress, btnCls, cardCls, inputCls, labelCls, primaryCls } from "@/components/studio/ui";

const KIND_LABEL: Record<string, string> = {
  video: "Video", image: "Bild", audio: "Audio", music: "Musik", sfx: "Soundeffekt", voice: "Sprachaufnahme",
  generated: "Generiert", brand: "Marke",
};

function size(b: number) {
  return b > 1e6 ? `${(b / 1e6).toFixed(1)} MB` : `${Math.max(1, Math.round(b / 1e3))} KB`;
}

export default function LibraryPage() {
  const [items, setItems] = useState<LibraryItem[] | null>(null);
  const [tags, setTags] = useState<string[]>([]);
  const [q, setQ] = useState("");
  const [kind, setKind] = useState("");
  const [tag, setTag] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [upload, setUpload] = useState<number | null>(null);
  const [meta, setMeta] = useState({ kind: "", tags: "", source: "upload", author: "", url: "", license_name: "", license_url: "" });
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [target, setTarget] = useState("");
  const [selected, setSelected] = useState<LibraryItem | null>(null);

  const load = useCallback(async () => {
    try {
      const d = await studio.library(q, kind, tag);
      setItems(d.items);
      setTags(d.tags);
      setError(null);
    } catch (e) {
      setError(errorMessage(e));
    }
  }, [q, kind, tag]);

  useEffect(() => {
    const t = setTimeout(load, 200);
    return () => clearTimeout(t);
  }, [load]);

  useEffect(() => {
    studio
      .projects()
      .then((p) => {
        setProjects(p);
        if (p[0]) setTarget(p[0].id);
      })
      .catch(() => undefined);
  }, []);

  async function onUpload(files: FileList | null) {
    if (!files?.length) return;
    setError(null);
    setNotice(null);
    for (const f of Array.from(files)) {
      try {
        setUpload(0);
        const item = await studio.libraryUpload(f, Object.fromEntries(Object.entries(meta).filter(([, v]) => v)), setUpload);
        if (item.duplicate) setNotice(`„${f.name}“ ist schon in der Mediathek („${item.name}“) — nicht doppelt gespeichert.`);
      } catch (e) {
        setError(errorMessage(e));
      }
    }
    setUpload(null);
    await load();
  }

  async function remove(stale: LibraryItem) {
    const it = items?.find((x) => x.id === stale.id) ?? stale; // aktuelle Nutzung, nicht die der Detailansicht
    const used = new Set(it.usage.map((u) => u.project_id)).size;
    const ok = window.confirm(
      used
        ? `„${it.name}“ wird in ${used} Projekt(en) verwendet. Die Projekte behalten ihre Kopie. Aus der Mediathek löschen?`
        : `„${it.name}“ aus der Mediathek löschen?`,
    );
    if (!ok) return;
    try {
      await studio.libraryDelete(it.id, used > 0);
    } catch (e) {
      if (e instanceof StudioApiError && e.code === "library_in_use") setError(`${e.message} Bitte erneut löschen.`);
      else setError(errorMessage(e));
      await load();
      return;
    }
    setSelected(null);
    await load();
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-white">Mediathek</h1>
          <p className="text-sm text-neutral-400">Eigene Medien, Musik, Effekte, Sprachaufnahmen, generierte Assets und Marken-Elemente — wiederverwendbar in allen Projekten.</p>
        </div>
      </div>

      <section className={`${cardCls} space-y-3`} aria-label="Hochladen">
        <div className="grid gap-2 sm:grid-cols-4">
          <div>
            <label className={labelCls} htmlFor="lib-kind">
              Art
            </label>
            <select id="lib-kind" className={inputCls} value={meta.kind} onChange={(e) => setMeta({ ...meta, kind: e.target.value })}>
              <option value="">automatisch</option>
              {Object.entries(KIND_LABEL).map(([k, v]) => (
                <option key={k} value={k}>
                  {v}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className={labelCls} htmlFor="lib-tags">
              Tags (Komma)
            </label>
            <input id="lib-tags" className={inputCls} value={meta.tags} onChange={(e) => setMeta({ ...meta, tags: e.target.value })} />
          </div>
          <div>
            <label className={labelCls} htmlFor="lib-source">
              Herkunft
            </label>
            <select id="lib-source" className={inputCls} value={meta.source} onChange={(e) => setMeta({ ...meta, source: e.target.value })}>
              <option value="upload">eigene Datei</option>
              <option value="stock">Stock/Fremdquelle</option>
              <option value="generated">KI-generiert</option>
              <option value="recording">eigene Aufnahme</option>
            </select>
          </div>
          <div>
            <label className={labelCls} htmlFor="lib-file">
              Dateien
            </label>
            <input id="lib-file" type="file" multiple accept="video/*,image/*,audio/*" className="text-sm text-neutral-300" onChange={(e) => {
                const input = e.currentTarget;
                void onUpload(input.files).then(() => {
                  input.value = ""; // gleiche Datei erneut wählbar
                });
              }}
            />
          </div>
        </div>
        {meta.source === "stock" && (
          <div className="grid gap-2 sm:grid-cols-4">
            <input aria-label="Urheber" placeholder="Urheber" className={inputCls} value={meta.author} onChange={(e) => setMeta({ ...meta, author: e.target.value })} />
            <input aria-label="Quelle (URL)" placeholder="Quelle (URL)" className={inputCls} value={meta.url} onChange={(e) => setMeta({ ...meta, url: e.target.value })} />
            <input aria-label="Lizenz" placeholder="Lizenz (z. B. CC0)" className={inputCls} value={meta.license_name} onChange={(e) => setMeta({ ...meta, license_name: e.target.value })} />
            <input aria-label="Lizenz-URL" placeholder="Lizenz-URL" className={inputCls} value={meta.license_url} onChange={(e) => setMeta({ ...meta, license_url: e.target.value })} />
          </div>
        )}
        {upload !== null && <Progress value={upload} label="Hochladen" />}
        {notice && <p className="text-xs text-amber-300">{notice}</p>}
      </section>

      <section className="flex flex-wrap gap-2" aria-label="Filter">
        <input aria-label="Suche" placeholder="Suchen (Name, Tag, Urheber)" className={`${inputCls} max-w-xs`} value={q} onChange={(e) => setQ(e.target.value)} />
        <select aria-label="Art filtern" className={`${inputCls} max-w-[11rem]`} value={kind} onChange={(e) => setKind(e.target.value)}>
          <option value="">alle Arten</option>
          {Object.entries(KIND_LABEL).map(([k, v]) => (
            <option key={k} value={k}>
              {v}
            </option>
          ))}
        </select>
        <select aria-label="Tag filtern" className={`${inputCls} max-w-[11rem]`} value={tag} onChange={(e) => setTag(e.target.value)}>
          <option value="">alle Tags</option>
          {tags.map((t) => (
            <option key={t}>{t}</option>
          ))}
        </select>
      </section>

      {error && <ErrorBox message={error} />}
      {items === null && !error && <p className="text-sm text-neutral-400">Lädt …</p>}
      {items?.length === 0 && <p className={`${cardCls} text-sm text-neutral-400`}>Noch nichts hier — Dateien oben hochladen oder im Editor „In Mediathek“ wählen.</p>}

      <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3" data-testid="library-grid">
        {items?.map((it) => (
          <li key={it.id} className={`${cardCls} space-y-2 ${selected?.id === it.id ? "ring-2 ring-indigo-400" : ""}`}>
            <button type="button" className="block w-full text-left" onClick={() => setSelected(it)} aria-label={`Details ${it.name}`}>
              {it.media_type === "image" && (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={studio.libraryFileUrl(it.id)} alt={it.name} className="h-32 w-full rounded-lg object-cover" />
              )}
              {it.media_type === "video" && <video src={studio.libraryFileUrl(it.id)} className="h-32 w-full rounded-lg object-cover" muted preload="metadata" />}
              {it.media_type === "audio" && <div className="grid h-12 place-items-center rounded-lg bg-neutral-800 text-xs text-neutral-400">♪ Audio</div>}
            </button>
            <p className="truncate text-sm font-medium text-white" title={it.name}>
              {it.name}
            </p>
            <p className="text-xs text-neutral-400">
              {KIND_LABEL[it.kind] ?? it.kind} · {size(it.bytes)}
              {it.duration ? ` · ${it.duration.toFixed(1)} s` : ""}
              {it.usage.length ? ` · in ${new Set(it.usage.map((u) => u.project_id)).size} Projekt(en)` : ""}
            </p>
            {it.tags.length > 0 && <p className="text-xs text-indigo-300">{it.tags.map((t) => `#${t}`).join(" ")}</p>}
          </li>
        ))}
      </ul>

      {selected && (
        <section className={`${cardCls} space-y-2`} aria-label="Details">
          <h2 className="text-sm font-semibold text-white">{selected.name}</h2>
          {selected.media_type === "audio" && <audio src={studio.libraryFileUrl(selected.id)} controls className="w-full" />}
          {selected.media_type === "video" && <video src={studio.libraryFileUrl(selected.id)} controls className="max-h-64 rounded-lg" />}
          <p className="text-xs text-neutral-400">
            Herkunft: {selected.provenance.source}
            {selected.provenance.author ? ` · ${selected.provenance.author}` : ""}
            {selected.provenance.license.name ? ` · Lizenz ${selected.provenance.license.name}` : ""}
            {selected.provenance.url ? (
              <>
                {" · "}
                <a className="underline" href={selected.provenance.url} target="_blank" rel="noreferrer">
                  Quelle
                </a>
              </>
            ) : null}
            {" · SHA-256 "}
            {selected.sha256.slice(0, 12)}…
          </p>
          <div className="flex flex-wrap items-end gap-2">
            <div>
              <label className={labelCls} htmlFor="lib-target">
                In Projekt verwenden
              </label>
              <select id="lib-target" className={inputCls} value={target} onChange={(e) => setTarget(e.target.value)}>
                {projects.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.title}
                  </option>
                ))}
              </select>
            </div>
            <button
              type="button"
              className={primaryCls}
              disabled={!target}
              onClick={async () => {
                try {
                  const r = await studio.libraryUse(selected.id, target);
                  setNotice(`In das Projekt kopiert als „${r.media.name}“.`);
                  await load();
                  setSelected({ ...selected, usage: [...selected.usage, { project_id: target, media: r.media.name, at: new Date().toISOString() }] });
                } catch (e) {
                  setError(errorMessage(e));
                }
              }}
            >
              Verwenden
            </button>
            <button
              type="button"
              className={btnCls}
              onClick={async () => {
                const t = window.prompt("Tags (Komma-getrennt)", selected.tags.join(", "));
                if (t === null) return;
                try {
                  setSelected(await studio.libraryPatch(selected.id, { tags: t.split(",") }));
                  await load();
                } catch (e) {
                  setError(errorMessage(e));
                }
              }}
            >
              Tags bearbeiten
            </button>
            <button type="button" className={btnCls} onClick={() => void remove(selected)}>
              Löschen
            </button>
          </div>
        </section>
      )}
    </div>
  );
}
