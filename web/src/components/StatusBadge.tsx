import type { JobStatus } from "@/lib/types";
import Spinner from "./Spinner";

const MAP: Record<JobStatus, { label: string; cls: string }> = {
  queued: {
    label: "In Warteschlange",
    cls: "bg-neutral-700/30 text-neutral-300 border-neutral-600/40",
  },
  processing: {
    label: "Wird analysiert",
    cls: "bg-indigo-500/10 text-indigo-300 border-indigo-500/30",
  },
  completed: {
    label: "Fertig",
    cls: "bg-emerald-500/10 text-emerald-300 border-emerald-500/30",
  },
  failed: {
    label: "Fehlgeschlagen",
    cls: "bg-rose-500/10 text-rose-300 border-rose-500/30",
  },
  interrupted: {
    label: "Unterbrochen",
    cls: "bg-amber-500/10 text-amber-300 border-amber-500/30",
  },
  incomplete: {
    label: "Unvollständig",
    cls: "bg-amber-500/10 text-amber-300 border-amber-500/30",
  },
  canceled: {
    label: "Abgebrochen",
    cls: "bg-neutral-700/30 text-neutral-300 border-neutral-600/40",
  },
};

export default function StatusBadge({ status }: { status: JobStatus }) {
  const { label, cls } = MAP[status] ?? MAP.queued;
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium ${cls}`}
    >
      {(status === "processing" || status === "queued") && (
        <Spinner className="h-3 w-3" />
      )}
      {label}
    </span>
  );
}
