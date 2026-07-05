import { test, expect } from "./helpers/fixtures";

// ---------------------------------------------------------------------------
// Flow B — Clip-Editor → Re-Render.
//
// Passt Start/Ende an und rendert im Browser einen neuen manuellen Export
// (echter ffmpeg-Lauf über das Backend).
// ---------------------------------------------------------------------------

test("Clip-Editor rendert einen neuen manuellen Export", async ({
  page,
  seeded,
}) => {
  await page.goto(`/jobs/${seeded.job.jobId}/clips/${seeded.clipIndex}/edit`);
  await expect(
    page.getByRole("heading", { name: `Clip #${seeded.clipIndex} bearbeiten` }),
  ).toBeVisible();

  const numbers = page.locator('input[type="number"]');
  await numbers.nth(0).fill("0");
  await numbers.nth(1).fill("20");
  await expect(page.getByText(/Neue Länge:/)).toContainText("20");

  const renderBtn = page.getByRole("button", { name: "Neu rendern" });
  await expect(renderBtn).toBeEnabled();
  await renderBtn.click();

  await expect(page.getByText("Manueller Export gespeichert")).toBeVisible({
    timeout: 60_000,
  });
  await expect(page.getByText(/Export-ID:/)).toBeVisible();
});
