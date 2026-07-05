import { test, expect } from "./helpers/fixtures";

// ---------------------------------------------------------------------------
// Flow C — Publishing Planner (lokale Drafts, kein Upload).
//
// Legt im Browser einen neuen Draft aus einem Auto-Clip an und validiert ihn.
// ---------------------------------------------------------------------------

test("Publishing Planner legt einen Draft an und validiert ihn", async ({
  page,
  seeded,
}) => {
  await page.goto(`/jobs/${seeded.job.jobId}/publishing`);
  await expect(
    page.getByRole("heading", { name: "Publishing Planner" }),
  ).toBeVisible();

  // Der geseedete YouTube-Draft ist sichtbar.
  await expect(page.locator(`#draft-${seeded.publishingId}`)).toBeVisible();

  // Neuen Draft aus Auto-Clip #2 als Instagram Reels anlegen.
  await page.locator("select").first().selectOption("clip:2");
  await page.locator("select").nth(1).selectOption("instagram_reels");
  await page.getByRole("button", { name: "Draft anlegen" }).click();

  const newest = page.locator("article").first();
  await expect(newest.getByText("Instagram Reels")).toBeVisible();

  // Validierung (Checkliste) auslösen.
  await newest.getByRole("button", { name: "Prüfen" }).click();
  await expect(newest.getByText("MP4 bereit")).toBeVisible();
  await expect(newest.getByText("Plattform gewählt")).toBeVisible();
});
