import { readFileSync } from 'node:fs';
import type { Page } from '@playwright/test';
import { expect, test } from './fixtures';

async function login(page: Page) {
  const me = page.waitForResponse((response) =>
    response.url().endsWith('/api/v1/auth/me'),
  );
  await page.goto('/entrar');
  await page.getByLabel('Usuário', { exact: true }).fill('admin');
  try {
    await page
      .getByLabel('Senha', { exact: true })
      .fill(
        readFileSync(
          new URL('../../../secrets/initial_admin_password', import.meta.url),
          'utf8',
        ).trim(),
      );
  } catch {
    throw new Error('Falha ao preencher credencial local.');
  }
  await page.getByRole('button', { name: 'Entrar', exact: true }).click();
  const actor = (await (await me).json()) as { id: string; username: string };
  await expect(
    page.getByRole('link', { name: 'Dispositivos', exact: true }),
  ).toBeVisible();
  await expect(page.getByLabel('Equipamento', { exact: true })).toHaveValue(
    'ac_01',
  );
  return actor;
}

test('indisponibilidade HTTP mantém sessão, informa erro em cada tela e permite recuperação', async ({
  page,
}) => {
  test.setTimeout(90000);
  let exceptions = 0;
  page.on('pageerror', () => exceptions++);
  await login(page);
  await page.route('**/api/v1/**', (route) =>
    route.abort('internetdisconnected'),
  );
  for (const name of [
    'Usuários',
    'Auditoria',
    'Mensageria',
    'Laboratório',
    'Treinamento',
    'Insights',
    'Dispositivos',
    'Cena 3D',
  ]) {
    await page.getByRole('link', { name, exact: true }).click();
    await expect(page.locator('h1')).toBeVisible();
    await expect(page.getByRole('alert').first()).toContainText(
      'Não foi possível conectar',
      { timeout: 10000 },
    );
    await expect(
      page.getByRole('button', { name: 'Sair', exact: true }),
    ).toBeVisible();
  }
  await page
    .getByRole('link', { name: 'Assistente local', exact: true })
    .click();
  await page
    .getByLabel('Pergunta sobre o equipamento', { exact: true })
    .fill('Os dados estão disponíveis?');
  await page
    .getByRole('button', { name: 'Perguntar ao assistente', exact: true })
    .click();
  await expect(page.getByRole('alert')).toContainText(
    'Não foi possível conectar',
  );
  await expect(page.locator('[data-turn-outcome="failed"]')).toBeVisible();
  await page.unroute('**/api/v1/**');
  await page.getByRole('link', { name: 'Usuários', exact: true }).click();
  await expect(
    page.getByRole('button', { name: 'Editar admin', exact: true }),
  ).toBeVisible();
  expect(exceptions).toBe(0);
  await page.getByRole('button', { name: 'Sair', exact: true }).click();
});

