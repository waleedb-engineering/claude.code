"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useT } from "@/lib/i18n";
import { errorMessage, studio, waitForTask, type Highlight, type StreamAnalysis, type StreamMeta, type Task } from "@/lib/studio";
import AgentChat from "@/components/studio/AgentChat";
import { ErrorBox, Progress, btnCls, cardCls, inputCls, labelCls, primaryCls } from "@/components/studio/ui";

function fmt(s: number): string {
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = Math.floor(s % 60);
  return `${h ? `${h}:` : ""}${String(m).padStart(h ? 2 : 1, "0")}:${String(sec).padStart(2, "0")}`;
}

function Heatmap({ a, onPick }: { a: StreamAnalysis; onPick: (h: Highlight) => void }) {
  const pts = a.heatmap.score;
  const max = Math.max(10, ...pts);
  const w = 1000;
  const path = pts.map((v, i) => `${(i / Math.max(1, pts.length - 1)) * w},${100 - (v / max) * 95}`).join(" ");
  return (
    <svg viewBox="0 0 1000 110" className="h-28 w-full rounded-lg bg-neutral-950" role="img" aria-label="Highlight-Heatmap">
      <polyline points={`0,100 ${path} ${w},100`} fill="rgba(129,140,248,0.25)" stroke="rgb(129,140,248)" strokeWidth="1.5" />
      {a.highlights.map((h) => (
        <g key={h.id} onClick={() => onPick(h)} className="cursor-pointer">
          <rect x={(h.start / a.duration) * w} y={0} width={Math.max(3, ((h.end - h.start) / a.duration) * w)} height={100} fill="rgba(250,204,21,0.25)" />
          <text x={(h.t / a.duration) * w} y={108} fontSize="9" fill="rgb(250,204,21)" textAnchor="middle">
            {h.id}
          </text>
        </g>
      ))}
    </svg>
  );
}

