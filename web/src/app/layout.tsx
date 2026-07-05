import type { Metadata } from "next";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import "./globals.css";
import Nav from "@/components/Nav";

export const metadata: Metadata = {
  title: "ClipForge AI — Lange Videos zu Shorts",
  description:
    "Lade ein langes Video hoch und erhalte automatisch bewertete 9:16-Kurzclips mit Untertiteln. Lokal, ohne Account.",
};

// Repo-weite VERSION-Datei (Single Source of Truth) — serverseitig gelesen,
// kein zusätzlicher Client-Request nötig. Defensiv: fehlt die Datei (z.B.
// ungewöhnliches Deployment), bleibt die Fußzeile einfach ohne Versionsangabe.
function readVersion(): string | null {
  try {
    return readFileSync(join(process.cwd(), "..", "VERSION"), "utf-8").trim();
  } catch {
    return null;
  }
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const version = readVersion();
  return (
    <html lang="de" className="h-full antialiased">
      <body className="app-bg flex min-h-full flex-col">
        <Nav />
        <main className="mx-auto w-full max-w-5xl flex-1 px-5 py-8">
          {children}
        </main>
        <footer className="mx-auto w-full max-w-5xl px-5 pb-10 pt-6 text-center text-xs text-neutral-600">
          ClipForge AI{version ? ` · v${version}` : ""} · lokales MVP · der
          Score ist eine Einschätzung, keine Garantie
        </footer>
      </body>
    </html>
  );
}
