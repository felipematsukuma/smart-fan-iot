import { readFileSync, mkdirSync } from 'node:fs';
import { resolve } from 'node:path';
import { randomUUID } from 'node:crypto';
import type { Page } from '@playwright/test';
import { test, expect } from './fixtures';
import { verifyContrast } from './ui-contrast';
import { isServerControl } from '../src/lib/ws-control';

test.use({ hasTouch: true });
const evidence = resolve('../../evidence/ui-devices-insights');
mkdirSync(evidence, { recursive: true });
const password = () =>
  readFileSync(resolve('../../secrets/initial_admin_password'), 'utf8').trim();
async function login(page: Page, username = 'admin', secret = password()) {
  await page.goto('/entrar');
  await page.getByLabel('Usuário', { exact: true }).fill(username);
  await page.getByLabel('Senha', { exact: true }).fill(secret);
  await page.getByRole('button', { name: 'Entrar', exact: true }).click();
  await expect(
    page.getByRole('heading', { name: 'Visão geral', exact: true }),
  ).toBeVisible();
}
async function visit(page: Page, name: string) {
  if (page.viewportSize()!.width < 1024) {
    await page
      .getByRole('button', { name: 'Abrir navegação', exact: true })
      .click();
    await page
      .getByRole('dialog')
      .getByRole('link', { name, exact: true })
      .click();
  } else await page.getByRole('link', { name, exact: true }).click();
  await expect(page.getByRole('heading', { name, exact: true })).toBeVisible();
}
async function screenshot(page: Page, name: string) {
  await expect
    .poll(() =>
      page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
    )
    .toBe(true);
  await page.evaluate(() => scrollTo(0, 0));
  await page.screenshot({
    path: resolve(evidence, name + '.png'),
    fullPage: true,
  });
}
const ac = (page: Page) => page.locator('[data-device-id="ac_01"]');

test('dados reais: Dispositivos e Insights no desktop/celular, teclado e contrastes', async ({
  page,
}) => {
  test.setTimeout(70000);
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await login(page);
  await visit(page, 'Dispositivos');
  await ac(page)
    .getByRole('button', { name: /^Detalhes/ })
    .click();
  await expect(
    page.locator('.device-detail-grid [data-testid="physical-state"]'),
  ).toBeVisible({ timeout: 15000 });
  await expect(ac(page).getByText('Registrado', { exact: true })).toHaveCount(
    0,
  );
  await expect(ac(page)).toContainText('Habilitado');
  await expect(ac(page)).toContainText('Dados recentes');
  await page.getByText('Detalhes do cadastro', { exact: true }).focus();
  await page.keyboard.press('Enter');
  await expect(
    page.getByText('Sensores e faixas', { exact: true }),
  ).toBeVisible();
  await page.keyboard.press('Enter');
  await expect(page.locator('.historical-panel')).toHaveAttribute(
    'aria-busy',
    'false',
    { timeout: 25000 },
  );
  await verifyContrast(
    page,
    resolve(evidence, 'devices-desktop-contrast.json'),
  );
  await screenshot(page, 'devices-desktop');
  await page.setViewportSize({ width: 390, height: 844 });
  await verifyContrast(page, resolve(evidence, 'devices-mobile-contrast.json'));
  await screenshot(page, 'devices-mobile');
  await visit(page, 'Insights');
  await page
    .getByLabel('Equipamento dos insights', { exact: true })
    .selectOption('ac_01');
  await expect(page.locator('.insight-source')).toContainText(
    'Última leitura às',
    { timeout: 15000 },
  );
  await expect(
    page.getByRole('button', { name: 'Atualizar alertas', exact: true }),
  ).toBeEnabled();
  await expect
    .poll(
      async () =>
        Number(
          await page
            .locator('.insight-main-grid')
            .getAttribute('data-trend-points'),
        ),
      { timeout: 20000 },
    )
    .toBeGreaterThanOrEqual(6);
  await verifyContrast(
    page,
    resolve(evidence, 'insights-mobile-contrast.json'),
  );
  await screenshot(page, 'insights-mobile');
  await page.setViewportSize({ width: 1440, height: 1000 });
  await verifyContrast(
    page,
    resolve(evidence, 'insights-desktop-contrast.json'),
  );
  await screenshot(page, 'insights-desktop');
  await page
    .getByText('Comparação entre equipamentos', { exact: true })
    .first()
    .focus();
  await page.keyboard.press('Enter');
  await expect(
    page.getByRole('columnheader', { name: 'Estado da previsão', exact: true }),
  ).toBeVisible();
  await page
    .getByRole('button', {
      name: 'Consultar histórico de insights',
      exact: true,
    })
    .click();
  await expect(
    page.getByText('Registros e versões', { exact: true }),
  ).toBeVisible({ timeout: 20000 });
  await page.getByText('Registros e versões', { exact: true }).click();
  await expect(page.locator('.history-table tbody tr').first()).toBeVisible();
  expect(errors).toEqual([]);
});

