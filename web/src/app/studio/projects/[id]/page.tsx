"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { useLocale, useT } from "@/lib/i18n";
import {
  StudioApiError,
  errorMessage,
  studio,
  waitForTask,
  type Estimate,
  type Project,
  type ProjectView,
  type QualityCheck,
  type Scene,
  type Task,
} from "@/lib/studio";
import SceneCard from "@/components/studio/SceneCard";
import SettingsPanel from "@/components/studio/SettingsPanel";
import SocialCopyPanel from "@/components/studio/SocialCopyPanel";
import AgentChat from "@/components/studio/AgentChat";
import Timeline from "@/components/studio/Timeline";
import { ErrorBox, Loading, Notice, Pill, btnCls, cardCls, fmtDate, inputCls, primaryCls } from "@/components/studio/ui";

const AUTOSAVE_MS = 1200;
const HISTORY_LIMIT = 60;

function newSceneId(): string {
  const bytes = new Uint8Array(6);
  crypto.getRandomValues(bytes);
  return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
}

function editable(p: Project): Record<string, unknown> {
  return {
    title: p.title,
    language: p.language,
    style: p.style,
    aspect_ratio: p.aspect_ratio,
    resolution: p.resolution,
    scenes: p.scenes,
    voice: p.voice,
    music: p.music,
    captions: p.captions,
    visuals: p.visuals,
    options: p.options,
    transitions: p.transitions,
    audio: p.audio,
    budget_limit_usd: p.budget_limit_usd,
  };
}

