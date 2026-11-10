import { mkdirSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { test as base, expect } from '@playwright/test';

export { expect };
export const test = base.extend({
  page: async ({ page }, use, info) => {
    const coverage = process.env.AIOT_COVERAGE === '1';
    if (coverage)
      await page.coverage.startJSCoverage({ resetOnNavigation: false });
    try {
      await use(page);
    } finally {
      if (coverage && !page.isClosed()) {
        const entries = await page.coverage.stopJSCoverage();
        const directory = resolve('../../evidence/coverage/browser');
        mkdirSync(directory, { recursive: true });
        writeFileSync(
          resolve(
            directory,
            `${info.testId.replace(/[^a-zA-Z0-9_-]/g, '_')}-${info.retry}.json`,
          ),
          JSON.stringify(entries),
        );
      }
    }
  },
});