test('fixtures de cadastro: erros próximos ao campo, salvamento, revisão, habilitação e configurações preservadas', async ({
  page,
}) => {
  test.setTimeout(60000);
  let seed: Record<string, unknown> = {};
  let fake: Record<string, unknown> | null = null;
  let failList = false;
  let emptyList = false;
  let posts = 0;
  let savedRule: Record<string, unknown> | null = null;
  let releaseSave!: () => void;
  const saveGate = new Promise<void>((resolveGate) => {
    releaseSave = resolveGate;
  });
  await page.route('**/api/v1/devices?**', async (route) => {
    if (failList)
      return route.fulfill({
        status: 503,
        json: { title: 'Consulta indisponível na fixture.' },
      });
    if (emptyList)
      return route.fulfill({ json: { items: [], next_cursor: null } });
    const response = await route.fetch();
    const body = await response.json();
    seed = body.items.find((item: { id: string }) => item.id === 'ac_01');
    await route.fulfill({
      response,
      json: { ...body, items: fake ? [fake, ...body.items] : body.items },
    });
  });
  await page.route('**/api/v1/devices', async (route) => {
    if (route.request().method() !== 'POST') return route.continue();
    posts++;
    const body = route.request().postDataJSON();
    if (body.id === 'ac_01')
      return route.fulfill({
        status: 409,
        json: { title: 'Dispositivo já cadastrado.' },
      });
    await saveGate;
    fake = {
      ...structuredClone(seed),
      ...body,
      revision: 1,
      enabled: true,
      boot_id: null,
      last_sample_at: null,
    };
    fake.sensor_ids = Object.fromEntries(
      Object.keys(seed.sensor_ids as object).map((key) => [
        key,
        `${body.id}_${key}`,
      ]),
    );
    await route.fulfill({ status: 201, json: fake });
  });
  await page.route('**/api/v1/devices/ui_fixture_device', async (route) => {
    const body = route.request().postDataJSON();
    expect(body.expected_revision).toBe(fake!.revision);
    expect(body).not.toHaveProperty('id');
    expect(body).not.toHaveProperty('zone');
    fake = { ...fake, ...body, revision: Number(fake!.revision) + 1 };
    await route.fulfill({ json: fake });
  });
  await page.route('**/api/v1/devices/ui_fixture_device/**', async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname.endsWith('/control'))
      return route.fulfill({ json: { fresh: false, observation: null } });
    if (url.pathname.endsWith('/commands'))
      return route.fulfill({ json: { items: [] } });
    if (url.pathname.endsWith('/metrics'))
      return route.fulfill({
        json: {
          period_start: new Date(Date.now() - 86400000).toISOString(),
          period_end: new Date().toISOString(),
          chart: [],
          energy: {
            energy_wh: null,
            coverage_fraction: 0,
            total_samples: 0,
            missing_samples: 0,
          },
        },
      });
    if (url.pathname.endsWith('/rule')) {
      if (route.request().method() === 'PATCH') {
        savedRule = route.request().postDataJSON();
        return route.fulfill({
          json: {
            ...(savedRule as object),
            revision: 2,
            timezone: 'America/Sao_Paulo',
          },
        });
      }
      const response = await route.fetch({
        url: route.request().url().replace('ui_fixture_device', 'ac_01'),
      });
      return route.fulfill({ response });
    }
    return route.continue();
  });
  await login(page);
  await visit(page, 'Dispositivos');
  await page
    .getByRole('button', { name: 'Novo dispositivo', exact: true })
    .click();
  await expect(page.getByLabel('Nome', { exact: true })).toBeFocused();
  await page
    .getByRole('button', { name: 'Salvar cadastro', exact: true })
    .click();
  await expect(page.getByLabel('Nome', { exact: true })).toHaveAttribute(
    'aria-invalid',
    'true',
  );
  expect(posts).toBe(0);
  await page
    .getByLabel('Nome', { exact: true })
    .fill('Equipamento de teste UI');
  await page.getByLabel('Zona', { exact: true }).fill('laboratorio');
  await page
    .getByLabel('ID do dispositivo', { exact: true })
    .fill('id inválido');
  await page
    .getByRole('button', { name: 'Salvar cadastro', exact: true })
    .click();
  await expect(page.locator('#device-id-error')).toContainText('Use letras');
  expect(posts).toBe(0);
  await page.getByLabel('ID do dispositivo', { exact: true }).fill('ac_01');
  await page
    .getByRole('button', { name: 'Salvar cadastro', exact: true })
    .click();
  await expect(page.locator('#device-id-error')).toContainText('já cadastrado');
  await page
    .getByLabel('ID do dispositivo', { exact: true })
    .fill('ui_fixture_device');
  await page
    .getByText('Perfil e faixas de referência', { exact: true })
    .click();
  await page.getByLabel('Corrente (A) — Máximo', { exact: true }).fill('0');
  await page
    .getByRole('button', { name: 'Salvar cadastro', exact: true })
    .click();
  await expect(page.locator('#field-current_a-maximum-error')).toContainText(
    'maior que o mínimo',
  );
  expect(posts).toBe(1);
  await page.getByLabel('Corrente (A) — Máximo', { exact: true }).fill('12');
  await page
    .getByRole('button', { name: 'Salvar cadastro', exact: true })
    .click();
  await expect(
    page.getByRole('button', { name: 'Salvando…', exact: true }),
  ).toBeDisabled();
  releaseSave();
  await expect(
    page.getByText('Cadastro salvo.', { exact: false }),
  ).toBeVisible();
  const row = page.locator('[data-device-id="ui_fixture_device"]');
  await expect(row.getByText('Registrado', { exact: true })).toHaveCount(0);
  await expect(row).toContainText('Habilitado');
  await expect(row).toContainText('Sem telemetria recente');
  await row.getByRole('button', { name: /^Editar/ }).click();
  await expect(
    page.getByLabel('ID do dispositivo', { exact: true }),
  ).toBeDisabled();
  await expect(page.getByLabel('Zona', { exact: true })).toBeDisabled();
  await page.getByLabel('Nome', { exact: true }).fill('Equipamento revisado');
  await page
    .getByRole('button', { name: 'Salvar cadastro', exact: true })
    .click();
  await expect(row).toContainText('Equipamento revisado');
  await row.getByRole('button', { name: /^Desabilitar/ }).click();
  await expect(row).toContainText('Desabilitado');
  await expect(
    page.getByRole('button', { name: 'Ligar ventilador', exact: true }),
  ).toBeDisabled();
  await page.getByText('Termostato e agenda', { exact: false }).click();
  await expect(
    page.getByLabel('Mínimo desligado (s)', { exact: true }),
  ).toHaveAttribute('min', '180');
  await page.getByRole('button', { name: 'Salvar regra', exact: true }).click();
  await expect(page.getByText('Regra salva;', { exact: false })).toBeVisible();
  expect(savedRule).toHaveProperty('expected_revision');
  expect(savedRule).toHaveProperty('configuration');
  failList = true;
  await page
    .getByRole('button', { name: 'Atualizar lista', exact: true })
    .click();
  await expect(page.getByRole('alert')).toContainText('Consulta indisponível');
  await expect(row).toBeVisible();
  failList = false;
  emptyList = true;
  await page
    .getByRole('button', { name: 'Atualizar lista', exact: true })
    .click();
  await expect(
    page.getByText('Nenhum dispositivo cadastrado.', { exact: true }),
  ).toBeVisible();
});

