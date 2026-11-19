import { execFileSync } from 'node:child_process';
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { resolve } from 'node:path';
import { randomUUID } from 'node:crypto';
import type { Page } from '@playwright/test';
import { expect, test } from './fixtures';
import { isServerControl } from '../src/lib/ws-control';

const root = fileURLToPath(new URL('../../../', import.meta.url));
const controls = JSON.parse(
  readFileSync(
    resolve(root, 'web-smart-fan-iot/frontend/src/lib/ws.fixtures.json'),
    'utf8',
  ),
) as { name: string; value: unknown }[];
const evidence = resolve(root, 'evidence/ui-pilot');
mkdirSync(evidence, { recursive: true });
const docker = (...args: string[]) =>
  execFileSync('docker', ['compose', ...args], { cwd: root, stdio: 'pipe' });
const password = () =>
  readFileSync(
    process.env.AIOT_TEST_PASSWORD_FILE ??
      resolve(root, 'secrets/initial_admin_password'),
    'utf8',
  ).trim();
async function login(page: Page, username = 'admin', secret = password()) {
  await page.goto('/entrar');
  await page.getByLabel('Usuário', { exact: true }).fill(username);
  await page.getByLabel('Senha', { exact: true }).fill(secret);
  await page.getByRole('button', { name: 'Entrar', exact: true }).click();
  await expect(
    page.getByRole('heading', { name: 'Visão geral', exact: true }),
  ).toBeVisible();
}