test('fixture de contas verifica formulário, edição e limpeza da sessão ao alterar o próprio acesso', async ({
  page,
}) => {
  const actor = await login(page);
  const accounts = [
    { ...actor, role: 'administrador', enabled: true },
    {
      id: '11111111-1111-4111-8111-111111111111',
      username: 'review_demo',
      role: 'visualizador',
      enabled: true,
    },
  ];
  let writes = 0;
  await page.route('**/api/v1/users**', async (route) => {
    const request = route.request();
    if (request.method() === 'GET')
      return route.fulfill({ json: { items: accounts, next_cursor: null } });
    writes++;
    const body = request.postDataJSON() as {
      username?: string;
      role: string;
      enabled?: boolean;
    };
    if (request.method() === 'POST') {
      const created = {
        id: crypto.randomUUID(),
        username: body.username!,
        role: body.role,
        enabled: true,
      };
      accounts.push(created);
      return route.fulfill({ status: 201, json: created });
    }
    const account = accounts.find((item) =>
      request.url().endsWith('/' + item.id),
    );
    if (account)
      Object.assign(account, { role: body.role, enabled: body.enabled });
    return route.fulfill({ status: 204 });
  });
  await page.getByRole('link', { name: 'Usuários', exact: true }).click();
  await page.getByLabel('Usuário', { exact: true }).fill('review_created');
  await page.getByLabel('Senha inicial', { exact: true }).fill('界'.repeat(30));
  await page.getByRole('button', { name: 'Salvar conta', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('senha é muito longa');
  expect(writes).toBe(0);
  await page
    .getByLabel('Senha inicial', { exact: true })
    .fill(crypto.randomUUID());
  await page.getByLabel('Papel', { exact: true }).selectOption('operador');
  await page.getByRole('button', { name: 'Salvar conta', exact: true }).click();
  await expect(
    page.getByRole('button', { name: 'Editar review_created', exact: true }),
  ).toBeVisible();
  await page
    .getByRole('button', { name: 'Editar review_demo', exact: true })
    .click();
  await expect(page.getByLabel('Usuário', { exact: true })).toHaveAttribute(
    'readonly',
  );
  await page.getByLabel('Papel', { exact: true }).selectOption('operador');
  await page.getByLabel('Conta ativa', { exact: true }).uncheck();
  await page.getByRole('button', { name: 'Salvar conta', exact: true }).click();
  await expect(
    page.getByRole('heading', { name: 'Nova conta', exact: true }),
  ).toBeVisible();
  await page
    .getByRole('button', { name: 'Editar review_demo', exact: true })
    .click();
  await page
    .getByRole('button', { name: 'Cancelar edição', exact: true })
    .click();
  await page.getByRole('button', { name: 'Editar admin', exact: true }).click();
  await page.getByLabel('Papel', { exact: true }).selectOption('operador');
  await page.getByRole('button', { name: 'Salvar conta', exact: true }).click();
  await expect(page).toHaveURL(/\/entrar/);
  await expect(
    page.getByRole('heading', { name: 'Bem-vindo de volta', exact: true }),
  ).toBeVisible();
});

test('fixture SSE apresenta Markdown seguro, mantém conversa limitada e informa cota recusada', async ({
  page,
}) => {
  await login(page);
  let calls = 0;
  await page.route('**/api/v1/assistant/chat', async (route) => {
    calls++;
    if (calls === 3)
      return route.fulfill({
        status: 429,
        contentType: 'application/problem+json',
        json: { title: 'Limite de perguntas atingido.' },
      });
    const body = route.request().postDataJSON() as { history: unknown[] };
    expect(body.history.length).toBe(calls - 1);
    const events = [
      [
        'meta',
        {
          state: 'warming',
          model: 'fixture-only',
          summary: { live: 'stale', rul_unit: 'calendar_hours' },
        },
      ],
      [
        'delta',
        {
          text: '**Resumo** <script>throw 1</script> [x](javascript:alert(1))',
        },
      ],
      ['done', { first_token_ms: 10 }],
    ];
    return route.fulfill({
      contentType: 'text/event-stream',
      body: events
        .map(
          ([kind, data]) => `event: ${kind}\ndata: ${JSON.stringify(data)}\n\n`,
        )
        .join(''),
    });
  });
  await page
    .getByRole('link', { name: 'Assistente local', exact: true })
    .click();
  for (let index = 0; index < 3; index++) {
    await page
      .getByLabel('Pergunta sobre o equipamento', { exact: true })
      .fill('Explique a ausência de dados.');
    await page
      .getByRole('button', { name: 'Perguntar ao assistente', exact: true })
      .click();
    if (index < 2)
      await expect(page.locator('[data-turn-outcome="completed"]')).toHaveCount(
        index + 1,
      );
  }
  await expect(page.getByRole('alert')).toContainText(
    'Limite de perguntas atingido',
  );
  await expect(page.locator('.markdown strong').first()).toHaveText('Resumo');
  await expect(page.locator('.markdown script, .markdown a')).toHaveCount(0);
  await page.getByRole('button', { name: 'Sair', exact: true }).click();
});
