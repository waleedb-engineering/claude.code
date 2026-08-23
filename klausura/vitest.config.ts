import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    environment: 'node',
    include: ['packages/*/src/**/*.test.ts'],
    // Determinismus: kein Test darf sich auf echte Zeit verlassen.
    // Der Kern bekommt die Uhr injiziert (ClockPort), s. docs/klausura/08.
    testTimeout: 10_000,
  },
});
