import { test as guarded, expect } from "./guards";
import {
  seedCompletedJob,
  seedYouTubeDraft,
  deleteJob,
  type SeededJob,
} from "./backend";

// ---------------------------------------------------------------------------
// Gemeinsame Fixtures.
//
// `seeded` erstellt EINMAL pro Worker einen fertigen Job (sample.mp4 +
// transcript.json → deterministisch) inklusive eines YouTube-Shorts-Drafts und
// räumt ihn am Ende wieder ab. Flows, die nur lesen/ergänzen (B–G), teilen ihn
// sich; Flow A lädt bewusst über den Browser selbst hoch.
// ---------------------------------------------------------------------------

export interface SeededContext {
  job: SeededJob;
  publishingId: string;
  clipIndex: number;
}

export const test = guarded.extend<object, { seeded: SeededContext }>({
  seeded: [
    async ({}, use) => {
      const job = await seedCompletedJob({ topN: 2 });
      const draft = await seedYouTubeDraft(job.jobId, 1);
      await use({ job, publishingId: draft.publishingId, clipIndex: 1 });
      await deleteJob(job.jobId);
    },
    { scope: "worker" },
  ],
});

export { expect };
