import { readFileSync, mkdirSync } from 'node:fs';
import { resolve } from 'node:path';
import type { Page } from '@playwright/test';
import { test, expect } from './fixtures';
import { verifyContrast } from './ui-contrast';
test.use({ hasTouch: true });
const output = resolve('../../evidence/ui-data-training');
mkdirSync(output, { recursive: true });
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
  await verifyContrast(page, resolve(output, name + '-contrast.json'));
  await page.evaluate(() => {
    scrollTo(0, 0);
    document.querySelectorAll('.tp-table').forEach((element) => {
      element.scrollLeft = 0;
    });
  });
  await page.screenshot({
    path: resolve(output, name + '.png'),
    fullPage: true,
  });
}
test('consultas reais: dados e resultados existentes em desktop e celular', async ({
  page,
}) => {
  test.setTimeout(90000);
  const errors: string[] = [];
  page.on('pageerror', (e) => errors.push(e.message));
  // Safety: this test must never submit jobs or promotion.
  await page.route('**/api/v1/**', async (route) => {
    if (
      route.request().method() === 'POST' &&
      /\/(lab\/jobs|training\/jobs|promote|cancel)$/.test(
        new URL(route.request().url()).pathname,
      )
    )
      throw new Error('Escrita não autorizada no ensaio visual');
    await route.continue();
  });
  await login(page);
  await visit(page, 'Dados sintéticos');
  await expect(page.getByTestId('dataset-estimate')).toContainText(
    'Estimativa:',
  );
  const advanced = page.getByText('Opções avançadas', { exact: true });
  await advanced.focus();
  await page.keyboard.press('Enter');
  await expect(page.getByLabel('Ruído normalizado')).toBeVisible();
  await page.keyboard.press('Enter');
  const completed = page
    .locator('.jobs tbody tr')
    .filter({ hasText: 'Concluído' })
    .first();
  await expect(completed).toBeVisible();
  await completed.getByRole('button').click();
  await expect(
    page.getByRole('heading', { name: 'Resultado gerado' }),
  ).toBeVisible();
  await expect(
    page.locator('.jobs tbody tr').first().getByRole('button'),
  ).toHaveText('Ver geração');
  const identity = page
    .locator('.job-detail')
    .getByText('Identificação do job', { exact: true });
  await identity.focus();
  await page.keyboard.press('Enter');
  const fullId = await page.locator('.job-detail').getAttribute('data-job-id');
  await expect(page.locator('.job-detail code').first()).toHaveText(fullId!);
  await page.context().grantPermissions(['clipboard-read', 'clipboard-write']);
  await page
    .locator('.job-detail')
    .getByRole('button', { name: 'Copiar identificador', exact: true })
    .first()
    .click();
  await expect
    .poll(() => page.evaluate(() => navigator.clipboard.readText()))
    .toBe(fullId);
  await identity.click();
  await capture(page, 'data-desktop');
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.locator('.jobs tbody tr').first()).toContainText('Geração');
  expect(
    await page
      .locator('.jobs .tp-table')
      .evaluate((el) => el.scrollWidth <= el.clientWidth),
  ).toBe(true);
  await capture(page, 'data-mobile');
  await advanced.tap();
  await expect(page.getByLabel('Ruído normalizado')).toBeVisible();
  await advanced.tap();
  await visit(page, 'Treinamento');
  const trained = page
    .locator('.registry tbody tr')
    .filter({ hasText: 'Concluído' })
    .first();
  await expect(trained).toBeVisible();
  await trained.getByRole('button').click();
  await expect(
    page.getByRole('heading', { name: 'Métricas por alvo' }),
  ).toBeVisible();
  await expect(page.locator('.metric-target')).toHaveCount(2);
  await expect(
    page.getByRole('heading', { name: 'Previsto × real' }),
  ).toBeVisible();
  await expect(page.locator('.responsive-metrics').first()).toBeVisible();
  expect(
    await page
      .locator('.responsive-metrics')
      .first()
      .evaluate((el) => el.scrollWidth <= el.clientWidth),
  ).toBe(true);
  await expect(
    page.getByRole('img', { name: /Importância por permutação: 5 de/ }),
  ).toBeVisible();
  expect(
    await page
      .locator('.responsive-metrics caption')
      .first()
      .evaluate((el) => el.getBoundingClientRect().height),
  ).toBeLessThan(120);
  await capture(page, 'training-mobile');
  await page.setViewportSize({ width: 1440, height: 1000 });
  await capture(page, 'training-desktop');
  await page.getByLabel('Alvo dos gráficos').selectOption('rul_calendar_hours');
  await expect(
    page.getByRole('img', { name: /Previsto versus real, h/ }),
  ).toBeVisible();
  expect(errors).toEqual([]);
});
test('fixtures: validação, valores preservados, contrato percentual e cancelamento confirmado', async ({
  page,
}) => {
  const job = {
    id: 'ui-fixture-job',
    dataset_id: 'ui-fixture-dataset',
    kind: 'generate',
    status: 'running',
    processed: 100,
    total: 1000,
    cancel_requested: false,
    reason_code: null,
    attempts: 1,
    updated_at: new Date().toISOString(),
  };
  let writes = 0;
  let fail = true;
  let body: Record<string, unknown> = {};
  await page.route('**/api/v1/jobs?*', (r) =>
    r.fulfill({ json: { items: [job] } }),
  );
  await page.route('**/api/v1/lab/jobs', async (r) => {
    writes++;
    body = r.request().postDataJSON();
    await r.fulfill(
      fail
        ? { status: 422, json: { title: 'Configuração recusada (fixture)' } }
        : { json: job },
    );
  });
  await page.route('**/api/v1/jobs/ui-fixture-job/cancel', async (r) => {
    job.cancel_requested = true;
    await r.fulfill({ json: job });
  });
  await login(page);
  await visit(page, 'Dados sintéticos');
  const equipment = page.getByLabel('Equipamentos sintéticos');
  await equipment.fill('2');
  await page
    .getByRole('button', { name: 'Gerar dataset', exact: true })
    .click();
  await expect(page.locator('.tp-field-error')).toBeVisible();
  expect(writes).toBe(0);
  await equipment.fill('30');
  await page.getByLabel('Equipamentos com falha (%)').fill('25');
  await page
    .getByRole('button', { name: 'Gerar dataset', exact: true })
    .click();
  await expect(
    page.getByRole('alert').filter({ hasText: 'Configuração recusada' }),
  ).toBeVisible();
  await expect(equipment).toHaveValue('30');
  expect(body.failure_fraction).toBe(0.25);
  fail = false;
  await page
    .getByRole('button', { name: 'Gerar dataset', exact: true })
    .click();
  await page.getByRole('button', { name: 'Cancelar geração' }).click();
  await expect(
    page.getByRole('button', { name: 'Cancelar geração' }),
  ).toBeDisabled();
  await expect(page.locator('.job-detail')).toContainText(
    'Cancelamento solicitado',
  );
  await expect(page.locator('.job-detail')).toHaveAttribute(
    'data-job-status',
    'running',
  );
  job.status = 'cancelled';
  await expect(page.locator('.job-detail')).toHaveAttribute(
    'data-job-status',
    'cancelled',
    { timeout: 7000 },
  );
});

