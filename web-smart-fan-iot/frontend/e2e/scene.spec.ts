import { execFileSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { expect, test } from './fixtures';

test('cena usa IDs reais, seleciona por teclado e congela sem amostra recente', async ({
  page,
}) => {
  test.setTimeout(75000);
  let errors = 0;
  page.on('pageerror', () => errors++);
  page.on('console', (message) => {
    if (message.type() === 'error') errors++;
  });
  await page.goto('/entrar');
  await page.getByLabel('Usuário', { exact: true }).fill('operador');
  const password = readFileSync(
    new URL('../../../secrets/initial_operator_password', import.meta.url),
    'utf8',
  ).trim();
  try {
    await page.getByLabel('Senha', { exact: true }).fill(password);
  } catch {
    throw new Error('Falha ao preencher credencial local.');
  }
  await page.getByRole('button', { name: 'Entrar', exact: true }).click();
  await page.getByRole('link', { name: 'Cena 3D', exact: true }).click();
  await expect(page.getByTestId('scene-status')).toHaveText('Dados recentes', {
    timeout: 15000,
  });
  const scene = page.locator('.scene-card');
  await expect
    .poll(async () => Number(await scene.getAttribute('data-geometries')))
    .toBeGreaterThan(0);
  await expect(page.locator('.component-list button')).toHaveCount(8);
  const vibration = page.getByRole('button', {
    name: 'Selecionar Vibração',
    exact: true,
  });
  await vibration.focus();
  await page.keyboard.press('Enter');
  await expect(vibration).toHaveAttribute('aria-pressed', 'true');
  await expect(
    page.getByRole('heading', { name: 'Vibração', exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole('img', {
      name: 'Histórico WS de Vibração (mm/s)',
      exact: true,
    }),
  ).toBeVisible();
  await page.getByText('Controles do equipamento', { exact: true }).click();
  const fan = page.getByRole('button', {
    name: 'Ligar ventilador do condensador',
    exact: true,
  });
  const release = page.getByRole('button', {
    name: 'Liberar controle automático',
    exact: true,
  });
  try {
    await expect(fan).toBeEnabled({ timeout: 10000 });
    await fan.click();
    await expect(page.locator('[data-command-status="confirmed"]')).toBeVisible(
      { timeout: 10000 },
    );
    const angle = await scene.getAttribute('data-fan-angle');
    await expect
      .poll(() => scene.getAttribute('data-fan-angle'))
      .not.toBe(angle);
    const geometries = await scene.getAttribute('data-geometries');
    const metrics = {
      calls: Number(await scene.getAttribute('data-draw-calls')),
      triangles: Number(await scene.getAttribute('data-triangles')),
      geometries: Number(geometries),
      text: await page.locator('.scene-performance').textContent(),
    };
    expect(metrics.calls).toBeLessThanOrEqual(100);
    expect(metrics.triangles).toBeLessThanOrEqual(50000);
    console.log('Scene metrics: ' + JSON.stringify(metrics));
    await page.screenshot({
      path: 'test-results/scene-review.png',
      fullPage: true,
    });
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await page.waitForTimeout(1200);
    const reduced = await scene.getAttribute('data-fan-angle');
    await page.waitForTimeout(1200);
    await expect(scene).toHaveAttribute('data-fan-angle', reduced!);
    await page.emulateMedia({ reducedMotion: 'no-preference' });
    execFileSync('docker', ['compose', 'stop', 'simulator'], {
      cwd: new URL('../../..', import.meta.url),
      stdio: 'pipe',
    });
    await expect(page.getByTestId('scene-status')).toHaveText(
      'Sem dados — cena congelada',
      { timeout: 12000 },
    );
    await page.waitForTimeout(1200);
    const frozen = await scene.getAttribute('data-fan-angle');
    await page.waitForTimeout(1500);
    await expect(scene).toHaveAttribute('data-fan-angle', frozen!);
    await expect(scene).toHaveAttribute('data-geometries', geometries!);
    await page.setViewportSize({ width: 390, height: 844 });
    await expect
      .poll(() =>
        page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
      )
      .toBe(true);
  } finally {
    execFileSync('docker', ['compose', 'start', 'simulator'], {
      cwd: new URL('../../..', import.meta.url),
      stdio: 'pipe',
    });
    await expect(release).toBeEnabled({ timeout: 12000 });
    await release.click();
    await expect(page.locator('[data-command-status="confirmed"]')).toBeVisible(
      { timeout: 10000 },
    );
  }
  expect(errors).toBe(0);
  await page.getByRole('link', { name: 'Insights', exact: true }).click();
  await expect(page.locator('canvas[aria-label^="Cena 3D"]')).toHaveCount(0);
  await page.getByRole('button', { name: 'Sair', exact: true }).click();
});
