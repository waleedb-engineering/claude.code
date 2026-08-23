import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  timeout: 60_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  reporter: [['list']],
  use: {
    baseURL: 'http://localhost:5183',
    // Chromium liegt im Image bereit. Der gepinnte @playwright/test erwartet
    // einen anderen Build — statt einen Download anzustossen, zeigen wir auf
    // das vorhandene Binary. PW_CHROMIUM erlaubt das Ueberschreiben.
    launchOptions: {
      executablePath: process.env['PW_CHROMIUM'] ?? '/opt/pw-browsers/chromium',
    },
    trace: 'off',
  },
  webServer: {
    command: 'pnpm vite --port 5183 --strictPort',
    url: 'http://localhost:5183',
    reuseExistingServer: true,
    timeout: 120_000,
  },
});
