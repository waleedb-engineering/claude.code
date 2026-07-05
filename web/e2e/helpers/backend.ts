import { execFileSync } from "node:child_process";
import { existsSync, mkdtempSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

// ---------------------------------------------------------------------------
// Backend-Seeding & Cleanup (Aufgabe 12 — Testdaten-Isolierung).
//
// Diese Helfer sprechen das Backend direkt an, um Voraussetzungen (ein fertiger
// Job mit Clips, ein Publishing-Draft) deterministisch bereitzustellen. Die
// Flows SELBST laufen über den Browser. Alle erzeugten Jobs tragen ein
// eindeutiges E2E-Präfix und werden am Ende wieder gelöscht — es werden nie
// fremde/echte Daten angefasst.
// ---------------------------------------------------------------------------

export const API_URL = process.env.E2E_API_URL ?? "http://127.0.0.1:8000";

export const E2E_PREFIX = "e2e-smoke";

const API_DIR = join(__dirname, "..", "..", "..", "api");
export const TESTDATA = {
  // transcript.json ist im Repo eingecheckt (60s, wortgenau) → deterministisch.
  transcript: join(API_DIR, "testdata", "transcript.json"),
};

// sample.mp4 ist bewusst NICHT eingecheckt (.gitignore). Für einen frischen
// Clone (CI) erzeugen wir eine deterministische 60s-Fixture (schwarz + Sinus,
// passend zur 60s-transcript.json) einmalig via ffmpeg. Lokal wird die
// vorhandene Datei wiederverwendet.
let cachedSample: string | null = null;
export function sampleVideoPath(): string {
  if (cachedSample) return cachedSample;
  const tracked = join(API_DIR, "testdata", "sample.mp4");
  if (existsSync(tracked)) {
    cachedSample = tracked;
    return tracked;
  }
  const dir = mkdtempSync(join(tmpdir(), "clipforge-e2e-"));
  const out = join(dir, "sample.mp4");
  execFileSync(
    "ffmpeg",
    [
      "-y",
      "-f", "lavfi", "-i", "color=c=black:s=640x360:r=24:d=60",
      "-f", "lavfi", "-i", "sine=frequency=220:duration=60",
      "-shortest",
      "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
      "-c:a", "aac",
      out,
    ],
    { stdio: "ignore" },
  );
  cachedSample = out;
  return out;
}

const RUN_ID = `${Date.now().toString(36)}`;
let counter = 0;

/** Eindeutiger, klar als E2E erkennbarer Dateiname für einen Job-Upload. */
export function uniqueUploadName(label = "sample"): string {
  counter += 1;
  return `${E2E_PREFIX}-${label}-${RUN_ID}-${counter}.mp4`;
}

function fileBlob(path: string, type: string): Blob {
  const buf = readFileSync(path);
  return new Blob([buf], { type });
}

export interface SeededJob {
  jobId: string;
  filename: string;
}

/**
 * Lädt sample.mp4 + transcript.json hoch (überspringt Whisper → deterministisch,
 * schnell) und wartet, bis der Job fertig ist. Reframe = center hält das Rendern
 * leichtgewichtig.
 */
export async function seedCompletedJob(opts?: {
  topN?: number;
  label?: string;
}): Promise<SeededJob> {
  const filename = uniqueUploadName(opts?.label ?? "sample");
  const form = new FormData();
  form.append("file", fileBlob(sampleVideoPath(), "video/mp4"), filename);
  form.append(
    "transcript",
    fileBlob(TESTDATA.transcript, "application/json"),
    "transcript.json",
  );
  form.append("top_n", String(opts?.topN ?? 2));
  form.append("remove_silence", "false");
  form.append("caption_mode", "karaoke");
  form.append("caption_style", "high_energy");
  form.append("reframe_mode", "center");
  form.append("advanced_analysis", "true");

  const res = await fetch(`${API_URL}/api/jobs`, { method: "POST", body: form });
  if (!res.ok) {
    throw new Error(`seedCompletedJob upload failed: ${res.status}`);
  }
  const { job_id } = (await res.json()) as { job_id: string };
  await waitForJobStatus(job_id, "completed");
  return { jobId: job_id, filename };
}

export async function waitForJobStatus(
  jobId: string,
  target: "completed" | "failed",
  timeoutMs = 120_000,
): Promise<string> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const res = await fetch(`${API_URL}/api/jobs/${jobId}`);
    if (res.ok) {
      const job = (await res.json()) as { status: string };
      if (job.status === "completed" || job.status === "failed") {
        return job.status;
      }
    }
    await new Promise((r) => setTimeout(r, 1500));
  }
  throw new Error(`Job ${jobId} reached no terminal status within ${timeoutMs}ms`);
}

export interface SeededDraft {
  publishingId: string;
}

/** Legt einen YouTube-Shorts-Publishing-Draft für einen Auto-Clip an. */
export async function seedYouTubeDraft(
  jobId: string,
  clipIndex = 1,
  title = `${E2E_PREFIX} draft`,
): Promise<SeededDraft> {
  const create = await fetch(`${API_URL}/api/jobs/${jobId}/publishing`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      platform: "youtube_shorts",
      source_type: "auto_clip",
      source_clip_index: clipIndex,
    }),
  });
  if (!create.ok) throw new Error(`seedYouTubeDraft failed: ${create.status}`);
  const draft = (await create.json()) as { publishing_id: string };

  // Titel/Caption/Hashtags setzen, damit die Übersicht durchsuchbar ist.
  await fetch(
    `${API_URL}/api/jobs/${jobId}/publishing/${draft.publishing_id}`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        title,
        caption: `${E2E_PREFIX} caption`,
        hashtags: [`#${E2E_PREFIX}`],
      }),
    },
  );
  return { publishingId: draft.publishing_id };
}

export async function deleteJob(jobId: string): Promise<void> {
  try {
    await fetch(`${API_URL}/api/jobs/${jobId}?force=true`, { method: "DELETE" });
  } catch {
    /* Cleanup ist best-effort */
  }
}
