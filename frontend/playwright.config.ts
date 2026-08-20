import { defineConfig, devices } from '@playwright/test'

/**
 * End-to-end tests run against a *running* Ermes instance: they exercise the
 * real API, the real SQLite store and the real retrieval path, which is the
 * point — the unit tests already cover the pieces in isolation.
 *
 * Start the stack first (`.\scripts\avvia_ermes.ps1`), then `npm run e2e`.
 * Credentials are read from the environment, never hard-coded here.
 */
export default defineConfig({
  testDir: './e2e',
  timeout: 60_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  reporter: process.env.CI ? 'list' : 'line',
  use: {
    baseURL: process.env.ERMES_E2E_URL ?? 'http://localhost:3000',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
  ],
})