export default function EditorPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const t = useT();
  const locale = useLocale();

  const [project, setProject] = useState<Project | null>(null);
  const [view, setView] = useState<Omit<ProjectView, "project"> | null>(null);
  const [past, setPast] = useState<Project[]>([]);
  const [future, setFuture] = useState<Project[]>([]);
  const [saveState, setSaveState] = useState<"saved" | "dirty" | "saving">("saved");
  const [conflict, setConflict] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeTask, setActiveTask] = useState<Task | null>(null);
  const [quality, setQuality] = useState<QualityCheck[] | null>(null);
  const [estimate, setEstimate] = useState<Estimate | null>(null);
  const [scriptMode, setScriptMode] = useState(false);
  const [scriptText, setScriptText] = useState("");
  const [versions, setVersions] = useState<{ version: number; updated_at: string; scene_count: number }[] | null>(null);

  const projectRef = useRef<Project | null>(null);
  const editCount = useRef(0);
  const dirty = useRef(false);
  const saving = useRef<Promise<boolean> | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const saveRef = useRef<(() => Promise<boolean>) | null>(null);
  const [thumbs, setThumbs] = useState<Record<string, { file: string; t: number; score: number; reasons: string[] }[]>>({});

  const applyServer = useCallback((p: Project) => {
    projectRef.current = p;
    setProject(p);
  }, []);

  const refresh = useCallback(
    async (takeProject: boolean) => {
      try {
        const v = await studio.project(id);
        setView({ tasks: v.tasks, renders: v.renders, media: v.media, artifacts: v.artifacts });
        if (takeProject) applyServer(v.project);
        const [q, e] = await Promise.all([studio.quality(id), studio.estimate(id)]);
        setQuality(q.checks);
        setEstimate(e);
        return v;
      } catch (e) {
        setError(errorMessage(e));
        return null;
      }
    },
    [id, applyServer],
  );

  // Erstes Laden + laufende Ingest-Aufgabe weiterverfolgen
  useEffect(() => {
    const signal = { cancelled: false };
    (async () => {
      const v = await refresh(true);
      const running = v?.tasks.find((tk) => tk.status === "queued" || tk.status === "running");
      if (running) {
        setActiveTask(running);
        await waitForTask(running.id, setActiveTask, signal);
        if (!signal.cancelled) {
          setActiveTask(null);
          await refresh(true);
        }
      }
    })();
    return () => {
      signal.cancelled = true;
    };
  }, [refresh]);

  const save = useCallback(async (): Promise<boolean> => {
    if (saving.current) await saving.current;
    const current = projectRef.current;
    if (!current || conflict) return false;
    const startedAt = editCount.current;
    setSaveState("saving");
    const run = (async () => {
      try {
        const saved = await studio.patchProject(id, { expected_version: current.version, ...editable(current) });
        const latest = projectRef.current;
        if (latest && editCount.current === startedAt) {
          applyServer(saved);
          dirty.current = false;
          setSaveState("saved");
        } else if (latest) {
          // währenddessen weiter getippt: nur die Version übernehmen
          applyServer({ ...latest, version: saved.version });
          setSaveState("dirty");
        }
        setError(null);
        return true;
      } catch (e) {
        if (e instanceof StudioApiError && e.code === "version_conflict") setConflict(true);
        else setError(errorMessage(e));
        setSaveState("dirty");
        return false;
      }
    })();
    saving.current = run;
    const ok = await run;
    saving.current = null;
    return ok;
  }, [id, conflict, applyServer]);

  /** Wartet, bis alle lokalen Änderungen im Backend liegen (vor Render/Regeneration). */
  useEffect(() => {
    saveRef.current = save;
  }, [save]);

  const flush = useCallback(async (): Promise<boolean> => {
    if (timer.current) clearTimeout(timer.current);
    if (saving.current) await saving.current;
    for (let i = 0; i < 5 && dirty.current; i++) {
      if (!(await save())) return false;
    }
    return !dirty.current;
  }, [save]);

  // Autosave (entprellt)
  useEffect(() => {
    if (saveState !== "dirty" || conflict) return;
    timer.current = setTimeout(() => {
      void save().then((ok) => {
        if (ok) void refresh(false);
      });
    }, AUTOSAVE_MS);
    return () => {
      if (timer.current) clearTimeout(timer.current);
    };
  }, [saveState, project, conflict, save, refresh]);

  const edit = useCallback((fn: (p: Project) => Project) => {
    const current = projectRef.current;
    if (!current) return;
    const next = fn(current);
    setPast((h) => [...h.slice(-HISTORY_LIMIT + 1), current]);
    setFuture([]);
    editCount.current += 1;
    projectRef.current = next;
    setProject(next);
    dirty.current = true;
    setSaveState("dirty");
  }, []);

  const undo = useCallback(() => {
    const current = projectRef.current;
    if (!current || past.length === 0) return;
    const prev = { ...past[past.length - 1], version: current.version };
    setPast((h) => h.slice(0, -1));
    setFuture((f) => [current, ...f]);
    editCount.current += 1;
    projectRef.current = prev;
    setProject(prev);
    dirty.current = true;
    setSaveState("dirty");
  }, [past]);

  const redo = useCallback(() => {
    const current = projectRef.current;
    if (!current || future.length === 0) return;
    const next = { ...future[0], version: current.version };
    setFuture((f) => f.slice(1));
    setPast((h) => [...h, current]);
    editCount.current += 1;
    projectRef.current = next;
    setProject(next);
    dirty.current = true;
    setSaveState("dirty");
  }, [future]);

  // Tastatur: Strg/Cmd+S speichern (überall), Strg/Cmd+Z / +Shift+Z bzw. +Y außerhalb von Textfeldern
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (!(e.ctrlKey || e.metaKey)) return;
      const key = e.key.toLowerCase();
      if (key === "s") {
        e.preventDefault();
        void saveRef.current?.();
        return;
      }
      const tag = (e.target as HTMLElement | null)?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
      if (key === "y") {
        e.preventDefault();
        redo();
        return;
      }
      if (key !== "z") return;
      e.preventDefault();
      if (e.shiftKey) redo();
      else undo();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [undo, redo]);

  // Ungespeichertes beim Verlassen schützen
  useEffect(() => {
    function onLeave(e: BeforeUnloadEvent) {
      if (dirty.current) e.preventDefault();
    }
    window.addEventListener("beforeunload", onLeave);
    return () => window.removeEventListener("beforeunload", onLeave);
  }, []);

  const setScenes = (fn: (scenes: Scene[]) => Scene[]) => edit((p) => ({ ...p, scenes: fn(p.scenes) }));

  async function runTask(start: () => Promise<Task>) {
    setError(null);
    if (!(await flush())) return;
    try {
      const task = await start();
      setActiveTask(task);
      const done = await waitForTask(task.id, setActiveTask);
      setActiveTask(null);
      if (done.status !== "succeeded" && done.error) setError(done.error.message);
      await refresh(false);
    } catch (e) {
      setActiveTask(null);
      setError(errorMessage(e));
      await refresh(false);
    }
  }

  async function regenerate(sceneId: string) {
    setError(null);
    if (!(await flush())) return;
    const current = projectRef.current;
    if (!current) return;
    try {
      const res = await studio.regenerateScene(id, sceneId, current.version);
      applyServer(res.project);
      setActiveTask(res.task);
      const done = await waitForTask(res.task.id, setActiveTask);
      setActiveTask(null);
      if (done.status !== "succeeded" && done.error) setError(done.error.message);
      await refresh(false);
    } catch (e) {
      setActiveTask(null);
      if (e instanceof StudioApiError && e.code === "version_conflict") setConflict(true);
      else setError(errorMessage(e));
    }
  }

  async function autoBroll() {
    setError(null);
    if (!(await flush())) return;
    const cur = projectRef.current;
    try {
      const task = await studio.brollAuto(id);
      setActiveTask(task);
      const done = await waitForTask(task.id, setActiveTask);
      setActiveTask(null);
      if (done.status !== "succeeded" && done.error) setError(done.error.message);
      if (cur) {
        setPast((h) => [...h.slice(-49), cur]); // Rückgängig möglich
        setFuture([]);
      }
      await refresh(true);
    } catch (e) {
      setActiveTask(null);
      setError(errorMessage(e));
    }
  }

  async function reload() {
    setConflict(false);
    setPast([]);
    setFuture([]);
    dirty.current = false;
    setSaveState("saved");
    await refresh(true);
  }

  if (!project) {
    return (
      <div className="space-y-4">
        <ErrorBox message={error} />
        {!error && <Loading />}
        <Link href="/studio" className={btnCls}>
          {t("ed.back")}
        </Link>
      </div>
    );
  }

  const busy = activeTask !== null;
  const blocking = (quality ?? []).filter((c) => c.level === "fail");
  const finalRender = view?.renders.find((r) => r.mode === "final");
  const lastExport = project.exports[project.exports.length - 1];
  const failedTask = view?.tasks.find((tk) => tk.status === "failed" || tk.status === "interrupted");

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Link href="/studio" className="text-sm text-neutral-300 hover:text-white">
          {t("ed.back")}
        </Link>
        <div className="flex flex-wrap items-center gap-2">
          <span role="status" aria-live="polite" className="text-xs text-neutral-300">
            {saveState === "saved" ? `✓ ${t("ed.saved")}` : saveState === "saving" ? t("ed.saving") : t("ed.unsaved")}
            {" · v"}
            {project.version}
          </span>
          <button type="button" className={btnCls} onClick={undo} disabled={past.length === 0}>
            ↶ {t("ed.undo")}
          </button>
          <button type="button" className={btnCls} onClick={redo} disabled={future.length === 0}>
            ↷ {t("ed.redo")}
          </button>
          <button type="button" className={btnCls} onClick={() => void save()} disabled={saveState !== "dirty" || conflict}>
            {t("common.save")}
          </button>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <label htmlFor="ed-title" className="sr-only">
          Titel
        </label>
        <input
          id="ed-title"
          className={`${inputCls} max-w-xl text-lg font-semibold`}
          value={project.title}
          maxLength={120}
          onChange={(e) => edit((p) => ({ ...p, title: e.target.value }))}
        />
        <Pill status={project.status} />
      </div>

      {conflict && (
        <ErrorBox message={t("ed.conflict")}>
          <button type="button" className={`${btnCls} ml-3`} onClick={reload}>
            {t("common.reload")}
          </button>
        </ErrorBox>
      )}
      <ErrorBox message={error} />
      {project.status === "failed" && project.status_error && (
        <ErrorBox message={project.status_error.message}>
          <button type="button" className={`${btnCls} ml-3`} onClick={() => runTask(() => studio.ingest(id)).then(() => refresh(true))}>
            {t("ed.reingest")}
          </button>
        </ErrorBox>
      )}
      {failedTask && project.status !== "failed" && !busy && (
        <Notice>
          {failedTask.kind}: {failedTask.error?.message}{" "}
          <button type="button" className={`${btnCls} ml-2`} onClick={() => runTask(() => studio.retryTask(failedTask.id))}>
            {t("common.retry")}
          </button>
        </Notice>
      )}
      {(project.script.notes ?? []).map((n) => (
        <Notice key={n}>{n}</Notice>
      ))}
      {typeof project.lineage.originality_notice === "string" && <Notice>{project.lineage.originality_notice}</Notice>}
      {activeTask && (
        <Notice>
          <span role="status" aria-live="polite">
            <Pill status={activeTask.status} /> {activeTask.progress[activeTask.progress.length - 1] ?? activeTask.kind}
          </span>
        </Notice>
      )}

      {project.linked_job_id && project.scenes.length === 0 ? (
        <div className={`${cardCls} space-y-3 text-sm text-neutral-200`}>
          <p>{t("ed.linkedJob")}</p>
          <Link href={`/jobs/${project.linked_job_id}`} className={primaryCls}>
            {t("dash.shorts_job")}
          </Link>
        </div>
      ) : (
        <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_20rem]">
          <div className="space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h2 className="text-lg font-semibold text-white">
                {t("ed.scenes")} ({project.scenes.length})
              </h2>
              <button
                type="button"
                className={btnCls}
                onClick={() => {
                  if (!scriptMode) setScriptText(project.scenes.map((s) => s.text).join("\n\n"));
                  setScriptMode(!scriptMode);
                }}
              >
                {scriptMode ? t("ed.sceneMode") : t("ed.scriptMode")}
              </button>
            </div>

            {scriptMode ? (
              <div className={`${cardCls} space-y-3`}>
                <label htmlFor="ed-script" className="text-xs text-neutral-300">
                  {t("ed.scriptHint")}
                </label>
                <textarea
                  id="ed-script"
                  className={`${inputCls} min-h-80 font-mono`}
                  value={scriptText}
                  onChange={(e) => setScriptText(e.target.value)}
                />
                <button
                  type="button"
                  className={primaryCls}
                  onClick={() => {
                    const blocks = scriptText
                      .split(/\n\s*\n/)
                      .map((b) => b.replace(/\s+/g, " ").trim())
                      .filter(Boolean);
                    setScenes((scenes) =>
                      blocks.map((text, i) =>
                        scenes[i]
                          ? { ...scenes[i], text }
                          : {
                              id: newSceneId(),
                              kind: "body",
                              text,
                              voice_text: null,
                              visual_prompt: "",
                              headline: "",
                              duration: null,
                              pause_after: 0,
                              visual: { mode: "motion", media: null, color: null, seed: i },
                            },
                      ),
                    );
                    setScriptMode(false);
                  }}
                >
                  {t("ed.apply")}
                </button>
              </div>
            ) : (
              <>
                {project.scenes.length === 0 && <p className={`${cardCls} text-sm text-neutral-300`}>{t("ed.empty")}</p>}
                {project.scenes.length > 0 && (
                  <Timeline
                    scenes={project.scenes}
                    onSelect={(i) => document.querySelectorAll("#scene-list > li")[i]?.scrollIntoView({ behavior: "smooth", block: "center" })}
                    onMove={(from, to) =>
                      setScenes((sc) => {
                        const next = [...sc];
                        const [moved] = next.splice(from, 1);
                        next.splice(to, 0, moved);
                        return next;
                      })
                    }
                  />
                )}
                <ol id="scene-list" className="space-y-3">
                  {project.scenes.map((scene, i) => (
                    <SceneCard
                      key={scene.id}
                      scene={scene}
                      index={i}
                      count={project.scenes.length}
                      media={view?.media ?? []}
                      busy={busy}
                      flagged={(quality ?? []).filter((c) => c.scene_id === scene.id && c.level !== "ok").map((c) => c.message)}
                      onChange={(patch) => setScenes((sc) => sc.map((s) => (s.id === scene.id ? { ...s, ...patch } : s)))}
                      onMove={(delta) =>
                        setScenes((sc) => {
                          const next = [...sc];
                          const j = i + delta;
                          if (j < 0 || j >= next.length) return sc;
                          [next[i], next[j]] = [next[j], next[i]];
                          return next;
                        })
                      }
                      onDuplicate={() =>
                        setScenes((sc) => [...sc.slice(0, i + 1), { ...scene, id: newSceneId() }, ...sc.slice(i + 1)])
                      }
                      onDelete={() => setScenes((sc) => sc.filter((s) => s.id !== scene.id))}
                      onRegenerate={() => regenerate(scene.id)}
                      projectId={id}
                      onMediaAdded={() => void refresh(false)}
                      dragProps={{
                        draggable: true,
                        onDragStart: (e) => {
                          // Ziehen nur am Kartenrand, nicht beim Markieren von Text in Feldern
                          const tag = (e.target as HTMLElement).tagName;
                          if (tag === "TEXTAREA" || tag === "INPUT" || tag === "SELECT") {
                            e.preventDefault();
                            return;
                          }
                          e.dataTransfer.setData("text/clipforge-scene", String(i));
                          e.dataTransfer.effectAllowed = "move";
                        },
                        onDragOver: (e) => {
                          if (e.dataTransfer.types.includes("text/clipforge-scene")) e.preventDefault();
                        },
                        onDrop: (e) => {
                          const from = Number(e.dataTransfer.getData("text/clipforge-scene"));
                          if (!Number.isInteger(from) || from === i) return;
                          e.preventDefault();
                          setScenes((sc) => {
                            const next = [...sc];
                            const [moved] = next.splice(from, 1);
                            next.splice(i, 0, moved);
                            return next;
                          });
                        },
                      }}
                    />
                  ))}
                </ol>
                <button
                  type="button"
                  className={btnCls}
                  onClick={() =>
                    setScenes((sc) => [
                      ...sc,
                      {
                        id: newSceneId(),
                        kind: "body",
                        text: "",
                        voice_text: null,
                        visual_prompt: "",
                        headline: "",
                        duration: null,
                        pause_after: 0,
                        visual: { mode: "motion", media: null, color: null, seed: sc.length },
                      },
                    ])
                  }
                >
                  + {t("ed.addScene")}
                </button>
                <button type="button" className={btnCls} disabled={busy || project.scenes.length === 0} onClick={() => void autoBroll()}>
                  🎞 {t("broll.auto")}
                </button>
              </>
            )}

            <SocialCopyPanel projectId={id} />

            <section className={`${cardCls} space-y-3`} aria-labelledby="ed-render-h">
              <h2 id="ed-render-h" className="text-sm font-semibold text-white">
                {t("ed.quality")}
              </h2>
              <ul className="space-y-1 text-xs">
                {(quality ?? []).map((c, i) => (
                  <li
                    key={`${c.id}-${i}`}
                    className={c.level === "fail" ? "text-rose-300" : c.level === "warn" ? "text-amber-300" : "text-emerald-300"}
                  >
                    {c.level === "fail" ? "✕" : c.level === "warn" ? "⚠" : "✓"} {c.message}
                  </li>
                ))}
              </ul>
              {blocking.length > 0 && <p className="text-xs text-rose-300">{t("ed.blocked")}</p>}
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  className={btnCls}
                  disabled={busy || blocking.length > 0 || project.scenes.length === 0}
                  onClick={() => runTask(() => studio.render(id, "preview"))}
                >
                  {t("ed.preview")}
                </button>
                <button
                  type="button"
                  className={primaryCls}
                  disabled={busy || blocking.length > 0 || project.scenes.length === 0}
                  onClick={() => runTask(() => studio.render(id, "final"))}
                >
                  {t("ed.final")}
                </button>
                {finalRender && (
                  <button
                    type="button"
                    className={btnCls}
                    disabled={busy}
                    onClick={async () => {
                      try {
                        const exp = await studio.exportToJob(id);
                        router.push(`/jobs/${exp.job_id}/publishing`);
                      } catch (e) {
                        setError(errorMessage(e));
                      }
                    }}
                  >
                    {t("ed.export")}
                  </button>
                )}
                {lastExport && (
                  <Link href={`/jobs/${lastExport.job_id}/publishing`} className={btnCls}>
                    {t("ed.exported")}
                  </Link>
                )}
                <button
                  type="button"
                  className={btnCls}
                  onClick={async () => {
                    try {
                      const copy = await studio.remix(id);
                      router.push(`/studio/projects/${copy.id}`);
                    } catch (e) {
                      setError(errorMessage(e));
                    }
                  }}
                >
                  {t("ed.remix")}
                </button>
              </div>
            </section>

            <section className={`${cardCls} space-y-3`} aria-labelledby="ed-renders-h">
              <h2 id="ed-renders-h" className="text-sm font-semibold text-white">
                {t("ed.renders")}
              </h2>
              {(view?.renders.length ?? 0) === 0 && <p className="text-sm text-neutral-400">{t("ed.noRenders")}</p>}
              <ul className="grid gap-4 sm:grid-cols-2">
                {(view?.renders ?? []).slice(0, 4).map((r) => (
                  <li key={r.render_id} className="space-y-2">
                    <video
                      src={studio.renderUrl(id, r.render_id)}
                      controls
                      preload="metadata"
                      className="max-h-96 w-full rounded-lg border border-neutral-800 bg-black"
                      aria-label={`${r.mode} ${r.width}x${r.height}`}
                    />
                    <p className="text-xs text-neutral-300">
                      <span className="font-medium uppercase">{r.mode}</span> · {r.width}×{r.height} · {r.duration.toFixed(1)}s ·{" "}
                      {fmtDate(r.rendered_at, locale)}
                    </p>
                    {r.warnings.map((w) => (
                      <p key={w} className="text-xs text-amber-300">
                        ⚠ {w}
                      </p>
                    ))}
                    <a href={studio.renderUrl(id, r.render_id, true)} className={btnCls}>
                      {t("ed.download")}
                    </a>
                    {r.mode === "final" && (
                      <button
                        type="button"
                        className={`${btnCls} ml-2`}
                        onClick={async () => {
                          try {
                            const th = await studio.thumbnails(id, r.render_id);
                            setThumbs((m) => ({ ...m, [r.render_id]: th }));
                          } catch (e) {
                            setError(errorMessage(e));
                          }
                        }}
                      >
                        🖼 {t("ed.thumbs")}
                      </button>
                    )}
                    {thumbs[r.render_id] && (
                      <div className="mt-2 flex flex-wrap gap-2">
                        {thumbs[r.render_id].map((th) => (
                          <a key={th.file} href={studio.thumbnailUrl(id, r.render_id, th.file)} download title={th.reasons.join(" · ")}>
                            {/* eslint-disable-next-line @next/next/no-img-element */}
                            <img src={studio.thumbnailUrl(id, r.render_id, th.file)} alt={`Thumbnail ${th.t}s`} className="h-28 rounded" />
                            <span className="block text-[10px] text-neutral-400">
                              {th.t}s · {th.score}
                            </span>
                          </a>
                        ))}
                      </div>
                    )}
                  </li>
                ))}
              </ul>
            </section>

            <section className={cardCls}>
              <button
                type="button"
                className={btnCls}
                aria-expanded={versions !== null}
                onClick={async () => setVersions(versions === null ? await studio.versions(id).catch(() => []) : null)}
              >
                {t("ed.versions")}
              </button>
              {versions !== null && (
                <ul className="mt-3 space-y-1 text-xs text-neutral-300">
                  {versions.map((v) => (
                    <li key={v.version} className="flex items-center justify-between gap-3">
                      <span>
                        v{v.version} · {fmtDate(v.updated_at, locale)} · {v.scene_count} {t("dash.scenes")}
                      </span>
                      <button
                        type="button"
                        className="underline hover:text-white"
                        onClick={async () => {
                          if (!(await flush())) return;
                          try {
                            applyServer(await studio.restoreVersion(id, v.version));
                            setPast([]);
                            setFuture([]);
                            setVersions(null);
                            await refresh(false);
                          } catch (e) {
                            setError(errorMessage(e));
                          }
                        }}
                      >
                        {t("ed.restore")}
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          </div>

          <div className="space-y-5">
          <AgentChat
            kind="project"
            targetId={id}
            beforeExecute={flush}
            onChanged={() => void refresh(true)}
          />
          <SettingsPanel
            project={project}
            media={view?.media ?? []}
            estimate={estimate}
            onChange={(patch) => edit((p) => ({ ...p, ...patch }))}
            onMediaChanged={() => void refresh(false)}
            onApplyTemplate={async (templateId) => {
              if (!(await save())) return;
              const cur = projectRef.current;
              if (!cur) return;
              try {
                setPast((h) => [...h.slice(-49), cur]);
                setFuture([]);
                applyServer(await studio.applyTemplate(id, templateId, cur.version));
                await refresh(false);
              } catch (e) {
                setError(errorMessage(e));
              }
            }}
          />
          </div>
        </div>
      )}
    </div>
  );
}
