"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import { setLocale, tDyn, useLocale, useT, type TKey } from "@/lib/i18n";

export const inputCls =
  "w-full rounded-lg border border-neutral-700 bg-neutral-900 px-3 py-2 text-sm text-neutral-100 placeholder:text-neutral-500 focus:border-indigo-400 focus:outline-none focus:ring-2 focus:ring-indigo-400/40";
export const btnCls =
  "inline-flex items-center justify-center gap-2 rounded-lg border border-neutral-700 px-3 py-1.5 text-sm text-neutral-100 transition hover:border-neutral-500 focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400 disabled:cursor-not-allowed disabled:opacity-50";
export const primaryCls =
  "inline-flex items-center justify-center gap-2 rounded-lg bg-indigo-500 px-4 py-2 text-sm font-medium text-white transition hover:bg-indigo-400 focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-300 disabled:cursor-not-allowed disabled:opacity-50";
export const cardCls = "rounded-2xl border border-neutral-800 bg-neutral-900/40 p-4";
export const labelCls = "mb-1 block text-xs font-medium text-neutral-300";

const TABS: { href: string; key: TKey }[] = [
  { href: "/studio", key: "nav.dashboard" },
  { href: "/studio/create", key: "nav.create" },
  { href: "/studio/automations", key: "nav.automations" },
  { href: "/studio/analytics", key: "nav.analytics" },
  { href: "/studio/ideas", key: "nav.ideas" },
  { href: "/studio/setup", key: "nav.setup" },
];

export function LocaleToggle() {
  const locale = useLocale();
  const t = useT();
  return (
    <div role="group" aria-label={t("common.language")} className="flex overflow-hidden rounded-lg border border-neutral-700 text-xs">
      {(["de", "en"] as const).map((l) => (
        <button
          key={l}
          type="button"
          aria-pressed={locale === l}
          onClick={() => setLocale(l)}
          className={`px-2 py-1 uppercase focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400 ${
            locale === l ? "bg-neutral-200 text-neutral-900" : "text-neutral-300 hover:bg-neutral-800"
          }`}
        >
          {l}
        </button>
      ))}
    </div>
  );
}

export function StudioNav() {
  const pathname = usePathname();
  const t = useT();
  return (
    <div className="mb-6 flex flex-wrap items-center justify-between gap-3 border-b border-neutral-800 pb-3">
      <nav aria-label="Studio" className="flex flex-wrap gap-1 text-sm">
        {TABS.map((tab) => {
          const active = tab.href === "/studio" ? pathname === "/studio" || pathname.startsWith("/studio/projects") : pathname.startsWith(tab.href);
          return (
            <Link
              key={tab.href}
              href={tab.href}
              aria-current={active ? "page" : undefined}
              className={`rounded-lg px-3 py-1.5 focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400 ${
                active ? "bg-neutral-800 text-white" : "text-neutral-300 hover:bg-neutral-900 hover:text-white"
              }`}
            >
              {t(tab.key)}
            </Link>
          );
        })}
      </nav>
      <LocaleToggle />
    </div>
  );
}

const PILL: Record<string, string> = {
  ready: "border-emerald-500/40 bg-emerald-500/10 text-emerald-300",
  succeeded: "border-emerald-500/40 bg-emerald-500/10 text-emerald-300",
  published: "border-emerald-500/40 bg-emerald-500/10 text-emerald-300",
  failed: "border-rose-500/40 bg-rose-500/10 text-rose-300",
  interrupted: "border-amber-500/40 bg-amber-500/10 text-amber-300",
  due: "border-amber-500/40 bg-amber-500/10 text-amber-300",
  not_configured: "border-amber-500/40 bg-amber-500/10 text-amber-300",
  ingesting: "border-indigo-500/40 bg-indigo-500/10 text-indigo-300",
  running: "border-indigo-500/40 bg-indigo-500/10 text-indigo-300",
  queued: "border-indigo-500/40 bg-indigo-500/10 text-indigo-300",
  scheduled: "border-sky-500/40 bg-sky-500/10 text-sky-300",
};

export function Pill({ status }: { status: string }) {
  const t = useT();
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium ${
        PILL[status] ?? "border-neutral-600/50 bg-neutral-700/30 text-neutral-300"
      }`}
    >
      {tDyn(t, "status", status)}
    </span>
  );
}

export function ErrorBox({ message, children }: { message: string | null; children?: ReactNode }) {
  if (!message) return null;
  return (
    <div role="alert" className="rounded-xl border border-rose-500/40 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">
      {message}
      {children}
    </div>
  );
}

export function Notice({ children }: { children: ReactNode }) {
  return (
    <div className="rounded-xl border border-indigo-500/30 bg-indigo-500/5 px-4 py-2.5 text-sm text-indigo-100">
      {children}
    </div>
  );
}

export function Loading() {
  const t = useT();
  return (
    <p role="status" aria-live="polite" className="text-sm text-neutral-400">
      {t("common.loading")}
    </p>
  );
}

export function Progress({ value, label }: { value: number; label: string }) {
  const pct = Math.round(Math.max(0, Math.min(1, value)) * 100);
  return (
    <div>
      <div className="mb-1 flex justify-between text-xs text-neutral-300">
        <span>{label}</span>
        <span>{pct}%</span>
      </div>
      <div
        role="progressbar"
        aria-label={label}
        aria-valuenow={pct}
        aria-valuemin={0}
        aria-valuemax={100}
        className="h-2 overflow-hidden rounded-full bg-neutral-800"
      >
        <div className="h-full bg-indigo-400 transition-all" style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

export function fmtDate(iso: string | null, locale: string): string {
  if (!iso) return "–";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString(locale === "en" ? "en-GB" : "de-DE", { dateStyle: "medium", timeStyle: "short" });
}