test('fixtures Insights: zero, aquecimento, inativo, dados antigos, erro e histórico separado', async ({
  page,
}) => {
  test.setTimeout(45000);
  const controls = JSON.parse(
    readFileSync('src/lib/ws.fixtures.json', 'utf8'),
  ) as { name: string; value: unknown }[];
  const snapshot = structuredClone(
    controls.find((item) => item.name === 'snapshot')!.value,
  );
  if (!isServerControl(snapshot) || snapshot.type !== 'snapshot')
    throw new Error('Invalid fixture');
  const frame = snapshot.events.find((item) => item.tipo === 'frame.ready');
  if (!frame || frame.tipo !== 'frame.ready') throw new Error('Missing frame');
  let streaming = false;
  let failed = false;
  const rule = {
    revision: 1,
    configuration: {
      enabled: true,
      health_raise: 40,
      health_clear: 60,
      rul_raise_hours: 24,
      rul_clear_hours: 48,
      bad_samples: 3,
      good_samples: 10,
    },
    state: null,
  };
  await page.route('**/api/v1/devices/ac_01/predictive-rule', (route) =>
    route.fulfill({ json: rule }),
  );
  await page.route('**/api/v1/insights/status', (route) =>
    route.fulfill({
      json: {
        selection: {
          active_version: 'fixture-v1',
          desired_version: 'fixture-v1',
        },
      },
    }),
  );
  await page.route('**/api/v1/alerts?**', (route) =>
    route.fulfill({
      status: failed ? 503 : 200,
      json: failed
        ? { title: 'Consulta indisponível na fixture.' }
        : {
            items: [
              {
                id: 'fixture-active',
                device_id: 'ac_01',
                severity: 'critical',
                status: 'active',
                raised_at: new Date().toISOString(),
                cleared_at: null,
                model_version: 'fixture-v1',
                rule_revision: 1,
              },
            ],
            next_cursor: null,
          },
    }),
  );
  await page.route('**/api/v1/devices/ac_01/insights/history?**', (route) =>
    route.fulfill({
      json: {
        items: [
          {
            sampled_at: new Date(Date.now() - 60000).toISOString(),
            boot_id: 'fixture-old',
            model_version: 'fixture-old',
            status: 'valid',
            health_score: 88,
            rul_calendar_hours: 25,
            source_event_id: 'fixture-history',
          },
        ],
        next_cursor: null,
      },
    }),
  );
  await page.routeWebSocket('**/ws', (socket) => {
    let interval: ReturnType<typeof setInterval>;
    socket.onMessage((raw) => {
      if (JSON.parse(raw.toString()).type !== 'authenticate') return;
      snapshot.server_time = new Date().toISOString();
      snapshot.events = [];
      socket.send(
        JSON.stringify({
          type: 'authenticated',
          server_time: snapshot.server_time,
          heartbeat_seconds: 15,
          stale_after_seconds: 6,
        }),
      );
      socket.send(JSON.stringify(snapshot));
      interval = setInterval(() => {
        if (!streaming) return;
        frame.timestamp = new Date().toISOString();
        frame.metadata.observed_at = frame.timestamp;
        frame.id = randomUUID();
        frame.metadata.sequence++;
        socket.send(JSON.stringify(frame));
      }, 200);
    });
    socket.onClose(() => clearInterval(interval));
  });
  await login(page);
  await visit(page, 'Insights');
  await expect(page.getByTestId('insight-status')).toHaveText(
    'Aguardando telemetria',
  );
  frame.conteudo.insight = {
    status: 'valid',
    model_version: 'fixture-v1',
    feature_version: 'hvac-window-v1',
    health_score: 0,
    rul_calendar_hours: 0,
  };
  streaming = true;
  await expect(page.getByTestId('insight-health')).toHaveText('0%');
  await expect(page.getByTestId('insight-rul')).toHaveText('0h');
  await page
    .getByRole('button', {
      name: 'Consultar histórico de insights',
      exact: true,
    })
    .click();
  await page.getByText('Registros e versões', { exact: true }).click();
  await expect(page.locator('.history-table')).toContainText('88');
  await expect(page.getByTestId('insight-health')).toHaveText('0%');
  await page.getByText('Regra preditiva', { exact: true }).click();
  await page
    .getByRole('button', { name: 'Editar regra preditiva', exact: true })
    .click();
  await expect(
    page.getByLabel('Previsões ruins consecutivas', { exact: true }),
  ).toHaveAttribute('min', '3');
  await expect(
    page.getByLabel('Previsões boas consecutivas', { exact: true }),
  ).toHaveAttribute('min', '10');
  await page
    .getByRole('button', { name: 'Cancelar edição', exact: true })
    .click();
  for (const [status, label] of [
    ['warming_up', 'Aquecendo a janela de observação'],
    ['inactive', 'Compressor inativo'],
    ['model_unavailable', 'Modelo indisponível'],
  ] as const) {
    frame.conteudo.insight = {
      ...frame.conteudo.insight,
      status,
      health_score: null,
      rul_calendar_hours: null,
    };
    await expect(page.getByTestId('insight-status')).toHaveText(label);
    await expect(page.getByTestId('insight-health')).toHaveText('—');
    await expect(page.getByTestId('insight-rul')).toHaveText('—');
  }
  failed = true;
  await page
    .getByRole('button', { name: 'Atualizar alertas', exact: true })
    .click();
  await expect(page.getByRole('alert')).toContainText(
    'Não foi possível atualizar alertas',
  );
  await expect(page.locator('.insight-alert-list')).toContainText(
    'Ativo · Crítico',
  );
  streaming = false;
  await expect(page.getByTestId('insight-status')).toHaveText(
    'Sem dados recentes',
    { timeout: 10000 },
  );
  await expect(
    page.getByText('Atualização interrompida', { exact: true }),
  ).toBeVisible();
  await expect(page.locator('.history-table')).toContainText('88');
  frame.conteudo.insight = {
    ...frame.conteudo.insight,
    status: 'valid',
    health_score: 0,
    rul_calendar_hours: 0,
  };
  streaming = true;
  failed = false;
  await page
    .getByRole('button', { name: 'Tentar novamente', exact: true })
    .click();
  await expect(page.getByTestId('insight-status')).toHaveText(
    'Previsão disponível',
  );
  await expect(page.getByTestId('insight-health')).toHaveText('0%');
});

