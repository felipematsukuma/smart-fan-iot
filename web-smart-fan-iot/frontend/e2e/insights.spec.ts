import { execFileSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { expect, test } from './fixtures';

test('insights usa frames reais, histórico separado e oculta números ao parar simulador', async ({
  page,
}) => {
  test.setTimeout(60000);
  let errors = 0;
  let frames = 0;
  page.on('pageerror', () => errors++);
  page.on('websocket', (socket) =>
    socket.on('framereceived', ({ payload }) => {
      const body: unknown = JSON.parse(payload.toString());
      if (
        body &&
        typeof body === 'object' &&
        'tipo' in body &&
        body.tipo === 'frame.ready'
      )
        frames++;
    }),
  );
  await page.goto('/entrar');
  await page.getByLabel('Usuário', { exact: true }).fill('visualizador');
  const password = readFileSync(
    new URL('../../../secrets/initial_viewer_password', import.meta.url),
    'utf8',
  ).trim();
  try {
    await page.getByLabel('Senha', { exact: true }).fill(password);
  } catch {
    throw new Error('Falha ao preencher credencial local.');
  }
  await page.getByRole('button', { name: 'Entrar', exact: true }).click();
  await page.getByRole('link', { name: 'Insights', exact: true }).click();
  await expect(
    page.getByRole('heading', { name: 'Insights', exact: true }),
  ).toBeVisible();
  await expect.poll(() => frames, { timeout: 15000 }).toBeGreaterThan(0);
  await expect(page.getByText('Última fonte:', { exact: false })).toBeVisible();
  await expect(
    page.getByRole('button', { name: 'Editar regra preditiva', exact: true }),
  ).toHaveCount(0);
  await page
    .getByRole('button', {
      name: 'Consultar histórico de insights',
      exact: true,
    })
    .click();
  await expect(page.locator('.history-table tbody tr').first()).toBeVisible();
  const count = await page.locator('.history-table tbody tr').count();
  await page.screenshot({
    path: 'test-results/insights-review.png',
    fullPage: true,
  });
  try {
    execFileSync('docker', ['compose', 'stop', 'simulator'], {
      cwd: new URL('../../..', import.meta.url),
      stdio: 'pipe',
    });
    await expect(page.getByTestId('insight-status')).toHaveText(
      'Sem dados recentes',
      { timeout: 12000 },
    );
    await expect(page.getByTestId('insight-health')).toHaveText('—');
    await expect(page.getByTestId('insight-rul')).toHaveText('—');
    await expect(page.locator('.history-table tbody tr')).toHaveCount(count);
  } finally {
    execFileSync('docker', ['compose', 'start', 'simulator'], {
      cwd: new URL('../../..', import.meta.url),
      stdio: 'pipe',
    });
  }
  expect(errors).toBe(0);
  await page.getByRole('button', { name: 'Sair', exact: true }).click();
});
