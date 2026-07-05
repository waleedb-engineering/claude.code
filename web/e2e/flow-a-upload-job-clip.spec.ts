import { readFileSync } from "node:fs";
import { test, expect } from "./helpers/fixtures";
import {
  TESTDATA,
  sampleVideoPath,
  uniqueUploadName,
  deleteJob,
} from "./helpers/backend";

// ---------------------------------------------------------------------------
// Flow A — Upload → Job → Clip (echte Browser-Interaktion).
//
// Der Upload läuft real über das Frontend (setInputFiles → FormData → HTTP).
// Deterministisch/schnell dank mitgeliefertem Transkript (kein Whisper). Der
// erzeugte Job wird am Ende gelöscht.
// ---------------------------------------------------------------------------

let createdJobId: string | null = null;

test.afterAll(async () => {
  if (createdJobId) await deleteJob(createdJobId);
});

test("Upload eines Videos erzeugt einen Job mit gerenderten Clips", async ({
  page,
}) => {
  const videoBuf = readFileSync(sampleVideoPath());
  const transcriptBuf = readFileSync(TESTDATA.transcript);
  const videoName = uniqueUploadName("flowA");

  await page.goto("/upload");
  await expect(
    page.getByRole("heading", { name: "Videos hochladen" }),
  ).toBeVisible();

  // Video wählen (verstecktes Mehrfach-File-Input).
  await page.locator('input[type="file"][multiple]').setInputFiles({
    name: videoName,
    mimeType: "video/mp4",
    buffer: videoBuf,
  });
  await expect(page.getByText(videoName)).toBeVisible();

  // Transkript-Input erscheint nur bei genau einer Datei.
  await page.locator('input[accept=".json"]').setInputFiles({
    name: "transcript.json",
    mimeType: "application/json",
    buffer: transcriptBuf,
  });

  await page.getByRole("button", { name: "Videos analysieren" }).click();

  // Ergebnis: genau ein Job angelegt.
  await expect(page.getByText(/Job\s+angelegt/)).toBeVisible({ timeout: 30_000 });
  await page.getByRole("button", { name: "Job öffnen" }).click();

  await page.waitForURL(/\/jobs\/[a-z0-9]+$/);
  createdJobId = page.url().split("/").pop() ?? null;
  expect(createdJobId).toBeTruthy();

  // Job läuft durch (Backend rendert Clips) — Seite pollt automatisch.
  await expect(page.getByText("Clips erkannt")).toBeVisible({ timeout: 120_000 });

  // Mindestens eine Clip-Karte mit Bearbeiten-/Publishing-Aktion.
  await expect(
    page.getByRole("link", { name: "Bearbeiten" }).first(),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: "Publishing vorbereiten" }).first(),
  ).toBeVisible();
});
