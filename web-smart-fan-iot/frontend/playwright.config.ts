import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: 'line',
  // Only the explicit runtime/coverage campaign prepares real artifacts. The
  // existing lab and training tests each run once, before read-only UI checks.
  projects:
    process.env.AIOT_COVERAGE === '1'
      ? [
          { name: 'laboratory', testMatch: /lab\.spec\.ts$/ },
          {
            name: 'training',
            testMatch: /training\.spec\.ts$/,
            dependencies: ['laboratory'],
          },
          {
            name: 'browser',
            testIgnore: [/lab\.spec\.ts$/, /training\.spec\.ts$/],
            dependencies: ['training'],
          },
        ]
      : undefined,
  use: {
    baseURL: 'http://127.0.0.1:8080',
    viewport: { width: 1440, height: 1000 },
    trace: 'off',
    video: 'off',
    screenshot: 'off',
  },
});