test('papéis reais: visualizador e operador preservam autorização de cadastros, comandos e regras', async ({
  browser,
  request,
}) => {
  test.setTimeout(60000);
  const auth = await request.post('/api/v1/auth/login', {
    data: { username: 'admin', password: password() },
  });
  const headers = {
    Authorization: `Bearer ${(await auth.json()).access_token}`,
    Origin: 'http://127.0.0.1:8080',
  };
  for (const role of ['visualizador', 'operador']) {
    const username = 'ui_' + randomUUID().replaceAll('-', '').slice(0, 16);
    const secret = randomUUID() + randomUUID();
    const created = await request.post('/api/v1/users', {
      headers,
      data: { username, password: secret, role },
    });
    expect(created.status()).toBe(201);
    const identity = (await created.json()).id;
    const context = await browser.newContext({
      baseURL: 'http://127.0.0.1:8080',
      viewport: { width: 1440, height: 1000 },
    });
    const page = await context.newPage();
    try {
      await login(page, username, secret);
      await visit(page, 'Dispositivos');
      await expect(
        page.getByRole('button', { name: 'Novo dispositivo', exact: true }),
      ).toHaveCount(0);
      await expect(
        ac(page).getByRole('button', { name: /^Editar/ }),
      ).toHaveCount(0);
      await ac(page)
        .getByRole('button', { name: /^Detalhes/ })
        .click();
      await expect(
        page.getByRole('button', { name: 'Ligar ventilador', exact: true }),
      ).toHaveCount(role === 'operador' ? 1 : 0);
      await page.getByText('Termostato e agenda', { exact: false }).click();
      await expect(
        page.getByLabel('Setpoint (°C)', { exact: true }),
      ).toBeDisabled();
      await expect(
        page.getByRole('button', { name: 'Salvar regra', exact: true }),
      ).toHaveCount(0);
      await visit(page, 'Insights');
      await page
        .getByLabel('Equipamento dos insights', { exact: true })
        .selectOption('ac_01');
      await page.getByText('Regra preditiva', { exact: true }).click();
      await expect(
        page.getByRole('button', {
          name: 'Editar regra preditiva',
          exact: true,
        }),
      ).toHaveCount(0);
      const signed = await request.post('/api/v1/auth/login', {
        data: { username, password: secret },
      });
      const ownHeaders = {
        Authorization: `Bearer ${(await signed.json()).access_token}`,
        Origin: 'http://127.0.0.1:8080',
      };
      expect(
        (
          await request.patch('/api/v1/devices/ac_01', {
            headers: ownHeaders,
            data: { expected_revision: 1, name: 'Não deve alterar' },
          })
        ).status(),
      ).toBe(403);
      expect(
        (
          await request.patch('/api/v1/devices/ac_01/predictive-rule', {
            headers: ownHeaders,
            data: {
              expected_revision: 1,
              configuration: {
                enabled: true,
                health_raise: 40,
                health_clear: 60,
                rul_raise_hours: 24,
                rul_clear_hours: 48,
                bad_samples: 3,
                good_samples: 10,
              },
            },
          })
        ).status(),
      ).toBe(403);
      if (role === 'visualizador')
        expect(
          (
            await request.post('/api/v1/devices/ac_01/commands', {
              headers: { ...ownHeaders, 'Idempotency-Key': randomUUID() },
              data: { action: 'fan_on' },
            })
          ).status(),
        ).toBe(403);
    } finally {
      await context.close();
      expect(
        (
          await request.patch(`/api/v1/users/${identity}`, {
            headers,
            data: { enabled: false },
          })
        ).status(),
      ).toBe(204);
    }
  }
});

