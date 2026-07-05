import { test, expect } from "./helpers/fixtures";
import { E2E_PREFIX } from "./helpers/backend";

// ---------------------------------------------------------------------------
// Flow D — Globale Publishing-Übersicht (/publishing).
//
// Suche (auf das E2E-Präfix begrenzt → keine Fremddaten), Plattform-Filter und
// Duplizieren eines Drafts.
// ---------------------------------------------------------------------------

test("Globale Publishing-Übersicht: Suche, Filter, Duplizieren", async ({
  page,
  seeded,
}) => {
  await page.goto("/publishing");
  await expect(page.getByRole("heading", { name: "Publishing" })).toBeVisible();

  // Auf unsere Drafts eingrenzen (Isolierung).
  await page
    .getByPlaceholder("Suche in Titel/Caption…")
    .fill(`${E2E_PREFIX} draft`);
  await expect(page.getByText(`${E2E_PREFIX} draft`).first()).toBeVisible();

  // Plattform-Filter (zweites Select) auf YouTube Shorts — Draft bleibt sichtbar.
  await page.locator("select").nth(1).selectOption("youtube_shorts");
  // Über die Pack-ZIP-URL (enthält publishing_id) eindeutig identifizieren —
  // NICHT per .first(), da "Duplizieren" selbst einen zweiten, ebenfalls
  // passenden Eintrag erzeugt und die Liste danach neu lädt (Reihenfolge/
  // Position sind nach dem Duplizieren nicht mehr verlässlich).
  const row = page
    .locator("article")
    .filter({ has: page.locator(`a[href*="/publishing/${seeded.publishingId}/pack.zip"]`) });
  await expect(row).toBeVisible();

  // Duplizieren.
  await row.getByRole("button", { name: "Duplizieren" }).click();
  await row.getByRole("button", { name: "Bestätigen" }).click();
  await expect(row.getByText(/Dupliziert als/)).toBeVisible();

  void seeded; // Draft wurde vom Worker-Fixture bereitgestellt.
});
