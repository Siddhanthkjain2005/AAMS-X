import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  workers: 1,
  timeout: 90000,
  expect: { timeout: 15000 },
  reporter: [['list']],
  use: {
    baseURL: 'http://127.0.0.1:8765',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    launchOptions: { args: ['--enable-unsafe-swiftshader'] },
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'], viewport: { width: 1440, height: 1050 } } }],
  webServer: {
    command: '../.venv/bin/python -m uvicorn backend.api:app --app-dir .. --host 127.0.0.1 --port 8765',
    url: 'http://127.0.0.1:8765/api/health',
    reuseExistingServer: !process.env.CI,
    timeout: 90000,
    env: { AAMS_DATA_DIR: process.env.AAMS_E2E_DATA_DIR ?? '../data/experiments-e2e' },
  },
})
