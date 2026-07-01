"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { listJobs } from "@/lib/api";
import type { JobSummary } from "@/lib/types";
import StatusBadge from "@/components/StatusBadge";
import Spinner from "@/components/Spinner";
import { fmtDateTime } from "@/lib/format";

export default function JobsPage() {
  const [jobs, setJobs] = useState<JobSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    try {
      setError(null);
      setJobs(await listJobs());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Konnte Jobs nicht laden.");
    }
  }

  useEffect(() => {
    load();
    const id = setInterval(load, 4000); // leichte Aktualisierung
    return () => clearInterval(id);
  }, []);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-white">Jobs</h1>
          <p className="mt-1 text-sm text-neutral-400">
            Alle Analysen auf diesem Rechner.
          </p>
        </div>
        <Link
          href="/upload"
          className="rounded-xl bg-white px-4 py-2 text-sm font-medium text-neutral-900 transition hover:bg-neutral-200"
        >
          + Neuer Job
        </Link>
      </div>

      {/* Error */}
      {error && (
        <div className="rounded-xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-300">
          {error}
        </div>
      )}

      {/* Loading */}
      {jobs === null && !error && (
        <div className="flex items-center gap-2 text-sm text-neutral-400">
          <Spinner className="h-4 w-4" /> Lade Jobs …
        </div>
      )}

      {/* Empty */}
      {jobs !== null && jobs.length === 0 && !error && (
        <div className="rounded-2xl border border-dashed border-neutral-800 bg-neutral-900/30 p-10 text-center">
          <p className="text-neutral-300">Noch keine Jobs.</p>
          <Link
            href="/upload"
            className="mt-3 inline-block rounded-lg bg-white px-4 py-2 text-sm font-medium text-neutral-900 hover:bg-neutral-200"
          >
            Erstes Video hochladen
          </Link>
        </div>
      )}

      {/* List */}
      {jobs && jobs.length > 0 && (
        <ul className="space-y-2">
          {jobs.map((j) => (
            <li key={j.id}>
              <Link
                href={`/jobs/${j.id}`}
                className="flex items-center justify-between gap-4 rounded-xl border border-neutral-800 bg-neutral-900/50 px-4 py-3 transition hover:border-neutral-700"
              >
                <div className="min-w-0">
                  <p className="truncate font-medium text-neutral-100">
                    {j.filename}
                  </p>
                  <p className="mt-0.5 text-xs text-neutral-500">
                    {fmtDateTime(j.created_at)} · {j.id}
                  </p>
                  {j.restored && (
                    <p className="mt-0.5 text-[11px] text-neutral-500">
                      ↻ Aus lokalem Speicher wiederhergestellt
                    </p>
                  )}
                </div>
                <div className="flex shrink-0 items-center gap-3">
                  {typeof j.clip_count === "number" && (
                    <span className="text-sm text-neutral-400">
                      {j.clip_count} Clips
                    </span>
                  )}
                  <StatusBadge status={j.status} />
                </div>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