test('fixture de comandos em Dispositivos separa aceitação, execução validada e observação', async ({
  page,
}) => {
  test.setTimeout(40000);
  let command: {
    id: string;
    revision: number;
    producer: string;
    status: string;
    result: string | null;
    reason_code: string;
    execution_unknown: boolean;
    created_at: string;
    ack_event_id: string | null;
  } | null = null;
  let fan = false;
  let hideSelected = false;
  await page.route('**/api/v1/devices?**', async (route) => {
    const response = await route.fetch();
    const body = await response.json();
    await route.fulfill({
      response,
      json: {
        ...body,
        items: hideSelected
          ? body.items.filter((device: { id: string }) => device.id !== 'ac_01')
          : body.items,
      },
    });
  });
  await page.route('**/api/v1/devices/ac_01/control', (route) =>
    route.fulfill({
      json: {
        fresh: true,
        observation: {
          sampled_at: new Date().toISOString(),
          mode: 'manual',
          manual_cooling_block: false,
          telemetry: {
            actuators: { compressor_on: false, condenser_fan_on: fan },
          },
        },
      },
    }),
  );
  await page.route('**/api/v1/devices/ac_01/commands', (route) => {
    if (route.request().method() === 'POST') {
      expect(route.request().postDataJSON()).toEqual({ action: 'fan_on' });
      expect(route.request().headers()['idempotency-key']).toBeTruthy();
      command = {
        id: randomUUID(),
        revision: 1,
        producer: 'api',
        status: 'pending',
        result: null,
        reason_code: 'manual',
        execution_unknown: false,
        created_at: new Date().toISOString(),
        ack_event_id: null,
      };
      return route.fulfill({ status: 202, json: command });
    }
    return route.fulfill({ json: { items: command ? [command] : [] } });
  });
  await login(page);
  await visit(page, 'Dispositivos');
  await ac(page)
    .getByRole('button', { name: /^Detalhes/ })
    .click();
  await expect(
    page.getByRole('button', { name: 'Ligar ventilador', exact: true }),
  ).toBeEnabled({ timeout: 15000 });
  await page
    .getByRole('button', { name: 'Ligar ventilador', exact: true })
    .click();
  await expect(page.locator('.pv-command-progress')).toContainText(
    'Aceito pela API',
  );
  await expect(
    page.getByTestId('physical-state').getByText('Desligado', { exact: true }),
  ).toHaveCount(2);
  command!.status = 'confirmed';
  await expect(page.locator('.pv-command-progress')).toContainText(
    'Sem execução confirmada',
    { timeout: 5000 },
  );
  command!.ack_event_id = randomUUID();
  command!.result = 'applied';
  await expect(page.locator('.pv-command-progress')).toContainText(
    'Executado pelo dispositivo',
    { timeout: 5000 },
  );
  await expect(
    page.getByTestId('physical-state').getByText('Desligado', { exact: true }),
  ).toHaveCount(2);
  fan = true;
  await expect(
    page.getByTestId('physical-state').getByText('Ligado', { exact: true }),
  ).toHaveCount(1, { timeout: 5000 });
  hideSelected = true;
  await page
    .getByRole('button', { name: 'Atualizar lista', exact: true })
    .click();
  await expect(ac(page)).toHaveCount(0);
  await expect(
    page.getByRole('button', { name: 'Ligar ventilador', exact: true }),
  ).toBeEnabled();
  await expect(
    page.getByTestId('physical-state').getByText('Ligado', { exact: true }),
  ).toHaveCount(1);
});