test('piloto real: comando aceito não é execução, navegação responsiva e páginas preservadas', async ({
  page,
}) => {
  test.setTimeout(150000);
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await login(page);
  await page.getByLabel('Equipamento', { exact: true }).selectOption('ac_01');
  await expect(
    page.getByRole('status').filter({ hasText: 'Dados recentes' }),
  ).toBeVisible({ timeout: 20000 });
  await expect(page.getByTestId('physical-state')).toBeVisible({
    timeout: 15000,
  });
  await expect(page.locator('.historical-panel')).toHaveAttribute(
    'aria-busy',
    'false',
    { timeout: 20000 },
  );
  await expect
    .poll(
      () => page.locator('.pv-live-chart .pv-section-heading').innerText(),
      { timeout: 30000 },
    )
    .toMatch(/(?:1[0-9]|[2-9][0-9]) amostras/);
  await page.screenshot({
    path: resolve(evidence, 'desktop.png'),
    fullPage: true,
  });
  const measureContrast = () =>
    page.evaluate(() => {
      const canvas = document.createElement('canvas');
      canvas.width = canvas.height = 1;
      const ctx = canvas.getContext('2d')!;
      const rgba = (color: string) => {
        ctx.clearRect(0, 0, 1, 1);
        ctx.fillStyle = color;
        ctx.fillRect(0, 0, 1, 1);
        return [...ctx.getImageData(0, 0, 1, 1).data];
      };
      const over = (top: number[], bottom: number[]) =>
        top
          .slice(0, 3)
          .map((v, i) => v * (top[3]! / 255) + bottom[i]! * (1 - top[3]! / 255))
          .concat(255);
      const lum = (rgb: number[]) =>
        rgb
          .slice(0, 3)
          .map((v) => {
            const n = v / 255;
            return n <= 0.04045 ? n / 12.92 : ((n + 0.055) / 1.055) ** 2.4;
          })
          .reduce((sum, v, i) => sum + v * [0.2126, 0.7152, 0.0722][i]!, 0);
      return [
        ...document.querySelectorAll<HTMLElement>(
          '.pilot-view *, .pv-navigation *, .pv-topbar *',
        ),
      ]
        .filter(
          (el) =>
            el.getClientRects().length &&
            [...el.childNodes].some(
              (n) => n.nodeType === Node.TEXT_NODE && n.textContent?.trim(),
            ) &&
            !el.closest(':disabled, .sr-only'),
        )
        .map((el) => {
          const style = getComputedStyle(el);
          let bg = [255, 255, 255, 255];
          const ancestors: Element[] = [];
          let parent: Element | null = el;
          while (parent) {
            ancestors.unshift(parent);
            parent = parent.parentElement;
          }
          for (const item of ancestors)
            bg = over(rgba(getComputedStyle(item).backgroundColor), bg);
          const fg = over(rgba(style.color), bg);
          const a = lum(fg),
            b = lum(bg);
          const ratio = (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
          const size = parseFloat(style.fontSize);
          const large =
            size >= 24 || (size >= 18.66 && parseInt(style.fontWeight) >= 700);
          return {
            text: el.innerText?.trim().slice(0, 90),
            color: style.color,
            background: bg.slice(0, 3),
            size,
            ratio: +ratio.toFixed(2),
            required: large ? 3 : 4.5,
          };
        });
    });
  const contrast = await measureContrast();
  writeFileSync(
    resolve(evidence, 'contrast.json'),
    JSON.stringify(contrast, null, 2),
  );
  expect(contrast.filter((item) => item.ratio < item.required)).toEqual([]);
  expect(contrast.filter((item) => item.size < 14)).toEqual([]);
  const totals = await page.locator('.energy-summary').innerText();
  await page.locator('.pv-zoom select').selectOption('15');
  expect(await page.locator('.energy-summary').innerText()).toBe(totals);
  await page.locator('.pv-zoom select').selectOption('0');
  await page.setViewportSize({ width: 720, height: 450 });
  const cdp = await page.context().newCDPSession(page);
  await cdp.send('Emulation.setDeviceMetricsOverride', {
    width: 720,
    height: 450,
    deviceScaleFactor: 2,
    mobile: false,
  });
  await expect
    .poll(() =>
      page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
    )
    .toBe(true);
  await page.getByRole('button', { name: 'Abrir navegação' }).click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await page.keyboard.press('Escape');
  await page.screenshot({
    path: resolve(evidence, 'zoom-200.png'),
    fullPage: true,
  });
  await cdp.send('Emulation.clearDeviceMetricsOverride');
  await cdp.detach();
  await page.setViewportSize({ width: 1440, height: 1000 });
  const auth = await page.request.post('/api/v1/auth/login', {
    data: { username: 'admin', password: password() },
  });
  expect(auth.status()).toBe(200);
  const token = (await auth.json()).access_token;
  const headers = {
    Authorization: `Bearer ${token}`,
    Origin: 'http://127.0.0.1:8080',
  };
  const prior = await (
    await page.request.get('/api/v1/devices/ac_01/control', { headers })
  ).json();
  const wasOn = prior.observation.telemetry.actuators.condenser_fan_on;
  try {
    docker('pause', 'gateway');
    await page
      .getByRole('button', {
        name: wasOn ? 'Desligar ventilador' : 'Ligar ventilador',
        exact: true,
      })
      .click();
    await expect(page.locator('.pv-command-progress')).toContainText(
      'Aceito pela API',
    );
    await expect(page.locator('.pv-command-progress')).not.toContainText(
      'Executado pelo dispositivo',
    );
    await page.screenshot({
      path: resolve(evidence, 'pending-real.png'),
      fullPage: true,
    });
  } finally {
    docker('unpause', 'gateway');
  }
  await expect(page.locator('.pv-command-progress')).toContainText(
    'Executado pelo dispositivo',
    { timeout: 20000 },
  );
  await expect(
    page
      .getByTestId('physical-state')
      .locator('div')
      .filter({ hasText: 'Ventilador' })
      .locator('strong'),
  ).toHaveText(wasOn ? 'Desligado' : 'Ligado', { timeout: 15000 });
  // Restore the previous operating intention using the existing command flow.
  const restored = await page.request.post('/api/v1/devices/ac_01/commands', {
    headers: { ...headers, 'Idempotency-Key': randomUUID() },
    data: {
      action:
        prior.observation.mode === 'auto'
          ? 'release_auto'
          : wasOn
            ? 'fan_on'
            : 'fan_off',
    },
  });
  expect(restored.status()).toBe(202);
  const commandId = (await restored.json()).id;
  await expect
    .poll(
      async () =>
        (
          await (
            await page.request.get(`/api/v1/commands/${commandId}`, { headers })
          ).json()
        ).status,
      { timeout: 15000 },
    )
    .toBe('confirmed');

  await page
    .getByRole('link', { name: 'Detalhes do equipamento', exact: true })
    .click();
  await expect(
    page.getByRole('heading', { name: 'Dispositivos', exact: true }),
  ).toBeVisible();
  for (const name of [
    'Insights',
    'Cena 3D',
    'Assistente local',
    'Dados sintéticos',
    'Treinamento',
    'Mensageria',
    'Auditoria',
    'Usuários',
    'Interfaces locais',
  ]) {
    await page.getByRole('link', { name, exact: true }).click();
    await expect(page.locator('main h1').first()).toHaveText(name);
    if (name === 'Mensageria')
      await expect(page.locator('.pv-card').first()).toHaveCSS(
        'border-radius',
        '10.5px',
      );
    if (name === 'Cena 3D')
      await expect(page.locator('canvas[aria-label^="Cena 3D"]')).toBeVisible();
  }
  await page.getByRole('link', { name: 'Visão geral', exact: true }).click();
  await page.getByLabel('Equipamento', { exact: true }).selectOption('ac_01');
  await page.setViewportSize({ width: 768, height: 1024 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(
    page.getByRole('status').filter({ hasText: 'Dados recentes' }),
  ).toBeVisible({ timeout: 15000 });
  await expect(page.locator('.historical-panel')).toHaveAttribute(
    'aria-busy',
    'false',
    { timeout: 20000 },
  );
  await expect
    .poll(() =>
      page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
    )
    .toBe(true);
  await page.evaluate(
    () =>
      new Promise<void>((done) =>
        requestAnimationFrame(() => requestAnimationFrame(() => done())),
      ),
  );
  const mobileContrast = await measureContrast();
  writeFileSync(
    resolve(evidence, 'contrast-mobile.json'),
    JSON.stringify(mobileContrast, null, 2),
  );
  expect(
    mobileContrast.filter(
      (item) => item.ratio < item.required || item.size < 14,
    ),
  ).toEqual([]);
  await page.screenshot({
    path: resolve(evidence, 'mobile.png'),
    fullPage: true,
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  const trigger = page.getByRole('button', {
    name: 'Abrir navegação',
    exact: true,
  });
  await trigger.focus();
  await page.keyboard.press('Enter');
  const dialog = page.getByRole('dialog', {
    name: 'Navegação do Ventora',
    exact: true,
  });
  await expect(dialog).toBeVisible();
  await page.keyboard.press('Shift+Tab');
  expect(
    await dialog.evaluate((element) =>
      element.contains(document.activeElement),
    ),
  ).toBe(true);
  await page.screenshot({
    path: resolve(evidence, 'mobile-menu.png'),
    fullPage: true,
  });
  await page.keyboard.press('Escape');
  await expect(dialog).toHaveCount(0);
  await expect(trigger).toBeFocused();
  await trigger.press('Enter');
  await dialog.getByRole('link', { name: 'Dispositivos', exact: true }).click();
  await expect(dialog).toHaveCount(0);
  await expect(page.locator('#main-content')).toBeFocused();
  expect(errors).toEqual([]);
});

test('visualizador mantém autorização e menu reduzido; cadastro vazio é explícito', async ({
  page,
}) => {
  test.setTimeout(45000);
  const loginResponse = await page.request.post('/api/v1/auth/login', {
    data: { username: 'admin', password: password() },
  });
  const adminToken = (await loginResponse.json()).access_token;
  const adminHeaders = {
    Authorization: `Bearer ${adminToken}`,
    Origin: 'http://127.0.0.1:8080',
  };
  const viewerPassword = randomUUID() + randomUUID();
  const username = 'pilot_' + randomUUID().replaceAll('-', '').slice(0, 16);
  const created = await page.request.post('/api/v1/users', {
    headers: adminHeaders,
    data: { username, password: viewerPassword, role: 'visualizador' },
  });
  expect(created.status()).toBe(201);
  const identity = (await created.json()).id;
  try {
    await page.routeWebSocket('**/ws', (socket) =>
      socket.onMessage((raw) => {
        if (JSON.parse(raw.toString()).type === 'authenticate') {
          const now = new Date().toISOString();
          socket.send(
            JSON.stringify({
              type: 'authenticated',
              server_time: now,
              heartbeat_seconds: 15,
              stale_after_seconds: 6,
            }),
          );
          socket.send(
            JSON.stringify({
              type: 'snapshot',
              server_time: now,
              devices: [],
              events: [],
            }),
          );
        }
      }),
    );
    await login(page, username, viewerPassword);
    await expect(
      page.getByText('Nenhum equipamento disponível.', { exact: false }),
    ).toBeVisible();
    await expect(
      page.getByRole('link', { name: 'Mensageria', exact: true }),
    ).toHaveCount(0);
    await expect(
      page.getByRole('button', { name: 'Ligar ventilador', exact: true }),
    ).toHaveCount(0);
    const auth = await page.request.post('/api/v1/auth/login', {
      data: { username, password: viewerPassword },
    });
    const viewerToken = (await auth.json()).access_token;
    const forbidden = await page.request.post(
      '/api/v1/devices/ac_01/commands',
      {
        headers: {
          Authorization: `Bearer ${viewerToken}`,
          'Idempotency-Key': randomUUID(),
        },
        data: { action: 'fan_on' },
      },
    );
    expect(forbidden.status()).toBe(403);
  } finally {
    expect(
      (
        await page.request.patch(`/api/v1/users/${identity}`, {
          headers: adminHeaders,
          data: { enabled: false },
        })
      ).status(),
    ).toBe(204);
  }
});

test('fixtures explícitas: zero, indisponibilidade, stale, carregamento, erro e recuperação', async ({
  page,
}) => {
  test.setTimeout(60000);
  const fixture = structuredClone(
    controls.find((item) => item.name === 'snapshot')!.value,
  );
  if (!isServerControl(fixture) || fixture.type !== 'snapshot')
    throw new Error('Invalid snapshot fixture');
  const frame = fixture.events.find((item) => item.tipo === 'frame.ready');
  if (!frame || frame.tipo !== 'frame.ready') throw new Error('Missing frame');
  frame.conteudo.insight = {
    status: 'valid',
    model_version: 'fixture-zero',
    feature_version: 'hvac-window-v1',
    health_score: 0,
    rul_calendar_hours: 0,
  };
  frame.conteudo.telemetry.readings.power_w = 0;
  let streaming = true;
  let failedAlerts = true;
  let failedHistory = false;
  let releaseHistory!: () => void;
  const historyGate = new Promise<void>((resolveGate) => {
    releaseHistory = resolveGate;
  });
  await page.route('**/api/v1/alerts?**', (route) =>
    route.fulfill({
      status: failedAlerts ? 503 : 200,
      json: failedAlerts
        ? { title: 'Falha de consulta simulada para teste de interface.' }
        : { items: [], next_cursor: null },
    }),
  );
  await page.route('**/api/v1/devices/ac_01/commands', (route) =>
    route.fulfill({ json: { items: [] } }),
  );
  await page.route('**/api/v1/devices/ac_01/control', (route) =>
    route.fulfill({
      json: {
        fresh: true,
        observation: {
          sampled_at: new Date().toISOString(),
          mode: 'auto',
          manual_cooling_block: false,
          telemetry: { actuators: frame.conteudo.telemetry.actuators },
        },
      },
    }),
  );
  await page.route('**/api/v1/devices/ac_01/metrics?**', async (route) => {
    await historyGate;
    await route.fulfill({
      status: failedHistory ? 503 : 200,
      json: failedHistory
        ? { title: 'Histórico indisponível no teste.' }
        : {
            period_start: new Date(Date.now() - 3600000).toISOString(),
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
  });
  await page.routeWebSocket('**/ws', (socket) => {
    let interval: ReturnType<typeof setInterval>;
    const stamp = () => {
      const at = new Date().toISOString();
      frame.timestamp = at;
      frame.metadata.observed_at = at;
      frame.metadata.sequence++;
      frame.id = randomUUID();
      fixture.server_time = at;
      fixture.devices[0]!.last_sample_at = at;
    };
    socket.onMessage((raw) => {
      const packet = JSON.parse(raw.toString());
      if (packet.type === 'authenticate') {
        stamp();
        fixture.events = [frame];
        socket.send(
          JSON.stringify({
            type: 'authenticated',
            server_time: fixture.server_time,
            heartbeat_seconds: 15,
            stale_after_seconds: 6,
          }),
        );
        socket.send(JSON.stringify(fixture));
        interval = setInterval(() => {
          if (streaming) {
            stamp();
            socket.send(JSON.stringify(frame));
          }
        }, 1000);
      }
      if (packet.type === 'pong') return;
    });
    socket.onClose(() => clearInterval(interval));
  });
  await login(page);
  await expect(page.getByTestId('pilot-health')).toHaveText('0%');
  await expect(page.getByTestId('pilot-rul')).toHaveText('0h');
  await expect(page.locator('.historical-panel')).toHaveAttribute(
    'aria-busy',
    'true',
  );
  releaseHistory();
  await expect(
    page.getByText('Nenhuma leitura no período selecionado.', { exact: true }),
  ).toBeVisible();
  await expect(
    page
      .getByRole('alert')
      .filter({ hasText: 'Situação dos alertas não confirmada' }),
  ).toBeVisible();
  failedAlerts = false;
  await page
    .getByRole('button', { name: 'Tentar novamente', exact: true })
    .click();
  await expect(
    page.getByText('Nenhum alerta ativo confirmado na última consulta.', {
      exact: true,
    }),
  ).toBeVisible();
  failedHistory = true;
  await page
    .locator('.historical-panel')
    .getByRole('button', { name: 'Atualizar', exact: true })
    .click();
  await expect(
    page.getByRole('alert').filter({ hasText: 'Histórico indisponível' }),
  ).toBeVisible();
  frame.conteudo.insight = {
    status: 'warming_up',
    model_version: 'fixture-zero',
    feature_version: 'hvac-window-v1',
    health_score: null,
    rul_calendar_hours: null,
  };
  await expect(page.getByTestId('pilot-health')).toHaveText('—');
  await expect(
    page.getByText('Aquecendo a janela de observação', { exact: true }).first(),
  ).toBeVisible();
  await expect(page.locator('.pv-freshness')).not.toContainText('há ');
  streaming = false;
  const elapsed = Date.now() - Date.parse(frame.timestamp);
  await page.waitForTimeout(Math.max(0, 5000 - elapsed));
  await expect(page.locator('.pv-freshness')).toContainText('Dados recentes');
  await expect(page.locator('.pv-freshness')).not.toContainText('há ');
  await expect(
    page.getByRole('status').filter({ hasText: 'Dados desatualizados' }),
  ).toBeVisible({ timeout: 10000 });
  await expect(page.getByTestId('pilot-power')).toHaveText('—');
  await expect(
    page.getByRole('button', { name: 'Ligar ventilador', exact: true }),
  ).toBeDisabled();
  await expect(
    page.getByText('Conexão ao vivo: Conectada', { exact: true }),
  ).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  await expect
    .poll(() =>
      page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
    )
    .toBe(true);
  await page.screenshot({
    path: resolve(evidence, 'fixture-stale-error.png'),
    fullPage: true,
  });
});