export default function StreamDetailPage() {
  const { id } = useParams<{ id: string }>();
  const t = useT();
  const [meta, setMeta] = useState<StreamMeta | null>(null);
  const [analysis, setAnalysis] = useState<StreamAnalysis | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [upload, setUpload] = useState<number | null>(null);
  const [task, setTask] = useState<Task | null>(null);
  const [params, setParams] = useState({ keywords: "", max_clips: 8, chat_delay: "", transcribe: true });
  const [selected, setSelected] = useState<string[]>([]);
  const [bounds, setBounds] = useState<Record<string, { start: number; end: number }>>({});
  const [preview, setPreview] = useState<Record<string, string>>({});
  const [opts, setOpts] = useState({ reframe_mode: "smart", remove_silence: true });
  const [jobId, setJobId] = useState<string | null>(null);
  const [live, setLive] = useState({ channel: "", recording_path: "" });
  const [liveState, setLiveState] = useState<Awaited<ReturnType<typeof studio.liveState>> | null>(null);

  const load = useCallback(async () => {
    try {
      const d = await studio.stream(id);
      setMeta(d.stream);
      setAnalysis(d.analysis);
      if (d.stream.live?.status === "running") setLiveState(await studio.liveState(id));
    } catch (e) {
      setError(errorMessage(e));
    }
  }, [id]);

  useEffect(() => {
    const first = setTimeout(load, 0);
    return () => clearTimeout(first);
  }, [load]);

  useEffect(() => {
    if (meta?.live?.status !== "running") return;
    const timer = setInterval(async () => {
      try {
        setLiveState(await studio.liveState(id));
      } catch {
        /* nächster Versuch */
      }
    }, 3000);
    return () => clearInterval(timer);
  }, [id, meta?.live?.status]);

  async function runTask(start: () => Promise<Task>) {
    setError(null);
    try {
      const tk = await start();
      setTask(tk);
      const done = await waitForTask(tk.id, setTask);
      setTask(null);
      if (done.status !== "succeeded") throw new Error(done.error?.message ?? "Fehlgeschlagen.");
      await load();
      return done;
    } catch (e) {
      setTask(null);
      setError(errorMessage(e));
      return null;
    }
  }

  async function onUpload(kind: "video" | "chat", file: File | undefined) {
    if (!file) return;
    setError(null);
    try {
      if (kind === "video") {
        setUpload(0);
        await studio.uploadStreamVideo(id, file, setUpload);
      } else await studio.uploadStreamChat(id, file);
      await load();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setUpload(null);
    }
  }

  if (!meta) return <ErrorBox message={error} />;
  const busy = !!task;

  return (
    <div className="space-y-5">
      <Link href="/studio/streams" className="text-sm text-neutral-300 hover:text-white">
        ← {t("st.title")}
      </Link>
      <h1 className="text-2xl font-bold text-white">{meta.title}</h1>
      <ErrorBox message={error} />
      {task && (
        <p role="status" className="rounded-lg border border-indigo-500/40 bg-indigo-500/10 px-3 py-2 text-sm text-indigo-200">
          ⏳ {task.progress[task.progress.length - 1] ?? "…"}
        </p>
      )}

      <section className={`${cardCls} grid gap-3 sm:grid-cols-2`}>
        <div>
          <label htmlFor="sv" className={labelCls}>
            {t("st.video")}
          </label>
          <input id="sv" type="file" accept="video/*,.mkv,.flv,.ts" className={inputCls} disabled={busy} onChange={(e) => void onUpload("video", e.target.files?.[0])} />
          {meta.video && (
            <p className="mt-1 text-xs text-emerald-300">
              ✓ {meta.video.original_name} · {fmt(meta.video.duration)} · {meta.video.width}×{meta.video.height}
            </p>
          )}
          {upload !== null && <Progress value={upload} label="Upload" />}
        </div>
        <div>
          <label htmlFor="sc" className={labelCls}>
            {t("st.chat")}
          </label>
          <input id="sc" type="file" accept=".json,.jsonl,.csv,.txt" className={inputCls} disabled={busy} onChange={(e) => void onUpload("chat", e.target.files?.[0])} />
          {meta.chat && (
            <p className="mt-1 text-xs text-emerald-300">
              ✓ {meta.chat.messages} {t("st.messages")} · {meta.chat.users} Chatter · {meta.chat.format}
            </p>
          )}
        </div>
        <details className="text-xs text-neutral-400 sm:col-span-2">
          <summary>{t("st.howto")}</summary>
          <p className="mt-1">{meta.how_to_get}</p>
        </details>
      </section>

      <section className={`${cardCls} grid gap-3 sm:grid-cols-4`}>
        <div className="sm:col-span-2">
          <label htmlFor="sk" className={labelCls}>
            {t("st.keywords")}
          </label>
          <input id="sk" className={inputCls} value={params.keywords} onChange={(e) => setParams({ ...params, keywords: e.target.value })} />
        </div>
        <div>
          <label htmlFor="sm" className={labelCls}>
            {t("st.maxClips")}
          </label>
          <input id="sm" type="number" min={1} max={20} className={inputCls} value={params.max_clips} onChange={(e) => setParams({ ...params, max_clips: Number(e.target.value) })} />
        </div>
        <div>
          <label htmlFor="sd" className={labelCls}>
            {t("st.delay")}
          </label>
          <input id="sd" type="number" min={0} max={30} className={inputCls} value={params.chat_delay} onChange={(e) => setParams({ ...params, chat_delay: e.target.value })} />
        </div>
        <label className="flex items-center gap-2 text-sm text-neutral-300 sm:col-span-3">
          <input type="checkbox" checked={params.transcribe} onChange={(e) => setParams({ ...params, transcribe: e.target.checked })} />
          {t("st.transcribe")}
        </label>
        <div>
          <button
            type="button"
            className={primaryCls}
            disabled={busy || !meta.video}
            onClick={() =>
              void runTask(() =>
                studio.analyzeStream(id, {
                  keywords: params.keywords.split(",").map((k) => k.trim()).filter(Boolean),
                  max_clips: params.max_clips,
                  chat_delay: params.chat_delay === "" ? null : Number(params.chat_delay),
                  transcribe: params.transcribe,
                }),
              )
            }
          >
            {t("st.analyze")}
          </button>
        </div>
      </section>

      {analysis && (
        <section className={`${cardCls} space-y-3`}>
          <p className="text-xs text-neutral-400">
            {t("st.signals")}: {analysis.signals.join(", ")} · {t("st.delayUsed")}: {analysis.chat_delay}s ({analysis.chat_delay_note}) · {analysis.disclaimer}
          </p>
          <Heatmap a={analysis} onPick={(h) => setSelected((s) => (s.includes(h.id) ? s : [...s, h.id]))} />
          <h2 className="text-sm font-semibold text-neutral-200">{t("st.highlights")}</h2>
          <ul className="space-y-3">
            {analysis.highlights.map((h) => {
              const b = bounds[h.id] ?? { start: h.start, end: h.end };
              return (
                <li key={h.id} className="rounded-xl border border-neutral-800 p-3">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <label className="flex items-center gap-2 text-sm font-medium text-white">
                      <input
                        type="checkbox"
                        checked={selected.includes(h.id)}
                        onChange={(e) => setSelected((s) => (e.target.checked ? [...s, h.id] : s.filter((x) => x !== h.id)))}
                      />
                      {h.id} · {fmt(h.start)}–{fmt(h.end)} · Score {h.score}
                      {h.edited ? " · bearbeitet" : ""}
                    </label>
                    <span className="text-xs text-neutral-400">
                      {Object.entries(h.chat_categories).map(([k, v]) => `${k} ${v}`).join(" · ")}
                      {h.top_terms.length ? ` · „${h.top_terms.join(", ")}“` : ""}
                    </span>
                  </div>
                  <ul className="mt-1 list-disc pl-5 text-xs text-neutral-300">
                    {h.reasons.map((r, i) => (
                      <li key={i}>{r}</li>
                    ))}
                  </ul>
                  {h.text && <p className="mt-1 text-xs italic text-neutral-400">„{h.text.slice(0, 240)}“</p>}
                  <div className="mt-2 flex flex-wrap items-end gap-2">
                    <div>
                      <label className={labelCls} htmlFor={`${h.id}-s`}>
                        Start (s)
                      </label>
                      <input id={`${h.id}-s`} type="number" step={0.5} className={`${inputCls} w-24`} value={b.start} onChange={(e) => setBounds({ ...bounds, [h.id]: { ...b, start: Number(e.target.value) } })} />
                    </div>
                    <div>
                      <label className={labelCls} htmlFor={`${h.id}-e`}>
                        Ende (s)
                      </label>
                      <input id={`${h.id}-e`} type="number" step={0.5} className={`${inputCls} w-24`} value={b.end} onChange={(e) => setBounds({ ...bounds, [h.id]: { ...b, end: Number(e.target.value) } })} />
                    </div>
                    <button
                      type="button"
                      className={btnCls}
                      disabled={busy}
                      onClick={async () => {
                        try {
                          await studio.patchHighlight(id, h.id, b);
                          await load();
                        } catch (e) {
                          setError(errorMessage(e));
                        }
                      }}
                    >
                      {t("st.save")}
                    </button>
                    <button
                      type="button"
                      className={btnCls}
                      disabled={busy}
                      onClick={async () => {
                        const done = await runTask(() => studio.previewHighlight(id, h.id));
                        if (done) setPreview({ ...preview, [h.id]: `${studio.highlightPreviewUrl(id, h.id)}?v=${Date.now()}` });
                      }}
                    >
                      ▶ {t("st.preview")}
                    </button>
                  </div>
                  {preview[h.id] && <video src={preview[h.id]} controls className="mt-2 max-h-64 rounded-lg" />}
                </li>
              );
            })}
          </ul>
          <div className="flex flex-wrap items-end gap-3 border-t border-neutral-800 pt-3">
            <div>
              <label htmlFor="sr" className={labelCls}>
                {t("st.reframe")}
              </label>
              <select id="sr" className={inputCls} value={opts.reframe_mode} onChange={(e) => setOpts({ ...opts, reframe_mode: e.target.value })}>
                <option value="smart">Smart (Gesicht/Bewegung)</option>
                <option value="face">Gesicht</option>
                <option value="center">Mitte</option>
              </select>
            </div>
            <label className="flex items-center gap-2 text-sm text-neutral-300">
              <input type="checkbox" checked={opts.remove_silence} onChange={(e) => setOpts({ ...opts, remove_silence: e.target.checked })} />
              {t("st.silence")}
            </label>
            <button
              type="button"
              className={primaryCls}
              disabled={busy || selected.length === 0}
              onClick={async () => {
                const done = await runTask(() => studio.renderHighlights(id, { ids: selected, ...opts }));
                if (done?.result) setJobId(String((done.result as { job_id: string }).job_id));
              }}
            >
              {t("st.render")} ({selected.length})
            </button>
            {jobId && (
              <Link href={`/jobs/${jobId}`} className="text-sm text-emerald-300 underline">
                {t("st.openJob")}
              </Link>
            )}
          </div>
        </section>
      )}

      {meta.video && <AgentChat kind="stream" targetId={id} onChanged={() => void load()} />}

      <section className={`${cardCls} space-y-3`}>
        <h2 className="text-sm font-semibold text-neutral-200">{t("st.live")}</h2>
        <p className="text-xs text-neutral-400">{t("st.liveHint")}</p>
        {meta.live?.status === "running" ? (
          <>
            <p className="text-sm text-emerald-300">
              ● {liveState?.state ? `${liveState.state.messages} ${t("st.messages")} · ${fmt(liveState.state.elapsed)}` : "…"}
              {liveState?.state && !liveState.state.chat_connected ? ` · Chat getrennt (${liveState.state.chat_error ?? "…"})` : ""}
            </p>
            <ul className="space-y-2 text-xs text-neutral-300">
              {(liveState?.state?.events ?? []).map((ev) => (
                <li key={ev.id}>
                  {ev.id} · {fmt(ev.start)}–{fmt(ev.end)} · {ev.status} · {ev.reason}
                  {ev.file && <video src={studio.liveClipUrl(id, ev.id)} controls className="mt-1 max-h-48 rounded" />}
                </li>
              ))}
            </ul>
            <button
              type="button"
              className={btnCls}
              onClick={async () => {
                try {
                  await studio.cancelTask(meta.live!.task_id);
                  setTimeout(() => void load(), 1500);
                } catch (e) {
                  setError(errorMessage(e));
                }
              }}
            >
              ■ {t("st.liveStop")}
            </button>
          </>
        ) : (
          <div className="grid gap-2 sm:grid-cols-3">
            <input aria-label={t("st.channel")} placeholder={t("st.channel")} className={inputCls} value={live.channel} onChange={(e) => setLive({ ...live, channel: e.target.value })} />
            <input aria-label={t("st.recording")} placeholder={t("st.recording")} className={inputCls} value={live.recording_path} onChange={(e) => setLive({ ...live, recording_path: e.target.value })} />
            <button
              type="button"
              className={primaryCls}
              disabled={!live.channel && !live.recording_path}
              onClick={async () => {
                setError(null);
                try {
                  await studio.startLive(id, { channel: live.channel || null, recording_path: live.recording_path || null });
                  await load();
                } catch (e) {
                  setError(errorMessage(e));
                }
              }}
            >
              {t("st.liveStart")}
            </button>
          </div>
        )}
      </section>
    </div>
  );
}
