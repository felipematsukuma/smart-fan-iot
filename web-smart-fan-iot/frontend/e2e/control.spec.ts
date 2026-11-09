import { readFileSync } from 'node:fs';
import { expect, test } from '@playwright/test';

test('Web altera atuador por ACK físico e libera novamente o automático', async ({
  page,
}) => {
  test.setTimeout(60000);
  let errors = 0;
  page.on('pageerror', () => errors++);
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
  await page.getByRole('link', { name: 'Dispositivos', exact: true }).click();
  await page
    .getByRole('button', { name: 'Detalhes de ac_01', exact: true })
    .click();
  const off = page.getByRole('button', {
    name: 'Desligar ventilador do condensador',
    exact: true,
  });
  const release = page.getByRole('button', {
    name: 'Liberar controle automático',
    exact: true,
  });
  await expect(off).toBeEnabled({ timeout: 15000 });
  try {
    await off.click();
    await expect(page.locator('[data-command-status="confirmed"]')).toBeVisible(
      { timeout: 15000 },
    );
    await expect(page.getByTestId('physical-state')).toContainText(
      'compressor desligado · ventilador do condensador desligado',
      { timeout: 10000 },
    );
    const on = page.getByRole('button', {
      name: 'Ligar ventilador do condensador',
      exact: true,
    });
    await expect(on).toBeEnabled();
    await on.click();
    await expect(page.locator('[data-command-status="confirmed"]')).toBeVisible(
      { timeout: 15000 },
    );
    await expect(page.getByTestId('physical-state')).toContainText(
      'ventilador do condensador ligado',
      { timeout: 10000 },
    );
    expect(errors).toBe(0);
  } finally {
    await expect(release).toBeEnabled({ timeout: 15000 });
    await release.click();
    await expect(page.locator('[data-command-status="confirmed"]')).toBeVisible(
      { timeout: 15000 },
    );
  }
  await page.getByRole('button', { name: 'Sair', exact: true }).click();
});
