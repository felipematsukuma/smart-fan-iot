import { readFileSync } from 'node:fs';
import type { Page } from '@playwright/test';
import { expect, test } from './fixtures';

let browserErrors = 0;
test.beforeEach(async ({ page }) => {
  browserErrors = 0;
  page.on('console', (message) => {
    if (message.type() === 'error') browserErrors++;
  });
  page.on('pageerror', () => browserErrors++);
});
test.afterEach(() => {
  expect(browserErrors, 'Erros de JavaScript ou CSP no navegador').toBe(0);
});

async function login(
  page: Page,
  username: string,
  credential: string,
  keyboard = false,
) {
  const password = readFileSync(
    new URL(`../../../secrets/${credential}`, import.meta.url),
    'utf8',
  ).trim();
  const input = page.getByLabel('Senha', { exact: true });
  await expect(input).toBeVisible();
  await page.getByLabel('Usuário', { exact: true }).fill(username);
  try {
    await input.fill(password);
  } catch {
    throw new Error('Não foi possível preencher a credencial local.');
  }
  if (keyboard) await input.press('Enter');
  else await page.getByRole('button', { name: 'Entrar', exact: true }).click();
}

test('visualizador entra, tem rota administrativa negada e sai', async ({
  page,
}) => {
  await page.goto('/usuarios');
  await login(page, 'visualizador', 'initial_viewer_password');
  await expect(
    page.getByRole('heading', { name: 'Acesso restrito' }),
  ).toBeVisible();
  await page.getByRole('link', { name: 'Voltar à visão geral' }).click();
  await expect(
    page.getByRole('heading', { name: 'Visão geral' }),
  ).toBeVisible();
  await expect(
    page.getByRole('navigation').getByRole('link', { name: 'Usuários' }),
  ).toHaveCount(0);
  const persisted = await page.evaluate(() => [
    ...Object.keys(localStorage),
    ...Object.keys(sessionStorage),
  ]);
  expect(
    persisted.filter((key) => /token|session|jwt|auth/i.test(key)),
  ).toEqual([]);
  await page.getByRole('button', { name: 'Sair', exact: true }).click();
  await expect(
    page.getByRole('heading', { name: 'Entrar', exact: true }),
  ).toBeVisible();
});

test('administrador consulta usuários e auditoria e recarregar exige novo login', async ({
  page,
}) => {
  await page.goto('/entrar');
  await login(page, 'admin', 'initial_admin_password');
  await expect(
    page.getByRole('heading', { name: 'Visão geral' }),
  ).toBeVisible();
  await page.getByRole('link', { name: 'Usuários', exact: true }).click();
  const adminRow = page.locator('[data-account-id]').filter({
    has: page.getByText('admin', { exact: true }),
  });
  await expect(page.locator('[data-account-id]').first()).toBeVisible();
  const next = page.getByRole('button', { name: 'Próxima', exact: true });
  while (!(await adminRow.count()) && (await next.isEnabled())) {
    const first = await page
      .locator('[data-account-id]')
      .first()
      .getAttribute('data-account-id');
    await next.click();
    await expect
      .poll(() =>
        page
          .locator('[data-account-id]')
          .first()
          .getAttribute('data-account-id'),
      )
      .not.toBe(first);
  }
  await expect(adminRow).toBeVisible();
  await page.getByRole('link', { name: 'Auditoria', exact: true }).click();
  await expect(
    page.getByRole('heading', { name: 'Auditoria', exact: true }),
  ).toBeVisible();
  await expect(page.locator('tbody tr').first()).toBeVisible();
  await page.reload();
  await expect(
    page.getByRole('heading', { name: 'Entrar', exact: true }),
  ).toBeVisible();
});

test('login funciona em tela pequena e respeita teclado', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/entrar');
  await expect(page.getByLabel('Usuário', { exact: true })).toBeFocused();
  await login(page, 'operador', 'initial_operator_password', true);
  await expect(
    page.getByRole('heading', { name: 'Visão geral' }),
  ).toBeVisible();
  await page.keyboard.press('Tab');
  await expect(
    page.getByRole('link', { name: 'Ir para conteúdo' }),
  ).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(page.locator('#main-content')).toBeFocused();
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth > innerWidth,
  );
  expect(overflow).toBe(false);
  await page
    .getByRole('button', { name: 'Abrir navegação', exact: true })
    .click();
  await page.getByRole('button', { name: 'Sair', exact: true }).click();
});
