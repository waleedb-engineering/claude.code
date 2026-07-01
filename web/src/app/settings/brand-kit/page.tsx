"use client";

import { useEffect, useState } from "react";
import { getBrandKit, getCaptionStyles, saveBrandKit } from "@/lib/api";
import type { BrandKit, CaptionStyleInfo } from "@/lib/types";
import Spinner from "@/components/Spinner";

const EMPTY: BrandKit = {
  brand_name: "",
  primary_color: "#FFDD00",
  secondary_color: "#000000",
  font_family: null,
  caption_style_default: "clean",
  highlight_keywords: [],
  watermark_text: "",
  watermark_enabled: false,
};

export default function BrandKitPage() {
  const [kit, setKit] = useState<BrandKit>(EMPTY);
  const [styles, setStyles] = useState<CaptionStyleInfo[]>([]);
  const [keywordsText, setKeywordsText] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const [k, s] = await Promise.all([getBrandKit(), getCaptionStyles()]);
        setKit(k);
        setKeywordsText((k.highlight_keywords ?? []).join(", "));
        setStyles(s);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Konnte Brand Kit nicht laden.");
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  function set<K extends keyof BrandKit>(key: K, val: BrandKit[K]) {
    setKit((prev) => ({ ...prev, [key]: val }));
    setSuccess(null);
  }

  async function handleSave() {
    setSaving(true);
    setError(null);
    setSuccess(null);
    const keywords = keywordsText
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
    try {
      const saved = await saveBrandKit({ ...kit, highlight_keywords: keywords });
      setKit(saved);
      setKeywordsText((saved.highlight_keywords ?? []).join(", "));
      setSuccess("Brand Kit gespeichert.");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Speichern fehlgeschlagen.");
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-sm text-neutral-400">
        <Spinner className="h-4 w-4" /> Lade Brand Kit …
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-white">Brand Kit</h1>
        <p className="mt-1 text-sm text-neutral-400">
          Lokale Marken-Defaults für einheitliche Clips. Optional — ohne Brand
          Kit gelten die Style-Standards. Keine Cloud, kein Account.
        </p>
      </div>

      <div className="space-y-4 rounded-2xl border border-neutral-800 bg-neutral-900/40 p-5">
        <label className="block">
          <span className="text-sm text-neutral-300">Brand Name</span>
          <input
            type="text"
            value={kit.brand_name}
            maxLength={60}
            onChange={(e) => set("brand_name", e.target.value)}
            placeholder="z. B. Acme Media"
            className="mt-1 w-full rounded-lg border border-neutral-700 bg-neutral-950 px-3 py-2 text-sm text-neutral-100 outline-none focus:border-indigo-500"
          />
        </label>

        <div className="grid gap-4 sm:grid-cols-2">
          <label className="block">
            <span className="text-sm text-neutral-300">Primary Color (Highlight)</span>
            <div className="mt-1 flex items-center gap-2">
              <input
                type="color"
                value={kit.primary_color}
                onChange={(e) => set("primary_color", e.target.value.toUpperCase())}
                className="h-9 w-12 rounded border border-neutral-700 bg-neutral-950"
              />
              <input
                type="text"
                value={kit.primary_color}
                onChange={(e) => set("primary_color", e.target.value)}
                className="w-full rounded-lg border border-neutral-700 bg-neutral-950 px-3 py-2 text-sm text-neutral-100 outline-none focus:border-indigo-500"
              />
            </div>
          </label>
          <label className="block">
            <span className="text-sm text-neutral-300">Secondary Color (Outline)</span>
            <div className="mt-1 flex items-center gap-2">
              <input
                type="color"
                value={kit.secondary_color}
                onChange={(e) => set("secondary_color", e.target.value.toUpperCase())}
                className="h-9 w-12 rounded border border-neutral-700 bg-neutral-950"
              />
              <input
                type="text"
                value={kit.secondary_color}
                onChange={(e) => set("secondary_color", e.target.value)}
                className="w-full rounded-lg border border-neutral-700 bg-neutral-950 px-3 py-2 text-sm text-neutral-100 outline-none focus:border-indigo-500"
              />
            </div>
          </label>
        </div>

        <label className="block">
          <span className="text-sm text-neutral-300">Default Caption-Style</span>
          <select
            value={kit.caption_style_default}
            onChange={(e) => set("caption_style_default", e.target.value)}
            className="mt-1 w-full rounded-lg border border-neutral-700 bg-neutral-950 px-3 py-2 text-sm text-neutral-100 outline-none focus:border-indigo-500"
          >
            {styles.map((s) => (
              <option key={s.style_id} value={s.style_id}>
                {s.name} — {s.recommended_for}
              </option>
            ))}
          </select>
        </label>

        <label className="block">
          <span className="text-sm text-neutral-300">
            Highlight-Keywords (Komma-getrennt)
          </span>
          <input
            type="text"
            value={keywordsText}
            onChange={(e) => {
              setKeywordsText(e.target.value);
              setSuccess(null);
            }}
            placeholder="z. B. hook, geld, jetzt"
            className="mt-1 w-full rounded-lg border border-neutral-700 bg-neutral-950 px-3 py-2 text-sm text-neutral-100 outline-none focus:border-indigo-500"
          />
          <span className="mt-1 block text-[11px] text-neutral-500">
            Diese Wörter werden in den Captions in der Primary Color hervorgehoben.
          </span>
        </label>

        <label className="block">
          <span className="text-sm text-neutral-300">Watermark-Text (max. 40)</span>
          <input
            type="text"
            value={kit.watermark_text}
            maxLength={40}
            onChange={(e) => set("watermark_text", e.target.value)}
            placeholder="z. B. @deinhandle"
            className="mt-1 w-full rounded-lg border border-neutral-700 bg-neutral-950 px-3 py-2 text-sm text-neutral-100 outline-none focus:border-indigo-500"
          />
        </label>

        <button
          type="button"
          onClick={() => set("watermark_enabled", !kit.watermark_enabled)}
          className="flex w-full items-center justify-between gap-3 rounded-lg border border-neutral-700 bg-neutral-950 px-3 py-2 text-left"
        >
          <span className="text-sm text-neutral-300">Watermark aktiv</span>
          <span
            role="switch"
            aria-checked={kit.watermark_enabled}
            className={`inline-flex h-6 w-11 shrink-0 items-center rounded-full transition ${
              kit.watermark_enabled ? "bg-indigo-500" : "bg-neutral-700"
            }`}
          >
            <span
              className={`inline-block h-5 w-5 transform rounded-full bg-white transition ${
                kit.watermark_enabled ? "translate-x-5" : "translate-x-0.5"
              }`}
            />
          </span>
        </button>
      </div>

      {error && (
        <div className="rounded-xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-300">
          {error}
        </div>
      )}
      {success && (
        <div className="rounded-xl border border-emerald-500/30 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-300">
          ✓ {success}
        </div>
      )}

      <button
        onClick={handleSave}
        disabled={saving}
        className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-white px-5 py-3 font-medium text-neutral-900 transition hover:bg-neutral-200 disabled:opacity-50"
      >
        {saving ? (
          <>
            <Spinner className="h-4 w-4" /> Speichere …
          </>
        ) : (
          "Brand Kit speichern"
        )}
      </button>

      <p className="text-[11px] text-neutral-600">
        Gespeichert lokal unter <code>api/config/brand_kit.json</code>. Keine
        externen Fonts, keine Cloud-Synchronisierung, kein Account. Die
        CSS-Vorschau ist nur eine Annäherung — die FFmpeg-Ausgabe ist maßgeblich.
      </p>
    </div>
  );
}
