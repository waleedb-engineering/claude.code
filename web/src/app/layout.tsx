import type { Metadata } from "next";
import "./globals.css";
import Nav from "@/components/Nav";

export const metadata: Metadata = {
  title: "ClipForge AI — Lange Videos zu Shorts",
  description:
    "Lade ein langes Video hoch und erhalte automatisch bewertete 9:16-Kurzclips mit Untertiteln. Lokal, ohne Account.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="de" className="h-full antialiased">
      <body className="app-bg flex min-h-full flex-col">
        <Nav />
        <main className="mx-auto w-full max-w-5xl flex-1 px-5 py-8">
          {children}
        </main>
        <footer className="mx-auto w-full max-w-5xl px-5 pb-10 pt-6 text-center text-xs text-neutral-600">
          ClipForge AI · lokales MVP · der Score ist eine Einschätzung, keine
          Garantie
        </footer>
      </body>
    </html>
  );
}
