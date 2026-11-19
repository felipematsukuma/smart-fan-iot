import { readFileSync, mkdirSync } from 'node:fs';
import { resolve } from 'node:path';
import type { Page } from '@playwright/test';
import { test, expect } from './fixtures';
import { verifyContrast } from './ui-contrast';
test.use({ hasTouch: true });
const evidence = resolve('../../evidence/ui-messaging-audit');
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
test('consultas reais: Mensageria e Auditoria desktop/celular, sem replay', async ({
  page,
}) => {
  const errors: string[] = [];
  const reads: string[] = [];
  page.on('pageerror', (e) => errors.push(e.message));
  await page.route('**/api/v1/messaging**', async (r) => {
    expect(r.request().method()).toBe('GET');
    reads.push(new URL(r.request().url()).pathname);
    await r.continue();
  });
  await login(page);
  await visit(page, 'Mensageria');
  await expect(page.locator('[data-queue="q.telemetry.writer"]')).toBeVisible();
  const details = page.locator('[data-queue="q.telemetry.writer"] summary');
  await details.focus();
  await page.keyboard.press('Enter');
  await expect(
    page.getByText('q.telemetry.writer', { exact: true }),
  ).toBeVisible();
  await page.keyboard.press('Enter');
  await capture(page, 'messaging-desktop');
  await page.setViewportSize({ width: 390, height: 844 });
  const queue = page.locator('[data-queue="q.telemetry.writer"]');
  const positions = await queue.evaluate((el) => {
    const box = (selector: string) =>
      el.querySelector(selector)!.getBoundingClientRect();
    const first = box('[data-label="Pendentes (mensagens)"]'),
      second = box('[data-label="Em processamento"]'),
      last = box('.queue-details');
    return {
      sameRow: Math.abs(first.top - second.top) < 2,
      twoColumns: second.left > first.left,
      detailsLast: last.top > box('[data-label="Entrega (msg/s)"]').bottom,
      height: el.getBoundingClientRect().height,
      summary: el.querySelector('summary')!.getBoundingClientRect().height,
    };
  });
  expect(positions.sameRow).toBe(true);
  expect(positions.twoColumns).toBe(true);
  expect(positions.detailsLast).toBe(true);
  expect(positions.height).toBeLessThan(330);
  expect(positions.summary).toBeGreaterThanOrEqual(44);
  await capture(page, 'messaging-mobile');
  expect(
    await page
      .locator('.ops-table')
      .first()
      .evaluate((el) => el.scrollWidth <= el.clientWidth),
  ).toBe(true);
  await details.tap();
  await expect(
    page.getByText('q.telemetry.writer', { exact: true }),
  ).toBeVisible();
  await details.tap();
  await visit(page, 'Auditoria');
  await expect(page.locator('[data-audit-id]').first()).toBeVisible();
  await expect(page.locator('[data-audit-id]')).toHaveCount(20);
  const row = page.locator('[data-audit-id]').first();
  const order = await row.evaluate((el) => {
    const top = (name: string) =>
      el.querySelector(`[data-label="${name}"]`)!.getBoundingClientRect().top;
    return {
      action: top('Ação'),
      result: top('Resultado'),
      user: top('Usuário'),
      time: top('Data / hora'),
      height: el.getBoundingClientRect().height,
    };
  });
  expect(Math.abs(order.action - order.result)).toBeLessThan(2);
  expect(order.user).toBeGreaterThan(order.action);
  expect(order.time).toBeGreaterThan(order.user);
  expect(order.height).toBeLessThan(250);
  const auditDetails = row.getByText('Detalhes do registro', { exact: true });
  await auditDetails.focus();
  await page.keyboard.press('Enter');
  await expect(row.getByText('Ação original', { exact: true })).toBeVisible();
  await page.keyboard.press('Enter');
  await capture(page, 'audit-mobile');
  await page.setViewportSize({ width: 1440, height: 1000 });
  await capture(page, 'audit-desktop');
  expect(
    reads.every(
      (p) => p === '/api/v1/messaging' || p === '/api/v1/messaging/failures',
    ),
  ).toBe(true);
  expect(errors).toEqual([]);
});
test('fixtures: filas vazias, consumidor ausente, envelhecimento, falha e replay confirmado', async ({
  page,
}) => {
  let mode = 'fresh',
    posts = 0;
  const full = '11111111-1111-4111-8111-111111111111';
  const queue = (name: string, consumers: number, ready = 0) => ({
    name,
    consumer_service: 'writer',
    messages_ready: ready,
    messages_unacknowledged: 0,
    consumers,
    publish_rate: 0,
    delivery_rate: 0,
    durable: true,
    type: 'quorum',
    state: 'running',
  });
  const failure = {
    id: full,
    source_event_id: full,
    owner: 'writer',
    reason_code: 'influx_unavailable',
    attempts: 3,
    created_at: new Date().toISOString(),
    delivery_state: 'failed',
    preview: {
      type: 'telemetry.sampled',
      producer: 'simulator',
      device_id: 'ac_01',
    },
    can_replay: true,
    replay_count: 0,
  };
  await page.route('**/api/v1/messaging', (r) =>
    r.fulfill(
      mode === 'error'
        ? { status: 503, json: { title: 'Consulta indisponível (fixture)' } }
        : {
            json: {
              sampled_at: new Date(
                Date.now() - (mode === 'old' ? 60000 : 0),
              ).toISOString(),
              source: 'fixture',
              cache_seconds: 2,
              queues: [
                queue('q.telemetry.writer', 1),
                queue('q.inference', 0, 5),
                queue('q.dlq', 0, 2),
              ],
              recent_messages: { items: [], note: 'Fixture identificada' },
            },
          },
    ),
  );
  await page.route('**/api/v1/messaging/failures?*', (r) =>
    r.fulfill({
      json: {
        items: [
          {
            ...failure,
            id: '22222222-2222-4222-8222-222222222222',
            can_replay: false,
          },
        ],
        next_cursor: null,
        note: 'fixture',
      },
    }),
  );
  await page.route('**/api/v1/messaging/failures', (r) =>
    r.fulfill({
      json: {
        items: [failure],
        next_cursor: 'fixture-cursor',
        note: 'fixture',
      },
    }),
  );
  await page.route('**/api/v1/messaging/failures/*/replay', (r) => {
    posts++;
    expect(r.request().postDataJSON().request_id).toBeTruthy();
    return r.fulfill({ json: { status: 'requested', failure_id: full } });
  });
  await login(page);
  await visit(page, 'Mensageria');
  await expect(page.locator('[data-queue="q.telemetry.writer"]')).toContainText(
    'Fila vazia',
  );
  await expect(page.locator('[data-queue="q.inference"]')).toContainText(
    'Consumidor ausente',
  );
  await page.getByRole('button', { name: 'Mais falhas' }).click();
  await expect(page.locator('[data-failure-id]')).toHaveCount(2);
  const detail = page
    .locator('[data-failure-id]')
    .first()
    .getByText('Detalhes da falha', { exact: true });
  await detail.click();
  mode = 'old';
  await page.getByRole('button', { name: 'Atualizar mensageria' }).click();
  await expect(
    page.getByText('Dados desatualizados', { exact: true }),
  ).toBeVisible();
  await expect(page.locator('[data-failure-id]')).toHaveCount(2);
  await expect(
    page
      .locator('[data-failure-id]')
      .first()
      .getByText('Código:', { exact: false }),
  ).toBeVisible();
  mode = 'error';
  await page.getByRole('button', { name: 'Atualizar mensageria' }).click();
  await expect(page.getByRole('alert')).toContainText('fixture');
  await expect(page.locator('[data-queue="q.inference"]')).toContainText('5');
  await page.setViewportSize({ width: 390, height: 844 });
  await capture(page, 'fixture-messaging-stale');
  const replay = page.getByRole('button', {
    name: 'Reprocessar telemetria',
    exact: true,
  });
  await replay.tap();
  expect(posts).toBe(0);
  await expect(page.getByRole('dialog')).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await expect(replay).toBeFocused();
  expect(posts).toBe(0);
  await replay.click();
  await page
    .getByRole('button', { name: 'Confirmar reprocessamento', exact: true })
    .click();
  await expect(
    page.getByRole('status').filter({ hasText: 'Reprocessamento solicitado' }),
  ).toBeVisible();
  expect(posts).toBe(1);
  await expect(page.locator('[data-failure-id]')).toHaveCount(2);
});
test('fixtures: auditoria mantém página e detalhes em erro, códigos e payload omitido', async ({
  page,
}) => {
  let fail = false;
  const cursors: string[] = [];
  const item = (id: string) => ({
    id,
    created_at: '2026-11-15T12:34:56Z',
    action: 'command.unconfirmed',
    actor_username: 'operador_fixture',
    entity_type: 'command',
    entity_id: 'fixture-resource-id',
    outcome: 'failure',
    correlation_id: 'fixture-correlation',
    details: {
      password: 'NEVER_RENDER_SECRET',
      access_token: 'NEVER_RENDER_TOKEN',
      payload: 'NEVER_RENDER_PAYLOAD',
    },
  });
  await page.route('**/api/v1/audit?*', (r) => {
    const cursor = new URL(r.request().url()).searchParams.get('cursor');
    cursors.push(cursor ?? 'first');
    return r.fulfill(
      fail
        ? { status: 503, json: { title: 'Auditoria indisponível (fixture)' } }
        : {
            json: {
              items: [item(cursor ? 'page-two' : 'page-one')],
              next_cursor: cursor ? null : 'cursor-two',
            },
          },
    );
  });
  await login(page);
  await visit(page, 'Auditoria');
  await page.getByRole('button', { name: 'Próxima', exact: true }).click();
  await expect(page.getByText('Página 2', { exact: true })).toBeVisible();
  await expect(page.locator('[data-audit-id="page-two"]')).toContainText(
    'Falhou',
  );
  const detail = page.getByText('Detalhes do registro', { exact: true });
  await detail.focus();
  await page.keyboard.press('Enter');
  await expect(
    page.getByText('command.unconfirmed', { exact: true }),
  ).toBeVisible();
  fail = true;
  await page.getByRole('button', { name: 'Atualizar', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('fixture');
  await expect(page.getByText('Página 2', { exact: true })).toBeVisible();
  await expect(
    page.getByText('command.unconfirmed', { exact: true }),
  ).toBeVisible();
  await page.getByRole('button', { name: 'Anterior', exact: true }).click();
  await expect(page.getByText('Página 2', { exact: true })).toBeVisible();
  fail = false;
  await page.getByRole('button', { name: 'Anterior', exact: true }).click();
  await expect(page.getByText('Página 1', { exact: true })).toBeVisible();
  expect(cursors).toEqual([
    'first',
    'cursor-two',
    'cursor-two',
    'first',
    'first',
  ]);
  expect(await page.locator('.audit-page').innerText()).not.toMatch(
    /NEVER_RENDER/,
  );
  await page.route('**/api/v1/audit?*', (r) =>
    r.fulfill({ json: { items: [], next_cursor: null } }),
  );
  await page.getByRole('button', { name: 'Atualizar', exact: true }).click();
  await expect(
    page.getByText('Nenhuma operação registrada.', { exact: true }),
  ).toBeVisible();
});

test('fixture: recusa do replay é informada sem declarar execução', async ({
  page,
}) => {
  const id = '33333333-3333-4333-8333-333333333333';
  let posts = 0;
  await page.route('**/api/v1/messaging', (r) =>
    r.fulfill({
      json: {
        sampled_at: new Date().toISOString(),
        source: 'fixture',
        cache_seconds: 2,
        queues: [],
        recent_messages: { items: [], note: 'fixture' },
      },
    }),
  );
  await page.route('**/api/v1/messaging/failures', (r) =>
    r.fulfill({
      json: {
        items: [
          {
            id,
            source_event_id: id,
            owner: 'writer',
            reason_code: 'influx_unavailable',
            attempts: 3,
            created_at: new Date().toISOString(),
            delivery_state: 'failed',
            preview: {},
            can_replay: true,
            replay_count: 1,
          },
        ],
        next_cursor: null,
        note: 'fixture',
      },
    }),
  );
  await page.route('**/api/v1/messaging/failures/*/replay', (r) => {
    posts++;
    return r.fulfill({
      status: 409,
      json: { title: 'Falha não elegível para reprocessamento (fixture).' },
    });
  });
  await login(page);
  await visit(page, 'Mensageria');
  await page
    .getByRole('button', { name: 'Reprocessar telemetria', exact: true })
    .click();
  await page
    .getByRole('button', { name: 'Confirmar reprocessamento', exact: true })
    .click();
  await expect(page.getByRole('alert')).toContainText('não elegível');
  expect(posts).toBe(1);
  await expect(
    page.getByRole('status').filter({ hasText: 'Reprocessamento solicitado' }),
  ).toHaveCount(0);
});
