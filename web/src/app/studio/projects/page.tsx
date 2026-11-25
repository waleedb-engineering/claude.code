"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { errorMessage, studio, type ProjectSummary } from "@/lib/studio";
import { ErrorBox, Pill, cardCls, inputCls, primaryCls } from "@/components/studio/ui";

/** Einstieg „Editor“: alle Projekte durchsuchen und im Editor öffnen. */
export default function ProjectsPage() {
  const [projects, setProjects] = useState<ProjectSummary[] | null>(null);
  const [q, setQ] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    studio
      .projects()
      .then(setProjects)
      .catch((e) => setError(errorMessage(e)));
  }, []);

  const shown = useMemo(
    () => (projects ?? []).filter((p) => p.title.toLowerCase().includes(q.toLowerCase()) || p.workflow.includes(q.toLowerCase())),
    [projects, q],
  );

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-white">Editor</h1>
          <p className="text-sm text-neutral-400">Projekt wählen: Szenen, Mehrspur-Timeline, Untertitel, KI-Assistent und Export.</p>
        </div>
        <Link href="/studio/create" className={primaryCls}>
          + Neues Video
        </Link>
      </div>
      <input aria-label="Projekte suchen" placeholder="Projekte suchen" className={`${inputCls} max-w-sm`} value={q} onChange={(e) => setQ(e.target.value)} />
      {error && <ErrorBox message={error} />}
      {projects === null && !error && <p className="text-sm text-neutral-400">Lädt …</p>}
      {projects?.length === 0 && <p className={`${cardCls} text-sm text-neutral-400`}>Noch keine Projekte — mit „Neues Video“ beginnen.</p>}
      <ul className="space-y-2">
        {shown.map((p) => (
          <li key={p.id} className={`${cardCls} flex flex-wrap items-center justify-between gap-2`}>
            <div>
              <Link href={`/studio/projects/${p.id}`} className="font-medium text-white hover:underline">
                {p.title}
              </Link>
              <p className="text-xs text-neutral-400">
                {p.workflow} · {p.scene_count} Szenen · {p.aspect_ratio} · v{p.version}
              </p>
            </div>
            <Pill status={p.status} />
          </li>
        ))}
      </ul>
    </div>
  );
}
