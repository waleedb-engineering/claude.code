import { test, expect } from "./helpers/fixtures";
import { API_URL, E2E_API_TOKEN, E2E_PREFIX } from "./helpers/backend";

// ---------------------------------------------------------------------------
// Flow L — Mehrspur-Timeline: Text-Element am Abspielkopf anlegen, ziehen
// (Server speichert neue Position), teilen, Spur sperren,
// Rückgängig. Lokal, kostenlos.
// ---------------------------------------------------------------------------

const H = { "Content-Type": "application/json", "X-ClipForge-Token": E2E_API_TOKEN };

async function timeline(pid: string) {
  const v = await fetch(`${API_URL}/api/studio/projects/${pid}`).then((r) => r.json());
  return v.project.timeline as { tracks: { kind: string; locked: boolean; items: { id: string; start: number; duration: number; keyframes?: Record<string, unknown[]> }[] }[] };
}

test("Timeline: anlegen, ziehen, teilen, sperren, rückgängig", async ({ page }) => {
  test.setTimeout(120_000);
  const created = await fetch(`${API_URL}/api/studio/projects`, {
    method: "POST",
    headers: H,
    body: JSON.stringify({ workflow: "script", title: `${E2E_PREFIX} Timeline`, script: "Erster Satz hier. Zweiter Satz dort. Folge für mehr." }),
  }).then((r) => r.json());
  const pid = created.project.id as string;
  try {
    for (let i = 0; i < 60; i += 1) {
      const v = await fetch(`${API_URL}/api/studio/projects/${pid}`).then((r) => r.json());
      if (v.project.status === "ready") break;
      await new Promise((r) => setTimeout(r, 500));
    }
    await page.goto(`/studio/projects/${pid}`);
    const tl = page.getByLabel("Mehrspur-Timeline");
    await expect(tl).toBeVisible();
    await tl.getByLabel("Hinzufügen auf").selectOption("caption");
    await tl.getByLabel("Text", { exact: true }).fill("Hallo Timeline");
    await tl.getByRole("button", { name: "+ am Abspielkopf" }).click();
    const item = tl.getByTestId("tl-item");
    await expect(item).toHaveCount(1);
    await expect.poll(async () => (await timeline(pid)).tracks[0].items[0].start).toBe(0);

    // ziehen um ca. 2 s (Zoom 60 px/s → 120 px)
    const box = (await item.boundingBox())!;
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    await page.mouse.down();
    await page.mouse.move(box.x + box.width / 2 + 120, box.y + box.height / 2, { steps: 8 });
    await page.mouse.up();
    await expect.poll(async () => (await timeline(pid)).tracks[0].items[0].start).toBeGreaterThan(1.5);

    // Abspielkopf auf 3 s setzen und teilen
    const ruler = tl.getByRole("slider", { name: "Abspielkopf" });
    const rb = (await ruler.boundingBox())!;
    await page.mouse.click(rb.x + 3 * 60, rb.y + 5);
    await item.first().click();
    await tl.getByRole("button", { name: /Teilen/ }).click();
    await expect(tl.getByTestId("tl-item")).toHaveCount(2);

    // Spur sperren → Ziehen wirkt nicht mehr
    await tl.getByRole("button", { name: /^Sperren: / }).click();
    await expect.poll(async () => (await timeline(pid)).tracks[0].locked).toBe(true);

    // Rückgängig (Strg+Z) hebt das Sperren auf
    await tl.getByRole("heading", { name: "Mehrspur-Timeline" }).click();
    await page.keyboard.press("Control+z");
    await expect.poll(async () => (await timeline(pid)).tracks[0].locked, { timeout: 10_000 }).toBe(false);
  } finally {
    await fetch(`${API_URL}/api/studio/projects/${pid}`, { method: "DELETE", headers: H });
  }
});
