import { execFileSync } from 'node:child_process';
import { readFileSync, mkdirSync } from 'node:fs';
import { resolve } from 'node:path';
import { randomUUID } from 'node:crypto';
import type { Page } from '@playwright/test';
import { test, expect } from './fixtures';
import { isServerControl } from '../src/lib/ws-control';

test.use({ viewport: { width: 390, height: 844 }, hasTouch: true });
const root = resolve('../..');
const evidence = resolve(root, 'evidence/ui-pilot');
mkdirSync(evidence, { recursive: true });
async function login(page: Page) {
  await page.goto('/entrar');
  await page.getByLabel('Usuário', { exact: true }).fill('admin');
  await page
    .getByLabel('Senha', { exact: true })
    .fill(
      readFileSync(
        resolve(root, 'secrets/initial_admin_password'),
        'utf8',
      ).trim(),
    );
  await page.getByRole('button', { name: 'Entrar', exact: true }).click();
  await page.getByLabel('Equipamento', { exact: true }).selectOption('ac_01');
}

test('fluxo real: recente, interrupção com socket ativo e retomada, sem perder pontos', async ({
  page,
}) => {
  test.setTimeout(60000);
  await login(page);
  await expect(page.locator('.pv-freshness')).toContainText('Dados recentes');
  await expect
    .poll(
      () => page.locator('.pv-live-chart .pv-section-heading').innerText(),
      { timeout: 25000 },
    )
    .toMatch(/(?:[8-9]|[1-9][0-9]) amostras/);
  await page.evaluate(() => scrollTo(0, 0));
  await page.screenshot({
    path: resolve(evidence, 'closure-mobile-fresh.png'),
    fullPage: true,
  });
  execFileSync('docker', ['compose', 'pause', 'simulator'], {
    cwd: root,
    stdio: 'pipe',
  });
  try {
    await expect(page.locator('.pv-freshness')).toContainText(
      'Dados desatualizados',
      { timeout: 12000 },
    );
    const state = await page.locator('.pv-freshness').innerText();
    const seconds = Number(/há (\d+) s/.exec(state)?.[1]);
    expect(seconds).toBeGreaterThanOrEqual(6);
    await expect(
      page.getByRole('heading', { name: 'Últimas leituras', exact: true }),
    ).toBeVisible();
    await expect(
      page.getByText('Atualização interrompida', { exact: true }),
    ).toHaveCount(1);
    await expect(
      page.getByText('Conexão ao vivo: Conectada', { exact: true }),
    ).toBeVisible();
    const range = await page.locator('.pv-visible-range').innerText();
    const frameId = await page
      .locator('.pv-live-chart')
      .getAttribute('data-frame-id');
    await page.waitForTimeout(1100);
    expect(await page.locator('.pv-visible-range').innerText()).toBe(range);
    await expect(page.locator('.pv-live-chart')).toHaveAttribute(
      'data-frame-id',
      frameId!,
    );
    await expect(page.locator('.power-chart canvas')).toBeVisible();
    await page.evaluate(() => scrollTo(0, 0));
    await page.screenshot({
      path: resolve(evidence, 'closure-mobile-stale.png'),
      fullPage: true,
    });
  } finally {
    execFileSync('docker', ['compose', 'unpause', 'simulator'], {
      cwd: root,
      stdio: 'pipe',
    });
  }
  await expect(page.locator('.pv-freshness')).toContainText('Dados recentes', {
    timeout: 15000,
  });
  await expect(
    page.getByRole('heading', { name: 'Potência em tempo real', exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText('Atualização interrompida', { exact: true }),
  ).toHaveCount(0);
});

test('fixture: ausência distinta de dados antigos, relógio coerente e plural dos alertas', async ({
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
  let count = 1;
  let sent = 0;
  await page.route('**/api/v1/alerts?**', (route) =>
    route.fulfill({
      json: {
        items: Array.from({ length: count }, (_, index) => ({
          id: `fixture-${index}`,
          device_id: 'ac_01',
          status: 'active',
          severity: 'warning',
          raised_at: new Date().toISOString(),
          cleared_at: null,
          model_version: 'fixture',
          rule_revision: 1,
        })),
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
        frame.metadata.sequence++;
        frame.id = randomUUID();
        sent++;
        socket.send(JSON.stringify(frame));
      }, 100);
    });
    socket.onClose(() => clearInterval(interval));
  });
  await login(page);
  await expect(page.locator('.pv-freshness')).toContainText('Sem telemetria');
  await expect(page.locator('.pv-freshness')).not.toContainText('há 0 s');
  await expect(
    page.getByRole('heading', { name: 'Últimas leituras', exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText('Atualização interrompida', { exact: true }),
  ).toHaveCount(0);
  await expect(page.locator('.pv-priority')).toContainText('1 alerta ativo.');
  await page.evaluate(() => {
    const seen: string[] = [];
    (window as unknown as { freshnessErrors: string[] }).freshnessErrors = seen;
    new MutationObserver(() => {
      const text = document.querySelector('.pv-freshness')?.textContent ?? '';
      if (text.includes('Dados desatualizados') && /há 0 s/.test(text))
        seen.push(text);
    }).observe(document.body, {
      subtree: true,
      childList: true,
      characterData: true,
    });
  });
  streaming = true;
  await expect.poll(() => sent).toBeGreaterThan(20);
  await expect(page.locator('.pv-freshness')).toContainText('Dados recentes');
  expect(
    await page.evaluate(
      () =>
        (window as unknown as { freshnessErrors: string[] }).freshnessErrors,
    ),
  ).toEqual([]);
  count = 2;
  await expect(page.locator('.pv-priority')).toContainText(
    '2 alertas ativos.',
    { timeout: 12000 },
  );
});