test('encerramento: motivo registrado, ausência explícita, badges e expansíveis compactos', async ({
  page,
}) => {
  await page.route('**/api/v1/alerts?**', (route) =>
    route.fulfill({
      json: {
        items: ['health_low', 'predictive_health_or_rul', null, 'unknown'].map(
          (reason, index) => ({
            id: `reason-fixture-${index}`,
            device_id: 'ac_01',
            reason_code: reason,
            status: 'active',
            severity: 'critical',
            raised_at: '2026-11-15T12:00:00Z',
            cleared_at: null,
            model_version: 'reason-fixture-model',
            rule_revision: 7,
          }),
        ),
        next_cursor: null,
      },
    }),
  );
  await login(page);
  await visit(page, 'Insights');
  await page
    .getByLabel('Equipamento dos insights', { exact: true })
    .selectOption('ac_01');
  const alerts = page.locator('.insight-alert-list > li');
  await expect(alerts).toHaveCount(4);
  await expect(alerts.nth(0)).toContainText('Saúde estimada abaixo do limite.');
  await expect(alerts.nth(1)).toContainText(
    'condição específica não registrada',
  );
  for (const index of [2, 3])
    await expect(alerts.nth(index)).toContainText(
      'Motivo não disponível no registro do alerta.',
    );
  await expect(alerts.nth(0)).toContainText('Ativo · Crítico');
  await expect(alerts.nth(0)).toContainText('Início:');
  await expect(
    page.getByText('reason-fixture-model', { exact: true }).first(),
  ).not.toBeVisible();
  const compact = page.locator('.insight-expandable');
  await expect(compact).toHaveCount(3);
  for (const card of await compact.all()) {
    expect((await card.boundingBox())!.height).toBeLessThanOrEqual(60);
    expect(
      (await card.locator('summary').first().boundingBox())!.height,
    ).toBeGreaterThanOrEqual(44);
  }
  const modelDetails = compact.first().locator('summary').first();
  await modelDetails.focus();
  await page.keyboard.press('Enter');
  await expect(compact.first().locator('details').first()).toHaveAttribute(
    'open',
    '',
  );
  await expect(modelDetails).toBeFocused();
  await page.keyboard.press('Enter');
  await page.setViewportSize({ width: 390, height: 844 });
  const summary = compact.last().locator('summary').first();
  await summary.tap();
  await expect(compact.last().locator('details').first()).toHaveAttribute(
    'open',
    '',
  );
  await summary.tap();
  await expect(compact.last().locator('details').first()).not.toHaveAttribute(
    'open',
    '',
  );
  await verifyContrast(
    page,
    resolve(evidence, 'closure-insights-contrast.json'),
  );
  await screenshot(page, 'insights-reasons-fixture-mobile');
  await visit(page, 'Dispositivos');
  await expect(page.getByText('Registrado', { exact: true })).toHaveCount(0);
  await expect(ac(page)).toContainText('Habilitado');
  await expect(ac(page)).toContainText(
    /Dados recentes|Dados desatualizados|Sem telemetria recente|Telemetria indisponível/,
  );
});
