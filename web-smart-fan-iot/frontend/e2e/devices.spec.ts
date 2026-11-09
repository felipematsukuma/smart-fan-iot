import { readFileSync } from 'node:fs';
import { expect, test } from '@playwright/test';

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
    page.getByRole('button', { name: 'Detalhes de ac_01', exact: true }),
  ).toBeVisible();
  const identity = 'ac_e2e_registry';
  const details = page.getByRole('button', {
    name: `Detalhes de ${identity}`,
    exact: true,
  });
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
  await page
    .getByRole('button', { name: `Editar ${identity}`, exact: true })
    .click();
  await expect(
    page.getByLabel('ID do dispositivo', { exact: true }),
  ).toBeDisabled();
  await page
    .getByLabel('Nome', { exact: true })
    .fill('Split de teste revisado');
  await page
    .getByLabel('Vida útil de referência (horas)', { exact: true })
    .fill('35000');
  await page.getByRole('button', { name: 'Salvar cadastro' }).click();
  await expect(
    page.getByText('Cadastro salvo.', { exact: false }),
  ).toBeVisible();
  const deactivate = page.getByRole('button', {
    name: `Desativar ${identity}`,
    exact: true,
  });
  if ((await deactivate.count()) === 0) {
    await page
      .getByRole('button', { name: `Ativar ${identity}`, exact: true })
      .click();
    await expect(deactivate).toBeVisible();
  }
  await deactivate.click();
  await expect(
    page.getByRole('button', { name: `Ativar ${identity}`, exact: true }),
  ).toBeVisible();
  await details.click();
  await expect(
    page.getByText(`${identity}_current`, { exact: false }),
  ).toBeVisible();
  await expect(
    page.getByText('Nenhuma leitura no período selecionado.', { exact: true }),
  ).toBeVisible({ timeout: 25000 });
  expect(failures).toBe(0);
  await page.getByRole('button', { name: 'Sair', exact: true }).click();
});
