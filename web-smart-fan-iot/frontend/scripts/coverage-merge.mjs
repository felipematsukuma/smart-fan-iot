import { readFileSync, readdirSync, writeFileSync, mkdirSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import convert from 'ast-v8-to-istanbul';
import { createCoverageMap } from '@vitest/istanbul-lib-coverage';
import { parseAstAsync } from 'vitest/node';

const frontend = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const directory = resolve(frontend, '../../evidence/coverage/browser');
const output = resolve(frontend, '../../evidence/coverage/frontend.json');
const unit = JSON.parse(
  readFileSync(resolve(frontend, 'coverage/coverage-final.json'), 'utf8'),
);
const wanted = (path) => {
  const normalized = path.replaceAll('\\', '/');
  return (
    normalized.startsWith(frontend.replaceAll('\\', '/') + '/src/') &&
    (normalized.includes('/src/aiot/') || normalized.includes('/src/lib/')) &&
    !normalized.endsWith('.test.ts') &&
    !normalized.includes('.generated.')
  );
};
const result = createCoverageMap({});
const browser = createCoverageMap({});
// Unit tests execute TS business rules; browser tests execute the production UI.
// SSR and production transforms have different maps: merging their zero baselines
// doubles functions/branches. Keep one authoritative program per source file.
const unitCore = (path) => {
  const name = path
    .replaceAll('\\', '/')
    .slice(frontend.replaceAll('\\', '/').length + 1);
  return (
    name.startsWith('src/lib/') ||
    [
      'auth.ts',
      'access.ts',
      'live-store.ts',
      'insights.ts',
      'assistant-stream.ts',
      'assistant-markdown.ts',
      'scene/model.ts',
    ].some((file) => name === 'src/aiot/' + file)
  );
};
for (const [path, value] of Object.entries(unit))
  if (wanted(path)) result.addFileCoverage(value);
let traces = 0;
const maps = new Map();
for (const filename of readdirSync(directory).filter((name) =>
  name.endsWith('.json'),
)) {
  traces++;
  const entries = JSON.parse(
    readFileSync(resolve(directory, filename), 'utf8'),
  );
  for (const entry of entries) {
    const url = new URL(entry.url || 'http://invalid');
    if (
      !['http://127.0.0.1:8080', 'http://localhost:8080'].includes(
        url.origin,
      ) ||
      !url.pathname.startsWith('/assets/') ||
      !url.pathname.endsWith('.js') ||
      !entry.source
    )
      continue;
    const name = entry.source.match(/sourceMappingURL=([^\s]+)/)?.[1];
    if (!name && url.pathname.includes('/_plugin-vue_export-helper-')) continue;
    if (!name)
      throw new Error(
        'Browser coverage needs the explicit sourcemap test build.',
      );
    const mapUrl = new URL(name, url);
    if (mapUrl.origin !== url.origin || !mapUrl.pathname.startsWith('/assets/'))
      throw new Error('Unexpected source map origin.');
    if (!maps.has(mapUrl.href)) {
      const response = await fetch(mapUrl);
      if (!response.ok) throw new Error('Source map unavailable.');
      maps.set(mapUrl.href, await response.json());
    }
    const converted = await convert({
      code: entry.source,
      ast: parseAstAsync(entry.source),
      sourceMap: maps.get(mapUrl.href),
      coverage: {
        functions: entry.functions,
        url: pathToFileURL(resolve(frontend, 'dist', url.pathname.slice(1)))
          .href,
      },
      wrapperLength: 0,
    });
    for (const [path, value] of Object.entries(converted)) {
      const canonical = path.startsWith('file:')
        ? fileURLToPath(path)
        : resolve(path);
      if (wanted(canonical))
        browser.merge({ [canonical]: { ...value, path: canonical } });
    }
  }
}
if (traces < 10)
  throw new Error(
    'Missing browser traces; full critical E2E suite is required.',
  );
for (const path of browser.files()) {
  if (!unitCore(path)) {
    // Replace the unexecuted SSR baseline, retaining all production branches.
    result.data[path] = browser.fileCoverageFor(path);
  }
}
mkdirSync(dirname(output), { recursive: true });
writeFileSync(output, JSON.stringify(result.toJSON()));
const summary = result.getCoverageSummary().toJSON();
console.log(
  JSON.stringify({ traces, files: result.files().length, summary }, null, 2),
);
if (summary.lines.pct < 70) process.exitCode = 1;
