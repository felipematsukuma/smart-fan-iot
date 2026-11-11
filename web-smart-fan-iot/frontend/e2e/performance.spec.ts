import { readFileSync, writeFileSync } from 'node:fs';
import { expect, test } from './fixtures';

type RenderSample = { sourceMs: number; gatewayMs: number };
declare global {
  interface Window {
    __aiotRenderSamples: RenderSample[];
    __aiotRenderSkipped: number;
  }
}

const baseURL = process.env.AIOT_PERF_URL;
test.use({ baseURL: baseURL ?? 'http://127.0.0.1:8080' });
test('opt-in: amostra MQTT alcança DOM e dois quadros reais do navegador', async ({
  page,
}) => {
  test.skip(
    !baseURL || !process.env.AIOT_PERF_PASSWORD_FILE,
    'Executado pelo ensaio físico M18, com cópia isolada e carga real.',
  );
  test.setTimeout(120000);
  await page.goto('/entrar');
  await page.getByLabel('Usuário', { exact: true }).fill('operador');
  const password = readFileSync(
    process.env.AIOT_PERF_PASSWORD_FILE!,
    'utf8',
  ).trim();
  try {
    await page.getByLabel('Senha', { exact: true }).fill(password);
  } catch {
    throw new Error('Falha ao preencher credencial privada do ensaio.');
  }
  await page.getByRole('button', { name: 'Entrar', exact: true }).click();
  const selector = page.getByLabel('Equipamento', { exact: true });
  await expect(selector).toBeVisible();
  if (process.env.AIOT_PERF_DEVICE)
    await selector.selectOption(process.env.AIOT_PERF_DEVICE);
  await expect(page.getByTestId('live-metrics')).toHaveAttribute(
    'data-source-id',
    /.+/,
    { timeout: 30000 },
  );
  await page.bringToFront();
  await page.evaluate(() => {
    window.__aiotRenderSamples = [];
    window.__aiotRenderSkipped = 0;
    const target = document.querySelector('[data-testid="live-metrics"]')!;
    const seen = new Set<string>();
    new MutationObserver(() => {
      const id = target.getAttribute('data-source-id');
      const sampled = Date.parse(target.getAttribute('data-sampled-at') ?? '');
      const observed = Date.parse(
        target.getAttribute('data-observed-at') ?? '',
      );
      if (
        !id ||
        seen.has(id) ||
        !Number.isFinite(sampled) ||
        !Number.isFinite(observed)
      )
        return;
      seen.add(id);
      requestAnimationFrame(() =>
        requestAnimationFrame(() => {
          if (target.getAttribute('data-source-id') !== id) {
            window.__aiotRenderSkipped++;
            return;
          }
          window.__aiotRenderSamples.push({
            sourceMs: Date.now() - sampled,
            gatewayMs: Date.now() - observed,
          });
        }),
      );
    }).observe(target, {
      attributes: true,
      attributeFilter: ['data-source-id'],
    });
  });
  await page.waitForTimeout(
    Number(process.env.AIOT_PERF_SECONDS ?? '60') * 1000,
  );
  const observation = await page.evaluate(() => ({
    samples: window.__aiotRenderSamples,
    skipped: window.__aiotRenderSkipped,
  }));
  const percentile = (values: number[]) =>
    values.sort((a, b) => a - b)[Math.ceil(values.length * 0.95) - 1];
  const report = {
    method:
      'Actual Vue DOM mutation plus two requestAnimationFrame callbacks; initial snapshot excluded.',
    samples: observation.samples.length,
    skipped: observation.skipped,
    sourceP95Ms: percentile(observation.samples.map((row) => row.sourceMs)),
    gatewayP95Ms: percentile(observation.samples.map((row) => row.gatewayMs)),
  };
  if (process.env.AIOT_PERF_REPORT)
    writeFileSync(
      process.env.AIOT_PERF_REPORT,
      JSON.stringify(report, null, 2) + '\n',
    );
  expect(report.samples).toBeGreaterThanOrEqual(100);
  expect(report.sourceP95Ms).toBeLessThanOrEqual(1500);
  expect(report.gatewayP95Ms).toBeLessThanOrEqual(1000);
  expect(report.skipped).toBeLessThanOrEqual(report.samples * 0.05);
  await page.getByRole('button', { name: 'Sair', exact: true }).click();
});
