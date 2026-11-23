import { defineConfig } from '@playwright/test';

// E2E contra el servidor local real. PENFOLD_URL y PENFOLD_TOKEN se pasan
// desde la terminal. Requiere `pnpm exec playwright install firefox`.
export default defineConfig({
  testDir: './e2e',
  timeout: 45_000,
  expect: { timeout: 15_000 },
  workers: 1,
  reporter: 'list',
  use: {
    baseURL: process.env.PENFOLD_URL ?? 'http://127.0.0.1:8791',
    browserName: 'firefox',
    launchOptions: process.env.FIREFOX_BIN
      ? { executablePath: process.env.FIREFOX_BIN }
      : undefined,
    viewport: { width: 1600, height: 1000 },
    screenshot: 'only-on-failure',
  },
});
