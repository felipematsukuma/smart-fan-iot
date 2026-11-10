import { execFileSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { expect, test } from './fixtures';

const root = fileURLToPath(new URL('../../../', import.meta.url));
test('mensageria mostra fila real crescer e esvaziar sem consumir a DLQ', async ({
  page,
}) => {
  test.setTimeout(90000);
  let errors = 0;
  page.on('pageerror', () => errors++);
  await page.goto('/entrar');
  await page.getByLabel('Usuário', { exact: true }).fill('admin');
  const password = readFileSync(
    new URL('../../../secrets/initial_admin_password', import.meta.url),
    'utf8',
  ).trim();
  try {
    await page.getByLabel('Senha', { exact: true }).fill(password);
  } catch {
    throw new Error('Falha ao preencher credencial local.');
  }
  await page.getByRole('button', { name: 'Entrar', exact: true }).click();
  await page.getByRole('link', { name: 'Mensageria', exact: true }).click();
  const queue = page.locator('[data-queue="q.telemetry.writer"]');
  await expect(queue).toHaveAttribute('data-consumers', '1', {
    timeout: 15000,
  });
  const dlq = page.locator('[data-queue="q.dlq"]');
  const previous = Number(await dlq.getAttribute('data-ready'));
  try {
    execFileSync('docker', ['compose', 'stop', 'writer'], {
      cwd: root,
      stdio: 'pipe',
    });
    await expect(queue).toHaveAttribute('data-consumers', '0', {
      timeout: 20000,
    });
    await expect
      .poll(async () => Number(await queue.getAttribute('data-ready')), {
        timeout: 20000,
      })
      .toBeGreaterThan(0);
  } finally {
    execFileSync('docker', ['compose', 'start', 'writer'], {
      cwd: root,
      stdio: 'pipe',
    });
  }
  await expect(queue).toHaveAttribute('data-consumers', '1', {
    timeout: 20000,
  });
  await expect(queue).toHaveAttribute('data-ready', '0', { timeout: 20000 });
  await page
    .getByRole('button', { name: 'Atualizar mensageria', exact: true })
    .click();
  await expect
    .poll(async () => Number(await dlq.getAttribute('data-ready')))
    .toBeGreaterThanOrEqual(previous);
  expect(errors).toBe(0);
  await page.getByRole('button', { name: 'Sair', exact: true }).click();
});
