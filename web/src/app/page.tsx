import Link from "next/link";

const STEPS = [
  {
    n: "1",
    title: "Video hochladen",
    body: "Lege ein langes Video ab — Podcast, Coaching-Call, Talk. Lokal, ohne Account.",
  },
  {
    n: "2",
    title: "Automatisch analysieren",
    body: "Transkription, Clip-Auswahl und Performance-Potential-Score laufen im Hintergrund.",
  },
  {
    n: "3",
    title: "Clips herunterladen",
    body: "Fertige 9:16-Clips mit Untertiteln, sortiert nach Score, als MP4 exportieren.",
  },
];

const FEATURES = [
  "Hook-Erkennung & Retention-Signale",
  "Automatische Clip-Auswahl aus dem Transkript",
  "Eingebrannte Untertitel (9:16)",
  "Transparenter Performance-Potential-Score",
  "Plattform-Metadaten (mit API-Key)",
  "Hook-Varianten für A/B-Ideen (mit API-Key)",
];

export default function Home() {
  return (
    <div className="flex flex-col gap-16">
      {/* Hero */}
      <section className="flex flex-col items-center pt-10 text-center">
        <span className="mb-5 inline-flex items-center gap-2 rounded-full border border-neutral-800 bg-neutral-900/60 px-3 py-1 text-xs text-neutral-400">
          <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
          Lokales MVP · läuft auf deinem Rechner
        </span>
        <h1 className="max-w-2xl text-balance text-4xl font-bold tracking-tight text-white sm:text-5xl">
          Aus langen Videos werden{" "}
          <span className="bg-gradient-to-r from-indigo-400 to-fuchsia-400 bg-clip-text text-transparent">
            starke Shorts
          </span>
        </h1>
        <p className="mt-4 max-w-xl text-pretty text-neutral-400">
          ClipForge AI findet die besten Momente, schneidet sie ins
          Hochformat, setzt Untertitel und bewertet jeden Clip — damit du
          schneller postest. Kein Viralitäts-Versprechen, nur messbare Signale.
        </p>
        <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
          <Link
            href="/upload"
            className="inline-flex items-center gap-2 rounded-xl bg-white px-5 py-2.5 font-medium text-neutral-900 transition hover:bg-neutral-200"
          >
            Video hochladen
            <svg
              className="h-4 w-4"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
            >
              <path
                d="M5 12h14m0 0-5-5m5 5-5 5"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </Link>
          <Link
            href="/jobs"
            className="rounded-xl border border-neutral-800 px-5 py-2.5 font-medium text-neutral-300 transition hover:border-neutral-700 hover:text-white"
          >
            Jobs ansehen
          </Link>
        </div>
      </section>

      {/* Steps */}
      <section className="grid gap-4 sm:grid-cols-3">
        {STEPS.map((s) => (
          <div
            key={s.n}
            className="rounded-2xl border border-neutral-800 bg-neutral-900/50 p-5"
          >
            <div className="mb-3 grid h-9 w-9 place-items-center rounded-lg bg-gradient-to-br from-indigo-500 to-fuchsia-500 text-sm font-bold text-white">
              {s.n}
            </div>
            <h3 className="font-semibold text-neutral-100">{s.title}</h3>
            <p className="mt-1 text-sm text-neutral-400">{s.body}</p>
          </div>
        ))}
      </section>

      {/* Features */}
      <section className="rounded-2xl border border-neutral-800 bg-neutral-900/40 p-6">
        <h2 className="text-lg font-semibold text-neutral-100">
          Was im MVP steckt
        </h2>
        <ul className="mt-4 grid gap-2 sm:grid-cols-2">
          {FEATURES.map((f) => (
            <li key={f} className="flex items-center gap-2 text-sm text-neutral-300">
              <svg
                className="h-4 w-4 shrink-0 text-emerald-400"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
              >
                <path
                  d="m5 13 4 4L19 7"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
              {f}
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
