import { expect, test } from '@playwright/test';
import { fileURLToPath } from 'node:url';

const PDF = fileURLToPath(new URL('./fixtures/altklausur.pdf', import.meta.url));

/**
 * Der vollstaendige Weg der M1-Definition-of-Done:
 * echte Klausur importieren, drei Aufgaben markieren, eine unter laufendem
 * Timer bearbeiten, App neu starten, den Versuch wiederfinden.
 */
test.describe('M1 · Import bis Versuch', () => {
  test.beforeEach(async ({ page }) => {
    // Jeder Lauf beginnt bei null — sonst haengt das Ergebnis am vorigen Test.
    await page.goto('/');
    await page.evaluate(async () => {
      for (const name of ['klausura', 'klausura-blobs']) {
        await new Promise<void>((res) => {
          const req = indexedDB.deleteDatabase(name);
          req.onsuccess = () => res();
          req.onerror = () => res();
          req.onblocked = () => res();
        });
      }
    });
    await page.reload();
  });

  test('importieren, drei Aufgaben markieren, loesen, neu starten, wiederfinden', async ({ page }) => {
    // --- Import -----------------------------------------------------------
    await page.getByTestId('nav-import').click();
    await page.getByTestId('exam-duration').fill('90');
    await page.getByTestId('exam-total').fill('30,5');
    await page.getByTestId('pdf-input').setInputFiles(PDF);

    await expect(page.getByTestId('page-indicator')).toContainText('SEITE 1 VON 2');

    // --- Drei Aufgaben markieren ------------------------------------------
    const marks = [
      { ordinal: 'A1', points: '8,5', topic: 'Netzwerke' },
      { ordinal: 'A2', points: '12', topic: 'Wechselstrom' },
      { ordinal: 'A3', points: '10', topic: 'Leistung' },
    ];

    for (const m of marks) {
      const frame = page.getByTestId('page-frame');
      const box = await frame.boundingBox();
      expect(box).not.toBeNull();
      if (box === null) return;

      // Rahmen wirklich ziehen — nicht per Tastaturweg abkuerzen.
      await page.mouse.move(box.x + 40, box.y + 40);
      await page.mouse.down();
      await page.mouse.move(box.x + box.width - 40, box.y + 160, { steps: 8 });
      await page.mouse.up();
      await expect(page.getByTestId('draft-rect')).toBeVisible();

      await page.getByTestId('seg-ordinal').fill(m.ordinal);
      await page.getByTestId('seg-points').fill(m.points);
      await page.getByTestId('seg-topic').fill(m.topic);
      await page.getByTestId('seg-save').click();
    }

    // Die Kreuzprobe muss aufgehen: 8,5 + 12 + 10 = 30,5.
    await expect(page.getByTestId('point-sum')).toContainText('stimmt mit der Klausur überein');
    await expect(page.getByTestId('seg-list').locator('li')).toHaveCount(3);

    await page.getByTestId('seg-finish').click();

    // --- Atlas ------------------------------------------------------------
    await expect(page.getByTestId('atlas-count')).toContainText('3 AUFGABEN');
    await expect(page.getByTestId('task-card')).toHaveCount(3);

    // --- Loesen unter Zeitdruck -------------------------------------------
    await page.getByTestId('task-card').first().click();
    await expect(page.getByTestId('timer')).toBeVisible();

    const firstRead = await page.getByTestId('timer-value').textContent();
    await page.waitForTimeout(2200);
    const secondRead = await page.getByTestId('timer-value').textContent();
    expect(secondRead).not.toBe(firstRead); // Der Timer laeuft wirklich.

    await page.getByTestId('answer-value').fill('12');
    await page.getByTestId('answer-unit').selectOption('kΩ');
    await page.getByTestId('submit-attempt').click();

    await expect(page.getByTestId('atlas-count')).toBeVisible();

    // --- Neustart ---------------------------------------------------------
    await page.reload();
    await expect(page.getByTestId('atlas-count')).toContainText('3 AUFGABEN');
    await page.getByTestId('task-card').first().click();

    const rows = page.getByTestId('attempt-row');
    await expect(rows).toHaveCount(1);
    await expect(page.getByTestId('attempt-answer')).toContainText('12');
    await expect(page.getByTestId('attempt-answer')).toContainText('kΩ');
    // Die gemessene Zeit ist echt: mindestens die zwei gewarteten Sekunden.
    const elapsed = await page.getByTestId('attempt-elapsed').textContent();
    expect(Number.parseInt(elapsed ?? '0', 10)).toBeGreaterThanOrEqual(2);
  });

  test('weist denselben Import ein zweites Mal ab', async ({ page }) => {
    await page.getByTestId('nav-import').click();
    await page.getByTestId('pdf-input').setInputFiles(PDF);
    await expect(page.getByTestId('page-indicator')).toBeVisible();

    await page.getByTestId('nav-import').click();
    await page.getByTestId('pdf-input').setInputFiles(PDF);
    await expect(page.getByTestId('import-error')).toContainText('bereits importiert');
  });

  test('Befehlspalette oeffnet mit Strg+K und ist mit der Tastatur bedienbar', async ({ page }) => {
    await page.locator('body').click(); // Fokus ins Dokument holen
    await page.keyboard.press('Control+k');
    await expect(page.getByTestId('command-palette')).toBeVisible();
    await page.getByTestId('palette-input').fill('Import');
    await page.keyboard.press('Enter');
    await expect(page.getByTestId('pdf-input')).toBeVisible();
  });
});
