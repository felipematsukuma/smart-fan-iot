import { readFileSync } from 'node:fs';
import { expect, test } from './fixtures';

test('cadastro administrativo preserva IDs e permite histórico desativado', async ({
  page,
}) => {
  test.setTimeout(60000);
  let failures = 0;
  page.on('pageerror', () => failures++);
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
  await page.getByRole('link', { name: 'Dispositivos', exact: true }).click();
  await expect(
    page.getByRole('button', { name: 'Novo dispositivo' }),
  ).toBeVisible();
  await expect(
    page
      .locator('[data-device-id="ac_01"]')
      .getByRole('button', { name: /^Detalhes/ }),
  ).toBeVisible();
  const identity = 'ac_e2e_registry';
  const row = page.locator(`[data-device-id="${identity}"]`);
  const details = row.getByRole('button', { name: /^Detalhes/ });
  if ((await details.count()) === 0) {
    await page.getByRole('button', { name: 'Novo dispositivo' }).click();
    await page.getByLabel('ID do dispositivo', { exact: true }).fill(identity);
    await page
      .getByLabel('Nome', { exact: true })
      .fill('Split de teste do cadastro');
    await page.getByLabel('Zona', { exact: true }).fill('sala_teste');
    await page.getByRole('button', { name: 'Salvar cadastro' }).click();
    await expect(details).toBeVisible();
  }
  await page.getByRole('button', { name: 'Novo dispositivo' }).click();
  await page.getByLabel('ID do dispositivo', { exact: true }).fill(identity);
  await page.getByLabel('Nome', { exact: true }).fill('Duplicado');
  await page.getByLabel('Zona', { exact: true }).fill('sala_teste');
  await page.getByRole('button', { name: 'Salvar cadastro' }).click();
  await expect(page.getByRole('alert')).toContainText('já cadastrado');
  await page.getByRole('button', { name: 'Cancelar', exact: true }).click();
  await row.getByRole('button', { name: /^Editar/ }).click();
  await expect(
    page.getByLabel('ID do dispositivo', { exact: true }),
  ).toBeDisabled();
  await page
    .getByLabel('Nome', { exact: true })
    .fill('Split de teste revisado');
  await page
    .getByText('Perfil e faixas de referência', { exact: true })
    .click();
  await page
    .getByLabel('Vida útil de referência (horas)', { exact: true })
    .fill('35000');
  await page.getByRole('button', { name: 'Salvar cadastro' }).click();
  await expect(
    page.getByText('Cadastro salvo.', { exact: false }),
  ).toBeVisible();
  const deactivate = row.getByRole('button', { name: /^Desabilitar/ });
  if ((await deactivate.count()) === 0) {
    await row.getByRole('button', { name: /^Habilitar/ }).click();
    await expect(deactivate).toBeVisible();
  }
  await deactivate.click();
  await expect(row.getByRole('button', { name: /^Habilitar/ })).toBeVisible();
  await details.click();
  await page.getByText('Detalhes do cadastro', { exact: true }).click();
  await expect(
    page.getByText(`${identity}_current`, { exact: false }),
  ).toBeVisible();
  await expect(
    page.getByText('Nenhuma leitura no período selecionado.', { exact: true }),
  ).toBeVisible({ timeout: 25000 });
  expect(failures).toBe(0);
  await page.getByRole('button', { name: 'Sair', exact: true }).click();
});
