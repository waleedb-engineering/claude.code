"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { listJobs } from "@/lib/api";
import type { JobSummary } from "@/lib/types";
import { tDyn, useLocale, useT } from "@/lib/i18n";
import { errorMessage, studio, waitForTask, type Template, type Workflow } from "@/lib/studio";
import { ErrorBox, Loading, Progress, cardCls, inputCls, labelCls, primaryCls } from "@/components/studio/ui";

const ACCEPT: Record<string, string> = {
  pdf: ".pdf,application/pdf",
  audio: "audio/*,video/*",
  music: "audio/*",
  podcast: "audio/*,video/*",
  longform: "video/*",
  youtube: "video/*",
  media: "image/png,image/jpeg,image/webp,video/*",
};

function newKey(): string {
  return `ui-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

export default function CreatePage() {
  const t = useT();
  const locale = useLocale();
  const router = useRouter();
  const [workflows, setWorkflows] = useState<Workflow[] | null>(null);
  const [jobs, setJobs] = useState<JobSummary[]>([]);
  const [selected, setSelected] = useState<string>("prompt");
  const [title, setTitle] = useState("");
  const [text, setText] = useState("");
  const [url, setUrl] = useState("");
  const [jobId, setJobId] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [transcript, setTranscript] = useState<File | null>(null);
  const [product, setProduct] = useState({ name: "", problem: "", benefits: "", price: "", cta: "" });
  const [seconds, setSeconds] = useState(45);
  const [aspect, setAspect] = useState("9:16");
  const [aspectTouched, setAspectTouched] = useState(false);
  const [resolution, setResolution] = useState("1080p");
  const [captions, setCaptions] = useState("karaoke");
  const [language, setLanguage] = useState<"de" | "en">(locale);
  const [opts, setOpts] = useState({
    platform: "generic",
    goal: "",
    audience: "",
    cta: "",
    creative_instructions: "",
    forbidden_topics: "",
    visual_style: "",
    media_type: "motion",
  });
  const [rights, setRights] = useState(false);
  const [templates, setTemplates] = useState<Template[]>([]);
  const [templateId, setTemplateId] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [upload, setUpload] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const idemKey = useRef(newKey());

  useEffect(() => {
    (async () => {
      try {
        const o = await studio.overview();
        setWorkflows(o.workflows.filter((w) => w.id !== "idea"));
        setTemplates(await studio.templates());
        const all = await listJobs();
        setJobs(all.filter((j) => j.status === "completed"));
      } catch (e) {
        setError(errorMessage(e));
      }
    })();
  }, []);

  const wf = workflows?.find((w) => w.id === selected);
  const needs = wf?.needs ?? "text";
  const isShorts = selected === "podcast" || selected === "longform" || selected === "youtube";
  const takesFile = needs === "file" || needs === "youtube";

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!wf || busy) return;
    setError(null);
    setBusy(t("create.creating"));
    try {
      const body: Record<string, unknown> = {
        workflow: selected,
        title,
        language,
        target_seconds: seconds,
        aspect_ratio: aspect,
        resolution,
        captions: { style: captions, use_brand: true },
        options: {
          ...opts,
          duration_target: seconds,
          forbidden_topics: opts.forbidden_topics.split(",").map((x) => x.trim()).filter(Boolean),
        },
      };
      // Das Seitenverhältnis folgt der Plattform, solange es nicht bewusst geändert wurde.
      if (!aspectTouched) delete body.aspect_ratio;
      if (templateId) body.template_id = templateId;
      if (selected === "script") body.script = text;
      else if (needs === "text" || needs === "file") body.prompt = text;
      if (needs === "url" || needs === "youtube") body.url = url;
      if (needs === "youtube") body.rights_confirmed = rights;
      if (needs === "job") body.job_id = jobId;
      if (needs === "product")
        body.product = { ...product, benefits: product.benefits.split("\n").filter((b) => b.trim()) };
      if (takesFile && files.length === 0) throw new Error(t("create.file"));
      const created = await studio.createProject(body, idemKey.current);
      const pid = created.project.id;
      let taskId = created.task_id;
      if (takesFile) {
        for (let i = 0; i < files.length; i++) {
          setBusy(`${t("create.uploading")} ${i + 1}/${files.length}`);
          setUpload(0);
          if (selected === "media") await studio.uploadMedia(pid, files[i], setUpload);
          else await studio.uploadSource(pid, files[i], setUpload);
        }
        if (transcript) await studio.uploadSource(pid, transcript, setUpload, "transcript");
        setUpload(null);
        taskId = (await studio.ingest(pid)).id;
      }
      if (taskId) {
        setBusy(t("create.processing"));
        const task = await waitForTask(taskId, (tk) => {
          const last = tk.progress[tk.progress.length - 1];
          if (last) setBusy(last);
        });
        if (task.status !== "succeeded") {
          // Projekt existiert bereits → im Editor weiter (dort ist Retry möglich)
          router.push(`/studio/projects/${pid}`);
          return;
        }
      }
      router.push(`/studio/projects/${pid}`);
    } catch (err) {
      setError(errorMessage(err));
      idemKey.current = newKey();
      setBusy(null);
      setUpload(null);
    }
  }

  if (!workflows && !error) return <Loading />;

  return (
    <form onSubmit={submit} className="space-y-6">
      <h1 className="text-2xl font-bold tracking-tight text-white">{t("create.title")}</h1>
      <ErrorBox message={error} />

      <fieldset>
        <legend className="mb-3 text-sm font-semibold text-neutral-200">{t("create.pick")}</legend>
        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
          {(workflows ?? []).map((w) => (
            <label
              key={w.id}
              className={`flex cursor-pointer flex-col rounded-xl border p-3 text-sm focus-within:ring-2 focus-within:ring-indigo-400 ${
                !w.available
                  ? "cursor-not-allowed border-neutral-800 bg-neutral-900/30 text-neutral-500"
                  : selected === w.id
                    ? "border-indigo-400 bg-indigo-500/10 text-white"
                    : "border-neutral-700 bg-neutral-900/40 text-neutral-200 hover:border-neutral-500"
              }`}
            >
              <span className="flex items-center gap-2">
                <input
                  type="radio"
                  name="workflow"
                  value={w.id}
                  checked={selected === w.id}
                  disabled={!w.available}
                  onChange={() => {
                    setSelected(w.id);
                    setFiles([]);
                    setError(null);
                  }}
                  className="accent-indigo-400"
                />
                <span className="font-medium">{tDyn(t, "wf", w.id)}</span>
              </span>
              {!w.available && (
                <span className="mt-1 text-xs text-neutral-400">
                  {w.reason}
                </span>
              )}
            </label>
          ))}
        </div>
      </fieldset>

      <section className={`${cardCls} space-y-4`}>
        <h2 className="text-sm font-semibold text-neutral-200">{t("create.details")}</h2>
        <div>
          <label htmlFor="c-title" className={labelCls}>
            {t("create.projectTitle")}
          </label>
          <input id="c-title" className={inputCls} value={title} maxLength={120} onChange={(e) => setTitle(e.target.value)} />
        </div>

        {(needs === "text" || (needs === "file" && (selected === "music" || selected === "media"))) && (
          <div>
            <label htmlFor="c-text" className={labelCls}>
              {selected === "script" ? t("create.script") : selected === "media" ? t("create.mediaLines") : t("create.prompt")}
            </label>
            <textarea
              id="c-text"
              className={`${inputCls} min-h-32`}
              value={text}
              required={needs === "text"}
              onChange={(e) => setText(e.target.value)}
            />
          </div>
        )}

        {needs === "youtube" && (
          <div className="space-y-3">
            <div>
              <label htmlFor="c-yt" className={labelCls}>
                {t("create.youtubeUrl")}
              </label>
              <input
                id="c-yt"
                type="url"
                required
                placeholder="https://www.youtube.com/watch?v=…"
                className={inputCls}
                value={url}
                onChange={(e) => setUrl(e.target.value)}
              />
            </div>
            <p className="text-xs text-neutral-300">{t("create.youtubeHint")}</p>
            <label className="flex items-start gap-2 text-sm text-neutral-200">
              <input
                type="checkbox"
                required
                className="mt-1 accent-indigo-400"
                checked={rights}
                onChange={(e) => setRights(e.target.checked)}
              />
              {t("create.youtubeRights")}
            </label>
          </div>
        )}

        {needs === "url" && (
          <div>
            <label htmlFor="c-url" className={labelCls}>
              {t("create.url")}
            </label>
            <input
              id="c-url"
              type="url"
              required
              placeholder="https://"
              className={inputCls}
              value={url}
              onChange={(e) => setUrl(e.target.value)}
            />
          </div>
        )}

        {takesFile && (
          <div className="space-y-3">
            <div>
              <label htmlFor="c-file" className={labelCls}>
                {selected === "media" ? t("create.files") : t("create.file")}
              </label>
              <input
                id="c-file"
                type="file"
                required
                multiple={selected === "media"}
                accept={ACCEPT[selected]}
                className={inputCls}
                onChange={(e) => setFiles(Array.from(e.target.files ?? []))}
              />
            </div>
            {(selected === "audio" || isShorts) && (
              <div>
                <label htmlFor="c-transcript" className={labelCls}>
                  {t("create.transcript")}
                </label>
                <input
                  id="c-transcript"
                  type="file"
                  accept=".json,.srt,.vtt,application/json,text/vtt"
                  className={inputCls}
                  onChange={(e) => setTranscript(e.target.files?.[0] ?? null)}
                />
              </div>
            )}
          </div>
        )}

        {needs === "job" && (
          <div>
            <label htmlFor="c-job" className={labelCls}>
              {t("create.job")}
            </label>
            {jobs.length === 0 ? (
              <p className="text-sm text-neutral-400">{t("create.noJobs")}</p>
            ) : (
              <select id="c-job" required className={inputCls} value={jobId} onChange={(e) => setJobId(e.target.value)}>
                <option value="">–</option>
                {jobs.map((j) => (
                  <option key={j.id} value={j.id}>
                    {j.filename} ({j.id})
                  </option>
                ))}
              </select>
            )}
          </div>
        )}

        {needs === "product" && (
          <div className="grid gap-3 sm:grid-cols-2">
            {(["name", "problem", "price", "cta"] as const).map((f) => (
              <div key={f}>
                <label htmlFor={`c-p-${f}`} className={labelCls}>
                  {t(`create.product.${f}`)}
                </label>
                <input
                  id={`c-p-${f}`}
                  className={inputCls}
                  required={f === "name"}
                  value={product[f]}
                  onChange={(e) => setProduct({ ...product, [f]: e.target.value })}
                />
              </div>
            ))}
            <div className="sm:col-span-2">
              <label htmlFor="c-p-benefits" className={labelCls}>
                {t("create.product.benefits")}
              </label>
              <textarea
                id="c-p-benefits"
                className={`${inputCls} min-h-24`}
                value={product.benefits}
                onChange={(e) => setProduct({ ...product, benefits: e.target.value })}
              />
            </div>
          </div>
        )}
      </section>

      {!isShorts && (
        <section className={`${cardCls} grid gap-3 sm:grid-cols-2 lg:grid-cols-5`}>
          <h2 className="text-sm font-semibold text-neutral-200 sm:col-span-2 lg:col-span-5">{t("create.settings")}</h2>
          <div className="sm:col-span-2 lg:col-span-5">
            <label htmlFor="c-template" className={labelCls}>
              {t("tpl.title")}
            </label>
            <select id="c-template" className={inputCls} value={templateId} onChange={(e) => setTemplateId(e.target.value)}>
              <option value="">{t("tpl.none")}</option>
              {templates.map((x) => (
                <option key={x.id} value={x.id}>
                  {locale === "en" ? x.name_en : x.name} — {x.description}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label htmlFor="c-lang" className={labelCls}>
              {t("common.language")}
            </label>
            <select id="c-lang" className={inputCls} value={language} onChange={(e) => setLanguage(e.target.value as "de" | "en")}>
              <option value="de">Deutsch</option>
              <option value="en">English</option>
            </select>
          </div>
          <div>
            <label htmlFor="c-aspect" className={labelCls}>
              {t("create.aspect")}
            </label>
            <select
              id="c-aspect"
              className={inputCls}
              value={aspect}
              onChange={(e) => {
                setAspect(e.target.value);
                setAspectTouched(true);
              }}
            >
              {["9:16", "16:9", "1:1", "4:5"].map((a) => (
                <option key={a}>{a}</option>
              ))}
            </select>
          </div>
          <div>
            <label htmlFor="c-res" className={labelCls}>
              {t("create.resolution")}
            </label>
            <select id="c-res" className={inputCls} value={resolution} onChange={(e) => setResolution(e.target.value)}>
              {["720p", "1080p", "4k"].map((a) => (
                <option key={a}>{a}</option>
              ))}
            </select>
          </div>
          <div>
            <label htmlFor="c-cap" className={labelCls}>
              {t("create.captions")}
            </label>
            <select id="c-cap" className={inputCls} value={captions} onChange={(e) => setCaptions(e.target.value)}>
              {["minimal", "bold", "karaoke", "dynamic", "none"].map((a) => (
                <option key={a}>{a}</option>
              ))}
            </select>
          </div>
          <div>
            <label htmlFor="c-sec" className={labelCls}>
              {t("create.seconds")}
            </label>
            <input
              id="c-sec"
              type="number"
              min={10}
              max={600}
              className={inputCls}
              value={seconds}
              onChange={(e) => setSeconds(Number(e.target.value) || 45)}
            />
          </div>
        </section>
      )}

      {!isShorts && (
        <details className={cardCls}>
          <summary className="cursor-pointer text-sm font-semibold text-neutral-200 focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400">
            {t("opt.title")}
          </summary>
          <p className="mt-2 text-xs text-neutral-300">{t("opt.llmHint")}</p>
          <div className="mt-3 grid gap-3 sm:grid-cols-2">
            <div>
              <label htmlFor="o-platform" className={labelCls}>
                {t("opt.platform")}
              </label>
              <select
                id="o-platform"
                className={inputCls}
                value={opts.platform}
                onChange={(e) => setOpts({ ...opts, platform: e.target.value })}
              >
                {["generic", "youtube_shorts", "tiktok", "instagram_reels", "x"].map((p) => (
                  <option key={p}>{p}</option>
                ))}
              </select>
            </div>
            <div>
              <label htmlFor="o-media" className={labelCls}>
                {t("opt.mediaType")}
              </label>
              <select
                id="o-media"
                className={inputCls}
                value={opts.media_type}
                onChange={(e) => setOpts({ ...opts, media_type: e.target.value })}
              >
                <option value="motion">{t("ed.mode.motion")}</option>
                <option value="static">{t("ed.mode.static")}</option>
                <option value="ai_image">{t("ed.mode.ai_image")}</option>
              </select>
            </div>
            {(
              [
                ["cta", "opt.cta"],
                ["forbidden_topics", "opt.forbidden"],
                ["visual_style", "opt.visualStyle"],
                ["goal", "opt.goal"],
                ["audience", "opt.audience"],
                ["creative_instructions", "opt.instructions"],
              ] as const
            ).map(([field, key]) => (
              <div key={field}>
                <label htmlFor={`o-${field}`} className={labelCls}>
                  {t(key)}
                </label>
                <input
                  id={`o-${field}`}
                  className={inputCls}
                  value={opts[field]}
                  onChange={(e) => setOpts({ ...opts, [field]: e.target.value })}
                />
              </div>
            ))}
          </div>
        </details>
      )}

      {upload !== null && <Progress value={upload} label={busy ?? t("create.uploading")} />}
      <div className="flex items-center gap-4">
        <button type="submit" className={primaryCls} disabled={!wf?.available || busy !== null}>
          {busy ? t("create.creating") : t("create.submit")}
        </button>
        {busy && (
          <p role="status" aria-live="polite" className="text-sm text-neutral-300">
            {busy}
          </p>
        )}
      </div>
    </form>
  );
}
