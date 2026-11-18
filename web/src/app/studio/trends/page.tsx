"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useT } from "@/lib/i18n";
import { errorMessage, studio } from "@/lib/studio";
import { ErrorBox, Notice, btnCls, cardCls, inputCls, labelCls } from "@/components/studio/ui";

type Trends = Awaited<ReturnType<typeof studio.trendsYoutube>>;
type Status = Awaited<ReturnType<typeof studio.trends>>;

export default function TrendsPage() {
  const t = useT();
  const [status, setStatus] = useState<Status | null>(null);
  const [region, setRegion] = useState("DE");
  const [category, setCategory] = useState("");
  const [data, setData] = useState<Trends | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState<string | null>(null);

  useEffect(() => {
    const first = setTimeout(async () => {
      try {
        setStatus(await studio.trends());
      } catch (e) {
        setError(errorMessage(e));
      }
    }, 0);
    return () => clearTimeout(first);
  }, []);

  async function load() {
    setError(null);
    try {
      setData(await studio.trendsYoutube(region, category));
    } catch (e) {
      setError(errorMessage(e));
    }
  }

  async function keep(title: string, url: string, views: number | null) {
    try {
      await studio.createIdea({ title, url, platform: "youtube_shorts", notes: t("tr.fromTrends"), metrics: views ? { views } : undefined });
      setSaved(title);
    } catch (e) {
      setError(errorMessage(e));
    }
  }

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-bold text-white">{t("nav.trends")}</h1>
        <p className="mt-1 text-sm text-neutral-300">{t("tr.hint")}</p>
      </div>
      <ErrorBox message={error} />
      {status && (
        <ul className="grid gap-2 sm:grid-cols-3">
          {Object.entries(status.platforms).map(([p, s]) => (
            <li key={p} className={`${cardCls} text-sm`}>
              <p className="font-medium text-white">{p === "youtube" ? "YouTube" : p === "tiktok" ? "TikTok" : "Instagram"}</p>
              <p className={`mt-1 text-xs ${s.available ? "text-emerald-300" : "text-amber-300"}`}>{s.note}</p>
            </li>
          ))}
        </ul>
      )}
      <section className={`${cardCls} space-y-3`}>
        <div className="flex flex-wrap items-end gap-3">
          <div>
            <label htmlFor="tr-region" className={labelCls}>
              {t("tr.region")}
            </label>
            <input id="tr-region" className={`${inputCls} w-20`} maxLength={2} value={region} onChange={(e) => setRegion(e.target.value.toUpperCase())} />
          </div>
          <div>
            <label htmlFor="tr-cat" className={labelCls}>
              {t("tr.category")}
            </label>
            <select id="tr-cat" className={inputCls} value={category} onChange={(e) => setCategory(e.target.value)}>
              {Object.entries(status?.categories ?? { "": "Alle" }).map(([id, name]) => (
                <option key={id} value={id}>
                  {name}
                </option>
              ))}
            </select>
          </div>
          <button type="button" className={btnCls} onClick={() => void load()}>
            {t("tr.load")}
          </button>
        </div>
        {data && (
          <>
            <Notice>
              {data.source} — {data.note}
            </Notice>
            <p className="text-sm text-neutral-300">
              {t("tr.keywords")}: {data.keywords.map((k) => `${k.keyword} (${k.count})`).join(", ")}
            </p>
            <ul className="divide-y divide-neutral-800 text-sm">
              {data.videos.map((v) => (
                <li key={v.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
                  <span className="min-w-0">
                    <a href={v.url} target="_blank" rel="noreferrer" className="text-white underline-offset-2 hover:underline">
                      {v.title}
                    </a>
                    <span className="ml-2 text-xs text-neutral-500">
                      {v.channel}
                      {v.views != null ? ` · ${v.views.toLocaleString()} Views` : ""}
                    </span>
                  </span>
                  <button type="button" className={btnCls} onClick={() => void keep(v.title, v.url, v.views)}>
                    {saved === v.title ? "✓" : t("tr.keep")}
                  </button>
                </li>
              ))}
            </ul>
          </>
        )}
      </section>
      <p className="text-sm text-neutral-300">
        {t("tr.manual")}{" "}
        <Link className="underline" href="/studio/ideas">
          {t("nav.ideas")}
        </Link>
      </p>
    </div>
  );
}
