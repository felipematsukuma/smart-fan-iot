import { readFileSync, mkdirSync } from 'node:fs';
import { resolve } from 'node:path';
import type { Page } from '@playwright/test';
import { test, expect } from './fixtures';
import { verifyContrast } from './ui-contrast';
test.use({ hasTouch: true });
const evidence = resolve('../../evidence/ui-users-local');
mkdirSync(evidence, { recursive: true });
async function login(page: Page) {
  await page.goto('/entrar');
  await page.getByLabel('Usuário', { exact: true }).fill('admin');
  await page
    .getByLabel('Senha', { exact: true })
    .fill(
      readFileSync(
        resolve('../../secrets/initial_admin_password'),
        'utf8',
      ).trim(),
    );
  await page.getByRole('button', { name: 'Entrar', exact: true }).click();
  await expect(
    page.getByRole('heading', { name: 'Visão geral', exact: true }),
  ).toBeVisible();
}
async function visit(page: Page, name: string) {
  if (page.viewportSize()!.width < 1024)
    await page.getByRole('button', { name: 'Abrir navegação' }).click();
  await page.getByRole('link', { name, exact: true }).click();
  await expect(page.getByRole('heading', { name, exact: true })).toBeVisible();
}
async function capture(page: Page, name: string) {
  await expect
    .poll(() =>
      page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
    )
    .toBe(true);
  await verifyContrast(page, resolve(evidence, name + '-contrast.json'));
  await page.evaluate(() => scrollTo(0, 0));
  await page.screenshot({
    path: resolve(evidence, name + '.png'),
    fullPage: true,
  });
}
test('consultas reais: Usuários e Interfaces locais desktop/celular sem alteração de contas', async ({
  page,
}) => {
  const errors: string[] = [];
  page.on('pageerror', (e) => errors.push(e.message));
  const external: string[] = [];
  page.on('request', (r) => {
    if ([15672, 8086].includes(Number(new URL(r.url()).port)))
      external.push(r.url());
  });
  await page.route('**/api/v1/users**', (r) => {
    expect(r.request().method()).toBe('GET');
    return r.continue();
  });
  await login(page);
  await visit(page, 'Usuários');
  await expect(page.locator('[data-account-id]').first()).toBeVisible();
  await capture(page, 'users-desktop');
  await page.setViewportSize({ width: 390, height: 844 });
  await capture(page, 'users-mobile');
  const edit = page.locator('[data-account-id]').first().getByRole('button');
  await edit.tap();
  await expect(page.getByLabel('Papel', { exact: true })).toBeFocused();
  await expect(
    page.getByLabel('Nova senha (opcional)', { exact: true }),
  ).toHaveValue('');
  await page.getByRole('button', { name: 'Cancelar edição' }).click();
  await visit(page, 'Interfaces locais');
  await expect(
    page.getByText('Disponibilidade não verificada por esta página.', {
      exact: false,
    }),
  ).toBeVisible();
  await expect(
    page.getByRole('link', { name: /Abrir RabbitMQ/ }),
  ).toHaveAttribute('href', 'http://127.0.0.1:15672');
  await expect(
    page.getByRole('link', { name: /Abrir InfluxDB/ }),
  ).toHaveAttribute('href', 'http://127.0.0.1:8086');
  await expect(
    page.getByRole('link', { name: /Abrir documentação/ }),
  ).toHaveAttribute('href', '/api/v1/docs');
  const details = page.getByText(
    'Configuração administrativa dos links locais',
    { exact: true },
  );
  await details.focus();
  await page.keyboard.press('Enter');
  await expect(page.locator('pre')).toContainText('compose.dev.yaml');
  await page.keyboard.press('Enter');
  await capture(page, 'interfaces-mobile');
  await page.setViewportSize({ width: 1440, height: 1000 });
  await capture(page, 'interfaces-desktop');
  const link = page.getByRole('link', { name: /Abrir RabbitMQ/ });
  await link.focus();
  await expect(link).toBeFocused();
  expect(external).toEqual([]);
  expect(errors).toEqual([]);
});
test('fixtures: criação e edição, validação inline, senha não repovoada e confirmação de desativação', async ({
  page,
}) => {
  let account = {
    id: 'fixture-account',
    username: 'conta_fixture',
    role: 'visualizador',
    enabled: true,
    password: 'NEVER_REPOPULATE_FROM_SERVER',
  };
  let created = false;
  let createFail = true;
  let patches = 0;
  let posts = 0;
  let body: Record<string, unknown> = {};
  await page.route('**/api/v1/users?*', (r) =>
    r.fulfill({ json: { items: created ? [account] : [], next_cursor: null } }),
  );
  await page.route('**/api/v1/users', (r) => {
    posts++;
    body = r.request().postDataJSON();
    if (createFail)
      return r.fulfill({
        status: 409,
        json: { title: 'Nome de usuário indisponível.' },
      });
    created = true;
    account = {
      ...account,
      username: String(body.username),
      role: String(body.role),
    };
    return r.fulfill({ status: 201, json: account });
  });
  await page.route('**/api/v1/users/fixture-account', (r) => {
    patches++;
    body = r.request().postDataJSON();
    account = { ...account, ...body };
    return r.fulfill({ status: 204 });
  });
  await login(page);
  await visit(page, 'Usuários');
  const username = page.getByLabel('Nome de usuário', { exact: true });
  const initial = page.getByLabel('Senha inicial', { exact: true });
  const save = page.getByRole('button', { name: 'Salvar conta', exact: true });
  await username.fill('bad space');
  await initial.fill('fixture-password-123');
  await save.click();
  await expect(page.locator('#username-error')).toBeVisible();
  expect(posts).toBe(0);
  await username.fill('conta_fixture');
  await initial.fill('é'.repeat(37));
  await save.click();
  await expect(page.locator('#password-error')).toContainText('72 bytes');
  expect(posts).toBe(0);
  await expect(initial).toHaveValue('');
  await initial.fill('fixture-password-123');
  await page.getByLabel('Papel', { exact: true }).selectOption('operador');
  await save.click();
  await expect(page.locator('#username-error')).toContainText('indisponível');
  await expect(username).toHaveValue('conta_fixture');
  await expect(page.getByLabel('Papel', { exact: true })).toHaveValue(
    'operador',
  );
  await expect(initial).toHaveValue('');
  createFail = false;
  await initial.fill('fixture-password-123');
  await save.click();
  await expect(page.getByRole('status')).toContainText('Conta salva');
  await page
    .getByRole('button', { name: 'Editar conta_fixture', exact: true })
    .click();
  await expect(
    page.getByLabel('Nova senha (opcional)', { exact: true }),
  ).toHaveValue('');
  await expect(username).toHaveAttribute('readonly', '');
  await page.getByLabel('Papel', { exact: true }).selectOption('visualizador');
  await save.click();
  expect(body).toEqual({ role: 'visualizador', enabled: true });
  expect(body).not.toHaveProperty('password');
  await page.setViewportSize({ width: 390, height: 844 });
  await page
    .getByRole('button', { name: 'Editar conta_fixture', exact: true })
    .tap();
  await page.getByLabel('Conta habilitada', { exact: true }).uncheck();
  await save.click();
  await expect(page.getByRole('dialog')).toContainText('conta_fixture');
  expect(patches).toBe(1);
  await page.keyboard.press('Escape');
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await expect(save).toBeFocused();
  expect(patches).toBe(1);
  await save.click();
  await page
    .getByRole('button', { name: 'Confirmar desativação', exact: true })
    .tap();
  await expect(
    page.locator('[data-account-id="fixture-account"]'),
  ).toContainText('Desabilitada');
  expect(patches).toBe(2);
  expect(body).toEqual({ role: 'visualizador', enabled: false });
});
test('fixtures: último administrador recusado, erro preserva edição e própria conta encerra sessão', async ({
  page,
}) => {
  let identity = '';
  let reject = true;
  let writes = 0;
  await page.route('**/api/v1/auth/me', async (r) => {
    const response = await r.fetch();
    const user = await response.json();
    identity = user.id;
    await r.fulfill({ response, json: user });
  });
  await page.route('**/api/v1/users?*', (r) =>
    r.fulfill({
      json: {
        items: [
          {
            id: identity,
            username: 'admin',
            role: 'administrador',
            enabled: true,
          },
        ],
        next_cursor: null,
      },
    }),
  );
  await page.route('**/api/v1/users/*', (r) => {
    writes++;
    return r.fulfill(
      reject
        ? {
            status: 409,
            json: { title: 'Mantenha pelo menos um administrador ativo.' },
          }
        : { status: 204 },
    );
  });
  await login(page);
  await visit(page, 'Usuários');
  await page.getByRole('button', { name: 'Editar admin', exact: true }).click();
  await expect(
    page.getByText('Você está editando sua conta.', { exact: false }),
  ).toBeVisible();
  await page.getByLabel('Papel', { exact: true }).selectOption('operador');
  await page
    .getByLabel('Nova senha (opcional)', { exact: true })
    .fill('fixture-password-123');
  await page.getByRole('button', { name: 'Salvar conta', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText(
    'pelo menos um administrador',
  );
  await expect(page.getByLabel('Papel', { exact: true })).toHaveValue(
    'operador',
  );
  await expect(
    page.getByLabel('Nova senha (opcional)', { exact: true }),
  ).toHaveValue('');
  await expect(
    page.getByRole('heading', { name: 'Usuários', exact: true }),
  ).toBeVisible();
  await page.getByLabel('Papel', { exact: true }).selectOption('administrador');
  await page.getByLabel('Conta habilitada', { exact: true }).uncheck();
  await page.getByRole('button', { name: 'Salvar conta', exact: true }).click();
  await expect(page.getByRole('dialog')).toContainText('Esta é a sua conta.');
  await page
    .getByRole('button', { name: 'Confirmar desativação', exact: true })
    .click();
  await expect(page.getByRole('alert')).toContainText(
    'pelo menos um administrador',
  );
  await expect(
    page.getByLabel('Conta habilitada', { exact: true }),
  ).not.toBeChecked();
  await expect(
    page.getByRole('heading', { name: 'Usuários', exact: true }),
  ).toBeVisible();
  await page.getByLabel('Conta habilitada', { exact: true }).check();
  reject = false;
  await page.getByLabel('Papel', { exact: true }).selectOption('administrador');
  await page.getByRole('button', { name: 'Salvar conta', exact: true }).click();
  await expect(
    page.getByRole('heading', { name: 'Usuários', exact: true }),
  ).toHaveCount(0);
  await expect(page.getByLabel('Senha', { exact: true })).toBeVisible();
  await expect(
    page.getByText('Conta atualizada. Entre novamente.', { exact: true }),
  ).toBeVisible();
  expect(writes).toBe(3);
});
test('fixtures: consulta com erro mantém página e campos não sensíveis', async ({
  page,
}) => {
  let fail = false;
  const cursors: string[] = [];
  await page.route('**/api/v1/users?*', (r) => {
    const cursor = new URL(r.request().url()).searchParams.get('cursor');
    cursors.push(cursor ?? 'first');
    return r.fulfill(
      fail
        ? { status: 503, json: { title: 'Consulta indisponível (fixture)' } }
        : {
            json: {
              items: [
                {
                  id: cursor ? 'two' : 'one',
                  username: cursor ? 'conta_dois' : 'conta_um',
                  role: 'visualizador',
                  enabled: true,
                },
              ],
              next_cursor: cursor ? null : 'two',
            },
          },
    );
  });
  await login(page);
  await visit(page, 'Usuários');
  await page.getByRole('button', { name: 'Próxima', exact: true }).click();
  await expect(page.getByText('Página 2', { exact: true })).toBeVisible();
  await page
    .getByRole('button', { name: 'Editar conta_dois', exact: true })
    .click();
  await page.getByLabel('Papel', { exact: true }).selectOption('operador');
  fail = true;
  await page.getByRole('button', { name: 'Atualizar', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('fixture');
  await expect(page.getByText('Página 2', { exact: true })).toBeVisible();
  await expect(page.getByLabel('Papel', { exact: true })).toHaveValue(
    'operador',
  );
  await expect(page.getByLabel('Nome de usuário', { exact: true })).toHaveValue(
    'conta_dois',
  );
  await page.getByRole('button', { name: 'Anterior', exact: true }).click();
  await expect(page.getByText('Página 2', { exact: true })).toBeVisible();
  fail = false;
  await page.getByRole('button', { name: 'Anterior', exact: true }).click();
  await expect(page.getByText('Página 1', { exact: true })).toBeVisible();
  expect(cursors).toEqual(['first', 'two', 'two', 'first', 'first']);
});
