import { readFileSync } from 'node:fs';
import { expect, test } from '@playwright/test';

test('UI treina dois alvos na massa final e distingue aprovação de ativação', async ({
  page,
}) => {
  test.setTimeout(180000);
  page.setDefaultTimeout(15000);
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
  await page.getByRole('link', { name: 'Treinamento', exact: true }).click();
  const train = page.getByRole('button', {
    name: 'Treinar modelos',
    exact: true,
  });
  await expect(train).toBeEnabled({ timeout: 15000 });
  await train.click();
  const model = page.locator('.model-detail');
  try {
    await expect(model).toHaveAttribute('data-model-status', 'completed', {
      timeout: 120000,
    });
    await expect(
      model.getByText('1.036.800 vetores de origem', { exact: false }),
    ).toBeVisible();
    await expect(
      page.getByRole('heading', { name: 'Previsto × real', exact: true }),
    ).toBeVisible();
    await expect(
      page.getByRole('img', {
        name: 'Importância por permutação dos 18 atributos observados',
        exact: true,
      }),
    ).toBeVisible();
    await page
      .getByLabel('Alvo dos gráficos', { exact: true })
      .selectOption('rul_calendar_hours');
    await expect(
      page.getByRole('img', {
        name: 'Previsto versus real, h de calendário; até 200 pontos do teste reservado',
        exact: true,
      }),
    ).toBeVisible();
    const promote = page.getByRole('button', {
      name: 'Promover candidato',
      exact: true,
    });
    if (await promote.isEnabled()) {
      await promote.click();
      await expect(
        page.getByRole('status').filter({ hasText: 'Aprovação registrada.' }),
      ).toBeVisible();
      const version = await model.getAttribute('data-model-version');
      await expect(page.locator('.selection')).toContainText(version!);
    } else {
      await expect(
        model.getByText('Bloqueios:', { exact: false }),
      ).toBeVisible();
    }
    expect(errors).toBe(0);
  } finally {
    const cancel = page.getByRole('button', {
      name: 'Cancelar treino',
      exact: true,
    });
    if (
      !page.isClosed() &&
      (await cancel.count().catch(() => 0)) &&
      (await cancel.isEnabled().catch(() => false))
    )
      await cancel.click({ timeout: 5000 }).catch(() => undefined);
  }
  await page.getByRole('button', { name: 'Sair', exact: true }).click();
});