test('fixtures: treino, erro preservado e cancelamento sem ativação', async ({
  page,
}) => {
  const job = {
    id: 'fixture-train',
    dataset_id: 'fixture-data',
    kind: 'train',
    status: 'running',
    processed: 35,
    total: 100,
    cancel_requested: false,
    reason_code: null,
    updated_at: new Date().toISOString(),
  };
  const model = {
    version: 'fixture-model',
    dataset_id: job.dataset_id,
    job_id: job.id,
    status: 'running',
    approved: false,
    artifact_sha256: null,
  };
  const selection = {
    active_version: 'previous-active',
    desired_version: 'previous-active',
    active_revision: 2,
    activation_revision: 2,
  };
  let fail = true;
  let payload: Record<string, unknown> = {};
  await page.route('**/api/v1/jobs?*', (r) =>
    r.fulfill({
      json: {
        items:
          new URL(r.request().url()).searchParams.get('kind') === 'generate'
            ? [
                {
                  ...job,
                  id: 'generation',
                  status: 'completed',
                  processed: 1000000,
                  total: 1000000,
                },
              ]
            : [job],
      },
    }),
  );
  await page.route('**/api/v1/models?*', (r) =>
    r.fulfill({ json: { items: [model], selection, next_cursor: null } }),
  );
  await page.route('**/api/v1/models/fixture-model', (r) =>
    r.fulfill({ json: model }),
  );
  await page.route('**/api/v1/training/jobs', (r) => {
    payload = r.request().postDataJSON();
    return r.fulfill(
      fail
        ? { status: 422, json: { title: 'Treino recusado (fixture)' } }
        : { json: job },
    );
  });
  await page.route('**/api/v1/jobs/fixture-train/cancel', (r) => {
    job.cancel_requested = true;
    return r.fulfill({ json: job });
  });
  await login(page);
  await visit(page, 'Treinamento');
  await page.getByLabel('Semente da divisão').fill('123');
  await page
    .getByRole('button', { name: 'Treinar modelos', exact: true })
    .click();
  await expect(page.getByRole('alert')).toContainText('Treino recusado');
  await expect(page.getByLabel('Semente da divisão')).toHaveValue('123');
  expect(payload.seed).toBe(123);
  fail = false;
  await page
    .getByRole('button', { name: 'Treinar modelos', exact: true })
    .click();
  await expect(page.locator('.model-detail')).toContainText(
    '35% informado pelo treino',
  );
  await expect(page.getByTestId('active-model')).toHaveText('previous-active');
  await page.getByRole('button', { name: 'Cancelar treino' }).click();
  await expect(
    page.getByRole('button', { name: 'Cancelar treino' }),
  ).toBeDisabled();
  await expect(page.locator('.model-detail')).toContainText(
    'aguardando parada confirmada',
  );
  job.status = 'cancelled';
  model.status = 'cancelled';
  await expect(page.locator('.model-detail')).toHaveAttribute(
    'data-model-status',
    'cancelled',
    { timeout: 8000 },
  );
  await expect(page.getByTestId('active-model')).toHaveText('previous-active');
});
for (const role of ['visualizador', 'operador'])
  test(`fixture de papel ${role}: navegação administrativa oculta`, async ({
    page,
  }) => {
    await page.route('**/api/v1/auth/me', async (r) => {
      const response = await r.fetch();
      const user = await response.json();
      await r.fulfill({ response, json: { ...user, role } });
    });
    await login(page);
    await expect(
      page.getByRole('link', { name: 'Dados sintéticos', exact: true }),
    ).toHaveCount(0);
    await expect(
      page.getByRole('link', { name: 'Treinamento', exact: true }),
    ).toHaveCount(0);
  });
