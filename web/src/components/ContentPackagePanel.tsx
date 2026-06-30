"use client";

import { useState } from "react";
import type { ContentPackage, ContentVariant, PlatformText } from "@/lib/types";

function copyText(text: string) {
  if (typeof navigator !== "undefined" && navigator.clipboard) {
    navigator.clipboard.writeText(text).catch(() => {});
  }
}

function CopyButton({ text, label = "Kopieren" }: { text: string; label?: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      onClick={() => {
        copyText(text);
        setCopied(true);
        setTimeout(() => setCopied(false), 1500);
      }}
      className="shrink-0 rounded-md border border-neutral-700 px-2 py-1 text-[11px] font-medium text-neutral-300 transition hover:border-neutral-500 hover:text-white"
    >
      {copied ? "✓ Kopiert" : label}
    </button>
  );
}

function TextRow({ label, value }: { label: string; value: string }) {
  if (!value) return null;
  return (
    <div className="flex items-start justify-between gap-2 rounded-lg bg-neutral-800/40 px-3 py-2">
      <div className="min-w-0">
        <p className="text-[10px] uppercase tracking-wide text-neutral-500">{label}</p>
        <p className="mt-0.5 whitespace-pre-wrap break-words text-sm text-neutral-200">{value}</p>
      </div>
      <CopyButton text={value} />
    </div>
  );
}

function HashtagRow({ hashtags }: { hashtags: string[] }) {
  if (!hashtags?.length) return null;
  const joined = hashtags.join(" ");
  return (
    <div className="flex items-start justify-between gap-2 rounded-lg bg-neutral-800/40 px-3 py-2">
      <div className="min-w-0">
        <p className="text-[10px] uppercase tracking-wide text-neutral-500">Hashtags</p>
        <p className="mt-0.5 break-words text-sm text-indigo-300">{joined}</p>
      </div>
      <CopyButton text={joined} />
    </div>
  );
}

function platformAll(name: string, p: PlatformText): string {
  return `${p.caption}\n\n${p.hashtags.join(" ")}\n\nPinned: ${p.pinned_comment}`;
}

function PlatformBlock({ title, data }: { title: string; data: PlatformText }) {
  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between">
        <h5 className="text-xs font-semibold text-neutral-200">{title}</h5>
        <CopyButton text={platformAll(title, data)} label="Alles kopieren" />
      </div>
      <TextRow label="Caption" value={data.caption} />
      <HashtagRow hashtags={data.hashtags} />
      <TextRow label="Pinned Comment" value={data.pinned_comment} />
    </div>
  );
}

function VariantBlock({ variant }: { variant: ContentVariant }) {
  const all = `${variant.hook}\n\n${variant.caption}\n\n${variant.hashtags.join(" ")}`;
  return (
    <div className="space-y-1.5 rounded-xl border border-neutral-800 p-3">
      <div className="flex items-center justify-between">
        <h5 className="text-xs font-semibold text-neutral-200">{variant.name}</h5>
        <CopyButton text={all} label="Alles kopieren" />
      </div>
      <TextRow label="Hook" value={variant.hook} />
      <TextRow label="Caption" value={variant.caption} />
      <HashtagRow hashtags={variant.hashtags} />
    </div>
  );
}

export default function ContentPackagePanel({ pkg }: { pkg: ContentPackage }) {
  const [open, setOpen] = useState(false);

  return (
    <div className="rounded-xl border border-neutral-800">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between px-3 py-2.5 text-left text-sm font-medium text-neutral-200"
      >
        <span>📦 Content-Paket</span>
        <span className="text-neutral-500">{open ? "▲" : "▼"}</span>
      </button>

      {open && (
        <div className="space-y-4 border-t border-neutral-800 px-3 py-3">
          <TextRow label="Primary Hook" value={pkg.primary_hook} />

          <div>
            <p className="mb-1.5 text-[11px] uppercase tracking-wide text-neutral-500">
              Hook-Varianten
            </p>
            <div className="space-y-1.5">
              {Object.entries(pkg.hook_variants || {}).map(([key, text]) => (
                <TextRow key={key} label={key} value={text} />
              ))}
            </div>
          </div>

          <div className="space-y-1.5">
            <div className="flex items-center justify-between">
              <h5 className="text-xs font-semibold text-neutral-200">YouTube Shorts</h5>
              <CopyButton
                text={`${pkg.youtube_shorts.title}\n\n${pkg.youtube_shorts.description}\n\n${pkg.youtube_shorts.hashtags.join(" ")}`}
                label="Alles kopieren"
              />
            </div>
            <TextRow label="Titel" value={pkg.youtube_shorts.title} />
            <TextRow label="Beschreibung" value={pkg.youtube_shorts.description} />
            <HashtagRow hashtags={pkg.youtube_shorts.hashtags} />
          </div>

          <PlatformBlock title="TikTok" data={pkg.tiktok} />
          <PlatformBlock title="Instagram Reels" data={pkg.instagram_reels} />

          {pkg.platform_recommendation && (
            <div className="rounded-lg bg-neutral-800/40 px-3 py-2 text-xs text-neutral-300">
              <span className="font-semibold text-neutral-200">
                Empfehlung: {pkg.platform_recommendation.best_platform}
              </span>{" "}
              — {pkg.platform_recommendation.reason}
            </div>
          )}

          <div>
            <p className="mb-1.5 text-[11px] uppercase tracking-wide text-neutral-500">
              Varianten A/B/C
            </p>
            <div className="grid gap-2 sm:grid-cols-3">
              <VariantBlock variant={pkg.variant_a} />
              <VariantBlock variant={pkg.variant_b} />
              <VariantBlock variant={pkg.variant_c} />
            </div>
          </div>

          {pkg.safety_note && (
            <p className="text-[11px] text-neutral-500">
              {Object.values(pkg.safety_note).join(" ")}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
