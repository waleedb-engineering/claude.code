"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import AccountMenu from "./AccountMenu";

// Hauptbereiche (eine Anwendung): Dashboard · Erstellen · Streams · Editor ·
// Mediathek · Clips (Langvideo → Shorts) · Publishing · Analytics · Einstellungen
const links = [
  { href: "/studio", label: "Dashboard", exact: true },
  { href: "/studio/create", label: "Erstellen" },
  { href: "/studio/streams", label: "Streams" },
  { href: "/studio/projects", label: "Editor" },
  { href: "/studio/library", label: "Mediathek" },
  { href: "/jobs", label: "Clips", also: ["/upload"] },
  { href: "/publishing", label: "Publishing" },
  { href: "/studio/analytics", label: "Analytics" },
  { href: "/studio/setup", label: "Einstellungen", also: ["/settings"] },
];

export default function Nav() {
  const pathname = usePathname();
  return (
    <header className="sticky top-0 z-20 border-b border-neutral-800/80 bg-neutral-950/70 backdrop-blur">
      <div className="mx-auto flex max-w-6xl items-center justify-between gap-3 px-5 py-3">
        <Link href="/" className="flex items-center gap-2">
          <span className="grid h-7 w-7 place-items-center rounded-lg bg-gradient-to-br from-indigo-500 to-fuchsia-500 text-sm font-bold text-white">
            C
          </span>
          <span className="font-semibold tracking-tight">
            ClipForge <span className="text-indigo-400">AI</span>
          </span>
        </Link>
        <nav aria-label="Hauptnavigation" className="flex items-center gap-1 overflow-x-auto text-sm">
          {links.map((l) => {
            const active = l.exact
              ? pathname === l.href
              : pathname.startsWith(l.href) || (l.also ?? []).some((a) => pathname.startsWith(a));
            return (
              <Link
                key={l.href}
                href={l.href}
                aria-current={active ? "page" : undefined}
                className={`rounded-lg px-3 py-1.5 transition ${
                  active
                    ? "bg-neutral-800 text-white"
                    : "text-neutral-400 hover:text-white hover:bg-neutral-900"
                }`}
              >
                {l.label}
              </Link>
            );
          })}
        </nav>
        <AccountMenu />
      </div>
    </header>
  );
}
