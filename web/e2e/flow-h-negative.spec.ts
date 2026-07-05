import { test, expect } from "./helpers/fixtures";
import { E2E_PREFIX } from "./helpers/backend";

// ---------------------------------------------------------------------------
// Flow H — Negativ-/Fehlerfälle (Aufgabe 10).
//
// Jeder Fall muss sauber behandelt werden: kein White-Screen, keine
// unbehandelten Page-Errors. Der bewusst offline gestellte Fall gibt exakt die
// erwarteten Netzwerk-Fehlermuster frei (kein pauschales Ignore).
// ---------------------------------------------------------------------------

test("Ungültiger Datei-Typ beim Upload wird als Fehler angezeigt", async ({
  page,
  errors,
}) => {
  // Der Server lehnt bewusst mit HTTP 400 ab — die App zeigt das sauber an.
  // Der zugehörige Netzwerk-Console-Eintrag ist erwartet, sonst nichts.
  errors.allow(/Failed to load resource.*40[0-9]/);
  await page.goto("/upload");
  await page.locator('input[type="file"][multiple]').setInputFiles({
    name: `${E2E_PREFIX}-notes.txt`,
    mimeType: "text/plain",
    buffer: Buffer.from("nicht-video"),
  });
  await page.getByRole("button", { name: "Videos analysieren" }).click();
  await expect(page.getByText(/Ungültiger Dateityp/)).toBeVisible({
    timeout: 20_000,
  });
});

test("Zu viele Batch-Dateien lösen eine klare Grenzmeldung aus", async ({
  page,
}) => {
  await page.goto("/upload");
  const many = Array.from({ length: 11 }, (_, i) => ({
    name: `${E2E_PREFIX}-batch-${i + 1}.mp4`,
    mimeType: "video/mp4",
    buffer: Buffer.from(`fake-${i}`),
  }));
  await page.locator('input[type="file"][multiple]').setInputFiles(many);
  await expect(page.getByText(/Maximal \d+ Dateien pro Batch/)).toBeVisible();
});

test("Ungültige Re-Render-Grenzen: Warnung + deaktivierter Button", async ({
  page,
  seeded,
}) => {
  await page.goto(`/jobs/${seeded.job.jobId}/clips/${seeded.clipIndex}/edit`);
  const numbers = page.locator('input[type="number"]');
  await numbers.nth(0).fill("30");
  await numbers.nth(1).fill("10"); // Ende < Start
  await expect(
    page.getByText("Endzeit muss größer als Startzeit sein."),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "Neu rendern" })).toBeDisabled();
});

test("Nicht existierender Job zeigt Fehler statt White-Screen", async ({
  page,
  errors,
}) => {
  // Erwartet: das Backend antwortet mit 404 für einen unbekannten Job.
  errors.allow(/Failed to load resource.*404/);
  await page.goto("/jobs/deadbeef0000");
  // Kein Absturz: Grund-Layout bleibt, ein Fehlerhinweis erscheint.
  await expect(page.getByRole("heading", { name: "Job" })).toBeVisible();
  await expect(
    page.getByText(/nicht gefunden|konnte nicht geladen|Not Found|404/i).first(),
  ).toBeVisible({ timeout: 15_000 });
});

test("Leerer Publishing-Zustand wird sauber angezeigt", async ({ page }) => {
  await page.goto("/publishing");
  await page
    .getByPlaceholder("Suche in Titel/Caption…")
    .fill("zzz-nonexistent-query-xyz");
  await expect(
    page.getByText(/Keine Publishing-Drafts gefunden/),
  ).toBeVisible({ timeout: 15_000 });
});

test("Backend nicht erreichbar: freundlicher Fehler statt Absturz", async ({
  page,
  errors,
}) => {
  // Bewusst provozierter Offline-Fall: nur diese Netzwerk-Muster freigeben.
  errors.allow(/Failed to load resource/);
  errors.allow(/net::ERR/);
  errors.allow(/Backend nicht erreichbar/);

  await page.route("**/api/**", (route) => route.abort("failed"));
  await page.goto("/jobs");
  await expect(page.getByRole("heading", { name: "Jobs" })).toBeVisible();
  await expect(page.getByText(/Backend nicht erreichbar/)).toBeVisible({
    timeout: 15_000,
  });
});
