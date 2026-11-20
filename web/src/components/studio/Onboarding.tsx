"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { studio, type ProjectSummary } from "@/lib/studio";
import { cardCls } from "./ui";

type Step = { done: boolean; title: string; text: string; href: string; cta: string };

/** Erste Schritte: Status je Schritt aus echten Daten (nichts wird angenommen). */
export default function Onboarding({ projects }: { projects: ProjectSummary[] | null }) {
  const [state, setState] = useState<{ ai: string | null; library: number; streams: number; exported: number } | null>(null);
  const [hidden, setHidden] = useState(false);

  useEffect(() => {
    const t = setTimeout(() => {
      try {
        setHidden(window.localStorage.getItem("cf.onboarding.hidden") === "1");
      } catch {
        /* Speicher gesperrt → Karte bleibt sichtbar */
      }
    }, 0);
    Promise.all([studio.agentEngines(), studio.library(), studio.streams()])
      .then(([eng, lib, streams]) => {
        const local = eng.engines.find((e) => e.id === "ollama" && e.ready);
        const cloud = eng.engines.find((e) => e.paid && e.ready);
        setState({
          ai: local ? "Ollama (lokal)" : cloud ? `${cloud.label}` : null,
          library: lib.items.length,
          streams: streams.length,
          exported: 0,
        });
      })
      .catch(() => setState({ ai: null, library: 0, streams: 0, exported: 0 }));
    return () => clearTimeout(t);
  }, []);

  if (hidden || !state) return null;
  const nProjects = projects?.length ?? 0;
  const exported = (projects ?? []).filter((p) => p.export_count > 0).length;
  const steps: Step[] = [
    { done: true, title: "ClipForge läuft", text: "Backend und Oberfläche sind verbunden.", href: "/studio/setup", cta: "Status" },
    {
      done: true,
      title: "KI wählen",
      text: state.ai
        ? `Zusätzlich verfügbar: ${state.ai}. Der Regel-Assistent funktioniert immer ohne Kosten.`
        : "Lokal und kostenlos: Regel-Assistent (sofort). Optional: Ollama auf diesem Rechner oder ein Cloud-Schlüssel (kostenpflichtig, nur nach Bestätigung).",
      href: "/studio/setup",
      cta: "Einrichten",
    },
    { done: state.library > 0 || nProjects > 0, title: "Medien importieren", text: "Eigene Videos, Bilder, Musik in die Mediathek laden.", href: "/studio/library", cta: "Mediathek" },
    {
      done: nProjects > 0 || state.streams > 0,
      title: "Video erzeugen oder Stream analysieren",
      text: "Aus Skript/Prompt/PDF ein Video erstellen oder eigenes VOD + Chat auswerten.",
      href: nProjects > 0 ? "/studio/streams" : "/studio/create",
      cta: nProjects > 0 ? "Streams" : "Erstellen",
    },
    { done: nProjects > 0, title: "Bearbeiten", text: "Im Editor per Timeline oder per KI-Chat ändern.", href: "/studio/projects", cta: "Editor" },
    { done: exported > 0, title: "Vorschau & Export", text: "Vorschau rendern, dann final exportieren.", href: "/studio/projects", cta: "Projekte" },
  ];
  const open = steps.filter((s) => !s.done).length;
  return (
    <section className={`${cardCls} space-y-3`} aria-label="Erste Schritte">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-white">Erste Schritte {open === 0 ? "✓" : `(${steps.length - open}/${steps.length})`}</h2>
        <button
          type="button"
          className="text-xs text-neutral-500 underline"
          onClick={() => {
            setHidden(true);
            try {
              window.localStorage.setItem("cf.onboarding.hidden", "1");
            } catch {
              /* egal */
            }
          }}
        >
          ausblenden
        </button>
      </div>
      <ol className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
        {steps.map((s, i) => (
          <li key={s.title} className={`rounded-xl border p-3 ${s.done ? "border-emerald-800/60" : "border-neutral-800"}`}>
            <p className="text-sm font-medium text-white">
              {s.done ? "✓" : `${i + 1}.`} {s.title}
            </p>
            <p className="mt-1 text-xs text-neutral-400">{s.text}</p>
            {!s.done && (
              <Link href={s.href} className="mt-2 inline-block text-xs text-indigo-300 underline">
                {s.cta} →
              </Link>
            )}
          </li>
        ))}
      </ol>
    </section>
  );
}
