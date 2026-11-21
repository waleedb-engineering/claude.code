import { execFileSync } from "node:child_process";
import { mkdtempSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test, expect } from "./helpers/fixtures";
import { API_URL, E2E_API_TOKEN, E2E_PREFIX } from "./helpers/backend";

// ---------------------------------------------------------------------------
// Flow N — Live-Vorschau: Position eines animierten Overlays folgt derselben
// Keyframe-Kurve wie der Render (Abspielkopf-Scrubbing), Text erscheint zeitgenau.
// ---------------------------------------------------------------------------

const H = { "Content-Type": "application/json", "X-ClipForge-Token": E2E_API_TOKEN };

test("Timeline-Live-Vorschau: Keyframe-Position und Text folgen dem Abspielkopf", async ({ page }) => {
  test.setTimeout(120_000);
  const created = await fetch(`${API_URL}/api/studio/projects`, {
    method: "POST",
    headers: H,
    body: JSON.stringify({ workflow: "script", title: `${E2E_PREFIX} Preview`, script: "Erster Satz hier. Zweiter Satz dort. Folge für mehr." }),
  }).then((r) => r.json());
  const pid = created.project.id as string;
  try {
    for (let i = 0; i < 60; i += 1) {
      const v = await fetch(`${API_URL}/api/studio/projects/${pid}`).then((r) => r.json());
      if (v.project.status === "ready") break;
      await new Promise((r) => setTimeout(r, 500));
    }
    const dir = mkdtempSync(join(tmpdir(), "cf-prev-"));
    const png = join(dir, "dot.png");
    execFileSync("ffmpeg", ["-v", "error", "-y", "-f", "lavfi", "-i", "color=c=red:s=40x40:d=1", "-frames:v", "1", png]);
    const form = new FormData();
    form.append("file", new Blob([readFileSync(png)], { type: "image/png" }), "dot.png");
    const media = await fetch(`${API_URL}/api/studio/projects/${pid}/media`, { method: "POST", headers: { "X-ClipForge-Token": E2E_API_TOKEN }, body: form }).then((r) => r.json());
    const v = await fetch(`${API_URL}/api/studio/projects/${pid}`).then((r) => r.json());
    await fetch(`${API_URL}/api/studio/projects/${pid}/timeline/ops`, {
      method: "POST",
      headers: H,
      body: JSON.stringify({
        expected_version: v.project.version,
        ops: [
          { op: "add_item", track_kind: "overlay", item: { src: media.name, start: 0, duration: 4, scale: 0.2, y: 0.5, keyframes: { x: [{ t: 0, v: 0.2 }, { t: 2, v: 0.8 }] } } },
          { op: "add_item", track_kind: "caption", item: { text: "LIVE", start: 1, duration: 1 } },
        ],
      }),
    });
    await page.goto(`/studio/projects/${pid}`);
    const stage = page.getByTestId("tl-preview");
    const layer = stage.getByTestId("tl-preview-layer");
    await expect(layer).toHaveCount(1);
    const centerX = async () => {
      const s = (await stage.boundingBox())!;
      const b = (await layer.boundingBox())!;
      return (b.x + b.width / 2 - s.x) / s.width;
    };
    expect(await centerX()).toBeCloseTo(0.2, 1);
    await expect(stage.getByTestId("tl-preview-caption")).toHaveCount(0);
    // Abspielkopf auf 1,5 s → x = 0,2 + 0,6 * 0,75 = 0,65 (linear), Text sichtbar
    const ruler = page.getByRole("slider", { name: "Abspielkopf" });
    await ruler.click({ position: { x: 1.5 * 60, y: 5 } });
    await expect(page.getByTestId("tl-playhead")).toContainText("0:01.5");
    await expect.poll(centerX).toBeGreaterThan(0.6);
    expect(await centerX()).toBeLessThan(0.7);
    await expect(stage.getByTestId("tl-preview-caption")).toHaveText("LIVE");
    // Bild für Bild vor
    await page.getByRole("button", { name: "Ein Bild vor" }).click();
    await expect(page.getByTestId("tl-playhead")).toContainText(/0:01\.[56]/);
  } finally {
    await fetch(`${API_URL}/api/studio/projects/${pid}`, { method: "DELETE", headers: H });
  }
});
