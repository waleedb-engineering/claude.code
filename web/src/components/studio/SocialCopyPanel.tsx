"use client";

import { useState } from "react";
import { useT } from "@/lib/i18n";
import { errorMessage, studio, type SocialCopy } from "@/lib/studio";
import { btnCls, cardCls, inputCls, labelCls } from "./ui";

const NAMES: Record<string, string> = { youtube_shorts: "YouTube Shorts", tiktok: "TikTok", instagram_reels: "Instagram Reels", x: "X" };

/** Titel, Beschreibung, Hashtags, CTA je Plattform — Vorschläge zum Bearbeiten und Kopieren. */
export default function SocialCopyPanel({ projectId }: { projectId: string }) {
  const t = useT();
  const [data, setData] = useState<SocialCopy | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState<string | null>(null);

  async function load(engine: "local" | "anthropic") {
    if (engine === "anthropic" && !window.confirm(t("copy.llmCost"))) return;
    setBusy(true);
    setError(null);
    try {
      setData(await studio.socialCopy(projectId, engine, engine === "anthropic"));
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  function edit(platform: string, field: "title" | "description" | "cta" | "hashtags", value: string) {
    if (!data) return;
    const cur = data.platforms[platform];
    const next = field === "hashtags" ? { ...cur, hashtags: value.split(/[\s,]+/).map((h) => h.replace(/^#/, "")).filter(Boolean) } : { ...cur, [field]: value };
    setData({ ...data, platforms: { ...data.platforms, [platform]: next } });
  }

  async function copy(platform: string) {
    const p = data?.platforms[platform];
    if (!p) return;
    const text = [p.title, p.description, p.hashtags.map((h) => `#${h}`).join(" ")].filter(Boolean).join("\n\n");
    try {
      await navigator.clipboard.writeText(text);
      setCopied(platform);
    } catch {
      setError(t("copy.clipboardFailed"));
    }
  }

  return (
    <section className={`${cardCls} space-y-3`} aria-labelledby="copy-h">
      <h2 id="copy-h" className="text-sm font-semibold text-neutral-200">
        {t("copy.title")}
      </h2>
      <p className="text-xs text-neutral-400">{t("copy.hint")}</p>
      <div className="flex flex-wrap gap-2">
        <button type="button" className={btnCls} disabled={busy} onClick={() => void load("local")}>
          {t("copy.local")}
        </button>
        <button type="button" className={btnCls} disabled={busy} onClick={() => void load("anthropic")}>
          {t("copy.llm")}
        </button>
      </div>
      {error && (
        <p role="alert" className="text-xs text-rose-300">
          {error}
        </p>
      )}
      {data && (
        <>
          <p className="text-xs text-neutral-400">
            {t("copy.keywords")}: {data.keywords.join(", ")}
          </p>
          <div className="grid gap-3 md:grid-cols-2">
            {Object.entries(data.platforms).map(([platform, p]) => (
              <div key={platform} className="space-y-1 rounded-xl border border-neutral-800 p-3">
                <p className="text-xs font-semibold text-neutral-200">{NAMES[platform] ?? platform}</p>
                <label className={labelCls} htmlFor={`cp-${platform}-t`}>
                  {t("copy.fTitle")}
                </label>
                <input id={`cp-${platform}-t`} className={inputCls} value={p.title} onChange={(e) => edit(platform, "title", e.target.value)} />
                <label className={labelCls} htmlFor={`cp-${platform}-d`}>
                  {t("copy.fDesc")}
                </label>
                <textarea id={`cp-${platform}-d`} className={`${inputCls} min-h-16`} value={p.description} onChange={(e) => edit(platform, "description", e.target.value)} />
                <label className={labelCls} htmlFor={`cp-${platform}-h`}>
                  Hashtags
                </label>
                <input
                  id={`cp-${platform}-h`}
                  className={inputCls}
                  value={p.hashtags.map((h) => `#${h}`).join(" ")}
                  onChange={(e) => edit(platform, "hashtags", e.target.value)}
                />
                <button type="button" className={btnCls} onClick={() => void copy(platform)}>
                  {copied === platform ? `✓ ${t("copy.copied")}` : t("copy.copy")}
                </button>
              </div>
            ))}
          </div>
        </>
      )}
    </section>
  );
}
